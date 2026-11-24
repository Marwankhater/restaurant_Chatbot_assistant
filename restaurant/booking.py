"""The reservation book, on SQLite.

A table is free for a request when no active reservation on it overlaps the requested seating
(start to start plus the seating length). Checking and inserting happen in one write transaction
(BEGIN IMMEDIATE), so two guests asking for the last table at the same moment cannot both get it.
Reservation codes are random, so one guest cannot guess another's code, and cancelling needs the
phone number the booking was made with.
"""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum

from restaurant.settings import Settings

SCHEMA = """
create table if not exists tables (
    table_id integer primary key,
    seats integer not null check (seats > 0)
);
create table if not exists reservations (
    code text primary key,
    table_id integer not null references tables(table_id),
    guest_name text not null,
    phone text not null,
    party_size integer not null check (party_size > 0),
    starts_at text not null,          -- local time, ISO 8601
    ends_at text not null,
    status text not null default 'confirmed' check (status in ('confirmed', 'cancelled')),
    created_at text not null
);
create index if not exists ix_reservations_table_time on reservations(table_id, starts_at, ends_at);
"""


class Problem(str, Enum):
    """Why a request cannot be booked. The bot turns each into a specific reply."""

    PARTY_TOO_LARGE = "party_too_large"
    IN_THE_PAST = "in_the_past"
    TOO_FAR_AHEAD = "too_far_ahead"
    OUTSIDE_HOURS = "outside_hours"
    FULLY_BOOKED = "fully_booked"


@dataclass(frozen=True)
class Reservation:
    code: str
    table_id: int
    guest_name: str
    phone: str
    party_size: int
    starts_at: datetime
    status: str


@dataclass(frozen=True)
class Availability:
    table_id: int | None
    problem: Problem | None = None
    alternatives: tuple[time, ...] = ()

    @property
    def ok(self) -> bool:
        return self.table_id is not None


class BookingError(RuntimeError):
    def __init__(self, problem: Problem, alternatives: tuple[time, ...] = ()) -> None:
        super().__init__(problem.value)
        self.problem = problem
        self.alternatives = alternatives


class BookingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.settings.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        conn.execute("pragma journal_mode = wal")
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.executemany("insert or ignore into tables (table_id, seats) values (?, ?)", self.settings.tables)

    def now(self) -> datetime:
        return datetime.now(self.settings.timezone).replace(tzinfo=None, second=0, microsecond=0)

    # Checks ------------------------------------------------------------------------------------

    def _problem(self, party_size: int, start: datetime) -> Problem | None:
        s = self.settings
        if party_size > s.largest_table:
            return Problem.PARTY_TOO_LARGE
        if start < self.now():
            return Problem.IN_THE_PAST
        if start.date() > self.now().date() + timedelta(days=s.booking_horizon_days):
            return Problem.TOO_FAR_AHEAD
        if not s.opens <= start.time() <= s.last_seating:
            return Problem.OUTSIDE_HOURS
        return None

    def _free_table(self, conn: sqlite3.Connection, party_size: int, start: datetime) -> int | None:
        end = start + timedelta(minutes=self.settings.seating_minutes)
        row = conn.execute(
            """
            select t.table_id from tables t
            where t.seats >= ?
              and not exists (
                  select 1 from reservations r
                  where r.table_id = t.table_id and r.status = 'confirmed'
                    and r.starts_at < ? and r.ends_at > ?
              )
            order by t.seats, t.table_id
            limit 1
            """,
            (party_size, end.isoformat(), start.isoformat()),
        ).fetchone()
        return row["table_id"] if row else None

    def _alternatives(
        self, conn: sqlite3.Connection, party_size: int, start: datetime, limit: int = 3
    ) -> tuple[time, ...]:
        """The nearest free start times the same day, every 30 minutes within opening hours."""
        s = self.settings
        day = start.date()
        slots = []
        cursor = datetime.combine(day, s.opens)
        while cursor.time() <= s.last_seating:
            if cursor != start and cursor >= self.now() and self._free_table(conn, party_size, cursor):
                slots.append(cursor)
            cursor += timedelta(minutes=30)
            if cursor.date() != day:
                break
        slots.sort(key=lambda t: abs((t - start).total_seconds()))
        return tuple(sorted(t.time() for t in slots[:limit]))

    def availability(self, party_size: int, day: date, at: time) -> Availability:
        start = datetime.combine(day, at)
        if problem := self._problem(party_size, start):
            return Availability(None, problem)
        with self._connect() as conn:
            table = self._free_table(conn, party_size, start)
            if table is None:
                return Availability(None, Problem.FULLY_BOOKED, self._alternatives(conn, party_size, start))
            return Availability(table)

    # Writes ------------------------------------------------------------------------------------

    def book(self, guest_name: str, phone: str, party_size: int, day: date, at: time) -> Reservation:
        start = datetime.combine(day, at)
        if problem := self._problem(party_size, start):
            raise BookingError(problem)
        with self._connect() as conn:
            conn.execute("begin immediate")  # take the write lock before checking, so check and insert are atomic
            try:
                table = self._free_table(conn, party_size, start)
                if table is None:
                    alternatives = self._alternatives(conn, party_size, start)
                    conn.execute("rollback")
                    raise BookingError(Problem.FULLY_BOOKED, alternatives)
                code = self._new_code(conn)
                end = start + timedelta(minutes=self.settings.seating_minutes)
                conn.execute(
                    """insert into reservations
                       (code, table_id, guest_name, phone, party_size, starts_at, ends_at, created_at)
                       values (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        code,
                        table,
                        guest_name,
                        phone,
                        party_size,
                        start.isoformat(),
                        end.isoformat(),
                        self.now().isoformat(),
                    ),
                )
                conn.execute("commit")
            except BookingError:
                raise
            except Exception:
                conn.execute("rollback")
                raise
        return Reservation(code, table, guest_name, phone, party_size, start, "confirmed")

    @staticmethod
    def _new_code(conn: sqlite3.Connection) -> str:
        while True:
            code = f"R-{secrets.randbelow(90000) + 10000}"
            if conn.execute("select 1 from reservations where code = ?", (code,)).fetchone() is None:
                return code

    def find(self, code: str, phone: str) -> Reservation | None:
        """A reservation by code, only if the phone matches (so codes alone reveal nothing)."""
        with self._connect() as conn:
            row = conn.execute("select * from reservations where code = ? and phone = ?", (code, phone)).fetchone()
        if row is None:
            return None
        return Reservation(
            row["code"],
            row["table_id"],
            row["guest_name"],
            row["phone"],
            row["party_size"],
            datetime.fromisoformat(row["starts_at"]),
            row["status"],
        )

    def cancel(self, code: str, phone: str) -> Reservation | None:
        with self._connect() as conn:
            updated = conn.execute(
                "update reservations set status = 'cancelled' where code = ? and phone = ? and status = 'confirmed'",
                (code, phone),
            ).rowcount
        return self.find(code, phone) if updated else None

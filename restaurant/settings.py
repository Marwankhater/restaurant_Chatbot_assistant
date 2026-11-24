"""Restaurant settings, read from environment variables with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo


def _time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("RESTAURANT_DB", "restaurant.db")))
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo(os.environ.get("RESTAURANT_TZ", "Africa/Cairo")))
    opens: time = field(default_factory=lambda: _time(os.environ.get("RESTAURANT_OPENS", "12:00")))
    last_seating: time = field(default_factory=lambda: _time(os.environ.get("RESTAURANT_LAST_SEATING", "22:00")))
    seating_minutes: int = field(default_factory=lambda: int(os.environ.get("RESTAURANT_SEATING_MINUTES", "120")))
    booking_horizon_days: int = field(default_factory=lambda: int(os.environ.get("RESTAURANT_HORIZON_DAYS", "60")))
    # (table number, seats). Overridable as "1:2,2:2,3:4".
    tables: tuple[tuple[int, int], ...] = field(
        default_factory=lambda: tuple(
            (int(n), int(s))
            for n, s in (
                part.split(":")
                for part in os.environ.get("RESTAURANT_TABLES", "1:2,2:2,3:4,4:4,5:4,6:6,7:8").split(",")
            )
        )
    )

    @property
    def largest_table(self) -> int:
        return max(seats for _, seats in self.tables)

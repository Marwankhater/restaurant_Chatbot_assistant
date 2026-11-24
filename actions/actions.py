"""Custom actions. They only translate between Rasa and the booking domain in `restaurant/`.

Forms collect the details; the validation actions parse each answer and ask again, with an
example, when they cannot read it. Nothing is assumed: an unreadable time is asked for again,
never replaced by a default.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, time
from pathlib import Path
from typing import Any

from rasa_sdk import Action, FormValidationAction, Tracker
from rasa_sdk.events import AllSlotsReset, EventType, FollowupAction, SlotSet
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from restaurant.booking import BookingError, BookingService, Problem
from restaurant.parsing import (
    parse_date,
    parse_name,
    parse_party_size,
    parse_phone,
    parse_reservation_code,
    parse_time,
)

log = logging.getLogger(__name__)

_service: BookingService | None = None


def service() -> BookingService:
    """One booking service per action-server process, created on first use."""
    global _service
    if _service is None:
        _service = BookingService()
    return _service


ARABIC_DAYS = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")


def say_date(day: date) -> str:
    return f"{ARABIC_DAYS[day.weekday()]} {day.day}/{day.month}"


def say_party(n: int) -> str:
    """Arabic number agreement: شخص واحد، شخصين، 3 أشخاص، 11 شخصًا."""
    if n == 1:
        return "شخص واحد"
    if n == 2:
        return "شخصين"
    return f"{n} أشخاص" if n <= 10 else f"{n} شخصًا"


def for_party(n: int) -> str:
    """'for N people' with the preposition joined the way Arabic writes it: لشخصين، لـ 3 أشخاص."""
    return "لشخص واحد" if n == 1 else "لشخصين" if n == 2 else f"لـ {say_party(n)}"


def say_time(at: time) -> str:
    hour = at.hour % 12 or 12
    period = "ظهرًا" if at.hour == 12 else "مساءً" if at.hour > 12 else "صباحًا"
    return f"{hour}:{at.minute:02d} {period}"


def slot_date(tracker: Tracker) -> date | None:
    value = tracker.get_slot("reservation_date")
    return date.fromisoformat(value) if value else None


def slot_time(tracker: Tracker) -> time | None:
    value = tracker.get_slot("reservation_time")
    return time.fromisoformat(value) if value else None


def answer_for(slot: str, value: Any, tracker: Tracker) -> tuple[str, bool]:
    """The text to parse for `slot`, and whether the guest was just asked for it.

    When the form asked for this slot, the whole message is parsed, so "3 الفجر" is read as one
    time instead of an entity extractor's partial "3". When the value came from a message about
    something else (details given up front), it is parsed as extracted, and an unreadable value
    is dropped without complaint, because the guest was not asked for it.
    """
    asked = tracker.get_slot("requested_slot") == slot
    text = tracker.latest_message.get("text") if asked else None
    return str(text if text else value), asked


# Booking -------------------------------------------------------------------------------------


class ValidateReservationForm(FormValidationAction):
    def name(self) -> str:
        return "validate_reservation_form"

    def validate_party_size(
        self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> dict[str, Any]:
        text, asked = answer_for("party_size", value, tracker)
        size = parse_party_size(text)
        if size is None:
            if asked:
                dispatcher.utter_message(response="utter_invalid_party_size")
            return {"party_size": None}
        if size > service().settings.largest_table:
            dispatcher.utter_message(response="utter_party_too_large", largest=service().settings.largest_table)
            return {"party_size": None}
        return {"party_size": float(size)}

    def validate_reservation_date(
        self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> dict[str, Any]:
        text, asked = answer_for("reservation_date", value, tracker)
        today = service().now().date()
        day = parse_date(text, today)
        if day is None:
            if asked:
                dispatcher.utter_message(response="utter_invalid_date")
            return {"reservation_date": None}
        if day < today:
            dispatcher.utter_message(response="utter_date_in_past")
            return {"reservation_date": None}
        if (day - today).days > service().settings.booking_horizon_days:
            dispatcher.utter_message(response="utter_date_too_far", days=service().settings.booking_horizon_days)
            return {"reservation_date": None}
        return {"reservation_date": day.isoformat()}

    def validate_reservation_time(
        self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> dict[str, Any]:
        text, asked = answer_for("reservation_time", value, tracker)
        s = service().settings
        at = parse_time(text, s.opens, s.last_seating)
        if at is None:
            if asked:
                dispatcher.utter_message(response="utter_invalid_time")
            return {"reservation_time": None}
        if not s.opens <= at <= s.last_seating:
            dispatcher.utter_message(
                response="utter_outside_hours", opens=say_time(s.opens), last=say_time(s.last_seating)
            )
            return {"reservation_time": None}
        return {"reservation_time": at.isoformat(timespec="minutes")}

    def validate_guest_name(
        self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> dict[str, Any]:
        text, asked = answer_for("guest_name", value, tracker)
        name = parse_name(text)
        if name is None and asked:
            dispatcher.utter_message(response="utter_invalid_name")
        return {"guest_name": name}

    def validate_phone(
        self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> dict[str, Any]:
        text, asked = answer_for("phone", value, tracker)
        phone = parse_phone(text)
        if phone is None and asked:
            dispatcher.utter_message(response="utter_invalid_phone")
        return {"phone": phone}


class ActionCheckAvailability(Action):
    """After the form: book-able as asked, or explain why not and ask again for what has to change."""

    def name(self) -> str:
        return "action_check_availability"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> list[EventType]:
        party, day, at = int(tracker.get_slot("party_size")), slot_date(tracker), slot_time(tracker)
        result = service().availability(party, day, at)
        if result.ok:
            dispatcher.utter_message(
                response="utter_confirm_booking",
                party=for_party(party),
                day=say_date(day),
                at=say_time(at),
                name=tracker.get_slot("guest_name"),
            )
            return [SlotSet("awaiting_confirmation", True)]
        return reject(dispatcher, result.problem, result.alternatives)


def reject(
    dispatcher: CollectingDispatcher, problem: Problem | None, alternatives: tuple[time, ...]
) -> list[EventType]:
    """Tell the guest what is wrong, clear only the slot that must change, and reopen the form."""
    if problem is Problem.FULLY_BOOKED:
        if alternatives:
            dispatcher.utter_message(
                response="utter_fully_booked_alternatives", options="، ".join(say_time(t) for t in alternatives)
            )
        else:
            dispatcher.utter_message(response="utter_fully_booked_day")
            return [
                SlotSet("reservation_date", None),
                SlotSet("reservation_time", None),
                SlotSet("awaiting_confirmation", False),
                FollowupAction("reservation_form"),
            ]
        return [
            SlotSet("reservation_time", None),
            SlotSet("awaiting_confirmation", False),
            FollowupAction("reservation_form"),
        ]
    if problem is Problem.IN_THE_PAST:
        dispatcher.utter_message(response="utter_time_passed")
        return [
            SlotSet("reservation_time", None),
            SlotSet("awaiting_confirmation", False),
            FollowupAction("reservation_form"),
        ]
    dispatcher.utter_message(response="utter_cannot_book")
    return [AllSlotsReset()]


class ActionCreateReservation(Action):
    def name(self) -> str:
        return "action_create_reservation"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> list[EventType]:
        party, day, at = int(tracker.get_slot("party_size")), slot_date(tracker), slot_time(tracker)
        try:
            booking = service().book(tracker.get_slot("guest_name"), tracker.get_slot("phone"), party, day, at)
        except BookingError as exc:
            # Someone took the last table between the confirmation question and the guest's "yes".
            return reject(dispatcher, exc.problem, exc.alternatives)
        log.info("reservation created", extra={"code": booking.code, "table": booking.table_id})
        dispatcher.utter_message(
            response="utter_booking_confirmed",
            code=booking.code,
            party=for_party(party),
            day=say_date(day),
            at=say_time(at),
        )
        return [AllSlotsReset()]


class ActionDiscardDraft(Action):
    def name(self) -> str:
        return "action_discard_draft"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> list[EventType]:
        dispatcher.utter_message(response="utter_booking_not_made")
        return [AllSlotsReset()]


# Looking up and cancelling -------------------------------------------------------------------


class ValidateLookupForm(FormValidationAction):
    def name(self) -> str:
        return "validate_lookup_form"

    def validate_reservation_code(
        self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> dict[str, Any]:
        text, asked = answer_for("reservation_code", value, tracker)
        code = parse_reservation_code(text)
        if code is None and asked:
            dispatcher.utter_message(response="utter_invalid_code")
        return {"reservation_code": code}

    def validate_phone(
        self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> dict[str, Any]:
        text, asked = answer_for("phone", value, tracker)
        phone = parse_phone(text)
        if phone is None and asked:
            dispatcher.utter_message(response="utter_invalid_phone")
        return {"phone": phone}


class ActionLookupReservation(Action):
    def name(self) -> str:
        return "action_lookup_reservation"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> list[EventType]:
        found = service().find(tracker.get_slot("reservation_code"), tracker.get_slot("phone"))
        if found is None:
            dispatcher.utter_message(response="utter_reservation_not_found")
        elif tracker.get_slot("lookup_purpose") == "cancel":
            cancelled = service().cancel(found.code, found.phone)
            dispatcher.utter_message(
                response="utter_reservation_cancelled" if cancelled else "utter_reservation_already_cancelled",
                code=found.code,
            )
        else:
            dispatcher.utter_message(
                response="utter_reservation_details",
                code=found.code,
                party=say_party(found.party_size),
                day=say_date(found.starts_at.date()),
                at=say_time(found.starts_at.time()),
                status="مؤكد" if found.status == "confirmed" else "ملغى",
            )
        return [AllSlotsReset()]


class ActionOpeningHours(Action):
    def name(self) -> str:
        return "action_opening_hours"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> list[EventType]:
        s = service().settings
        dispatcher.utter_message(response="utter_opening_hours", opens=say_time(s.opens), last=say_time(s.last_seating))
        return []

"""The custom actions, driven with real rasa_sdk trackers against a temporary database."""

from datetime import time

import pytest
from rasa_sdk import Tracker
from rasa_sdk.events import AllSlotsReset, FollowupAction, SlotSet
from rasa_sdk.executor import CollectingDispatcher

import actions.actions as acts
from restaurant.booking import BookingService

from .conftest import NOW


@pytest.fixture(autouse=True)
def booking(service: BookingService, monkeypatch: pytest.MonkeyPatch) -> BookingService:
    monkeypatch.setattr(acts, "_service", service)
    return service


def tracker(text: str = "", **slots) -> Tracker:
    return Tracker("guest", slots, {"text": text}, [], False, None, {"name": "reservation_form"}, "action_listen")


def responses(dispatcher: CollectingDispatcher) -> list[str]:
    return [m.get("response") for m in dispatcher.messages]


@pytest.mark.parametrize(
    ("method", "text", "expected", "reply"),
    [
        ("validate_party_size", "احنا تلاتة", {"party_size": 3.0}, None),
        ("validate_reservation_date", "امبارح", {"reservation_date": None}, "utter_date_in_past"),
        ("validate_party_size", "كتير", {"party_size": None}, "utter_invalid_party_size"),
        ("validate_party_size", "20", {"party_size": None}, "utter_party_too_large"),
        ("validate_reservation_date", "بكرة", {"reservation_date": "2026-03-12"}, None),
        ("validate_reservation_date", "1/1/2026", {"reservation_date": None}, "utter_date_in_past"),
        ("validate_reservation_date", "قريب", {"reservation_date": None}, "utter_invalid_date"),
        ("validate_reservation_time", "8 ونص", {"reservation_time": "20:30"}, None),
        ("validate_reservation_time", "3 الفجر", {"reservation_time": None}, "utter_outside_hours"),
        ("validate_guest_name", "اسمي سارة", {"guest_name": "سارة"}, None),
        ("validate_phone", "٠١٠١٢٣٤٥٦٧٨", {"phone": "+201012345678"}, None),
        ("validate_phone", "123", {"phone": None}, "utter_invalid_phone"),
    ],
)
def test_form_validation(method: str, text: str, expected: dict, reply: str | None) -> None:
    dispatcher = CollectingDispatcher()
    asked = tracker(text, requested_slot=method.removeprefix("validate_"))
    result = getattr(acts.ValidateReservationForm(), method)(text, dispatcher, asked, {})
    assert result == expected
    assert responses(dispatcher) == ([reply] if reply else [])


def test_whole_answer_is_parsed_when_asked_and_extras_are_dropped_quietly() -> None:
    form = acts.ValidateReservationForm()
    dispatcher = CollectingDispatcher()
    # The entity extractor saw only "3"; the guest wrote "3 الفجر" when asked for the time.
    asked = tracker("3 الفجر", requested_slot="reservation_time")
    assert form.validate_reservation_time("3", dispatcher, asked, {}) == {"reservation_time": None}
    assert responses(dispatcher) == ["utter_outside_hours"]
    # A stray "4" picked up as a phone while the form asked for the party size: dropped, no message.
    dispatcher = CollectingDispatcher()
    other = tracker("4", requested_slot="party_size")
    assert form.validate_phone("4", dispatcher, other, {}) == {"phone": None}
    assert responses(dispatcher) == []


FRIDAY_8PM = {
    "party_size": 2.0,
    "reservation_date": "2026-03-13",
    "reservation_time": "20:00",
    "guest_name": "Sara",
    "phone": "+201012345678",
}


def test_check_then_create(booking: BookingService) -> None:
    dispatcher = CollectingDispatcher()
    events = acts.ActionCheckAvailability().run(dispatcher, tracker(**FRIDAY_8PM), {})
    assert events == [SlotSet("awaiting_confirmation", True)]
    assert dispatcher.messages[0]["party"] == "لشخصين"

    dispatcher = CollectingDispatcher()
    events = acts.ActionCreateReservation().run(dispatcher, tracker(**FRIDAY_8PM), {})
    assert events == [AllSlotsReset()]
    code = dispatcher.messages[0]["code"]
    assert booking.find(code, "+201012345678") is not None


def test_taken_between_question_and_yes_offers_other_times(booking: BookingService) -> None:
    for name in ("a", "b", "c"):  # fill every table at 20:00
        booking.book(name, "+201000000000", 2, NOW.date().replace(day=13), time(20))
    dispatcher = CollectingDispatcher()
    events = acts.ActionCreateReservation().run(dispatcher, tracker(**FRIDAY_8PM), {})
    assert responses(dispatcher) == ["utter_fully_booked_alternatives"]
    assert SlotSet("reservation_time", None) in events and FollowupAction("reservation_form") in events


def test_cancel_needs_code_and_phone(booking: BookingService) -> None:
    made = booking.book("Sara", "+201012345678", 2, NOW.date().replace(day=13), time(20))
    dispatcher = CollectingDispatcher()
    acts.ActionLookupReservation().run(
        dispatcher, tracker(reservation_code=made.code, phone="+201099999999", lookup_purpose="cancel"), {}
    )
    assert responses(dispatcher) == ["utter_reservation_not_found"]
    dispatcher = CollectingDispatcher()
    acts.ActionLookupReservation().run(
        dispatcher, tracker(reservation_code=made.code, phone="+201012345678", lookup_purpose="cancel"), {}
    )
    assert responses(dispatcher) == ["utter_reservation_cancelled"]
    assert booking.find(made.code, "+201012345678").status == "cancelled"

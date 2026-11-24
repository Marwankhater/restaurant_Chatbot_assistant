import threading
from datetime import date, time

import pytest

from restaurant.booking import BookingError, BookingService, Problem

FRIDAY = date(2026, 3, 13)
PHONE = "+201012345678"


def test_smallest_fitting_table_is_used(service: BookingService) -> None:
    assert service.availability(2, FRIDAY, time(20)).table_id == 1
    assert service.availability(3, FRIDAY, time(20)).table_id == 2


def test_overlapping_seatings_cannot_share_a_table(service: BookingService) -> None:
    first = service.book("Sara", PHONE, 2, FRIDAY, time(20))
    # 21:00 overlaps the 20:00 to 22:00 seating on table 1, so the next table up is used.
    second = service.book("Omar", PHONE, 2, FRIDAY, time(21))
    assert first.table_id == 1 and second.table_id == 2
    # 22:00 starts exactly when the first seating ends: table 1 is free again.
    assert service.availability(2, FRIDAY, time(22)).table_id == 1


def test_fully_booked_offers_the_nearest_free_times(service: BookingService) -> None:
    service.book("A", PHONE, 8, FRIDAY, time(20))
    with pytest.raises(BookingError) as caught:
        service.book("B", PHONE, 6, FRIDAY, time(20, 30))
    assert caught.value.problem is Problem.FULLY_BOOKED
    assert caught.value.alternatives  # earlier or later the same evening
    assert all(t <= time(18) or t >= time(22) for t in caught.value.alternatives)


@pytest.mark.parametrize(
    ("party", "day", "at", "problem"),
    [
        (9, FRIDAY, time(20), Problem.PARTY_TOO_LARGE),
        (2, date(2026, 3, 10), time(20), Problem.IN_THE_PAST),
        (2, date(2026, 3, 11), time(9, 30), Problem.IN_THE_PAST),
        (2, date(2026, 9, 1), time(20), Problem.TOO_FAR_AHEAD),
        (2, FRIDAY, time(23), Problem.OUTSIDE_HOURS),
        (2, FRIDAY, time(11), Problem.OUTSIDE_HOURS),
    ],
)
def test_requests_that_cannot_be_booked(service: BookingService, party, day, at, problem) -> None:
    assert service.availability(party, day, at).problem is problem
    with pytest.raises(BookingError):
        service.book("X", PHONE, party, day, at)


def test_concurrent_requests_for_the_last_table_book_it_once(service: BookingService) -> None:
    results: list[str] = []
    barrier = threading.Barrier(8)

    def attempt(i: int) -> None:
        barrier.wait()
        try:
            service.book(f"guest {i}", PHONE, 8, FRIDAY, time(19))
            results.append("booked")
        except BookingError as exc:
            results.append(exc.problem.value)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("booked") == 1
    assert results.count("fully_booked") == 7


def test_codes_are_unguessable_and_cancel_needs_the_phone(service: BookingService) -> None:
    booking = service.book("Sara", PHONE, 2, FRIDAY, time(20))
    assert booking.code.startswith("R-") and len(booking.code) == 7
    assert service.find(booking.code, "+201199999999") is None
    assert service.cancel(booking.code, "+201199999999") is None
    cancelled = service.cancel(booking.code, PHONE)
    assert cancelled is not None and cancelled.status == "cancelled"
    assert service.cancel(booking.code, PHONE) is None  # already cancelled
    # The table is free again.
    assert service.availability(2, FRIDAY, time(20)).table_id == 1

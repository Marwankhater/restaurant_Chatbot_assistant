from datetime import date, time

import pytest

from restaurant.parsing import (
    normalize,
    parse_date,
    parse_name,
    parse_party_size,
    parse_phone,
    parse_reservation_code,
    parse_time,
)

WEDNESDAY = date(2026, 3, 11)


def test_normalize_digits_and_letters() -> None:
    assert normalize("٢٥/١٢") == "25/12"
    assert normalize("أربعة") == "اربعه"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4", 4),
        ("٤ أشخاص", 4),
        ("أربعة", 4),
        ("احنا تلاتة", 3),
        ("لشخصين", 2),
        ("table for two", 2),
        ("5 people", 5),
        ("ستة", 6),
        ("عشرة أفراد", 10),
        ("", None),
        ("مش عارف", None),
        ("0", None),
    ],
)
def test_party_size(text: str, expected: int | None) -> None:
    assert parse_party_size(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("اليوم", WEDNESDAY),
        ("النهارده", WEDNESDAY),
        ("tonight", WEDNESDAY),
        ("بكرة", date(2026, 3, 12)),
        ("غداً", date(2026, 3, 12)),
        ("tomorrow", date(2026, 3, 12)),
        ("بعد بكرة", date(2026, 3, 13)),
        ("بعد غد", date(2026, 3, 13)),
        ("الخميس", date(2026, 3, 12)),
        ("الجمعة", date(2026, 3, 13)),
        ("السبت", date(2026, 3, 14)),
        ("الأربعاء", WEDNESDAY),
        ("الأربعاء الجاي", date(2026, 3, 18)),
        ("next friday", date(2026, 3, 13)),
        ("25/3", date(2026, 3, 25)),
        ("٢٥/٣", date(2026, 3, 25)),
        ("1/2", date(2027, 2, 1)),
        ("2026-04-02", date(2026, 4, 2)),
        ("15 أبريل", date(2026, 4, 15)),
        ("April 15", date(2026, 4, 15)),
        ("31/2", None),
        ("قريب", None),
        ("", None),
    ],
)
def test_dates(text: str, expected: date | None) -> None:
    assert parse_date(text, WEDNESDAY) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8 مساءً", time(20)),
        ("٨ مساء", time(20)),
        ("9 بالليل", time(21)),
        ("8 م", time(20)),
        ("8", time(20)),
        ("2", time(14)),
        ("12", time(12)),
        ("8:30", time(20, 30)),
        ("8.30", time(20, 30)),
        ("8 ونص", time(20, 30)),
        ("9 وربع", time(21, 15)),
        ("9 الا ربع", time(20, 45)),
        ("20:00", time(20)),
        ("8pm", time(20)),
        ("8:30 pm", time(20, 30)),
        ("11 الصبح", time(11)),
        ("الساعة تمانية", time(20)),
        ("25:00", None),
        ("بعدين", None),
    ],
)
def test_times(text: str, expected: time | None) -> None:
    assert parse_time(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01012345678", "+201012345678"),
        ("٠١٠١٢٣٤٥٦٧٨", "+201012345678"),
        ("+20 101 234 5678", "+201012345678"),
        ("00201112345678", "+201112345678"),
        ("1512345678", "+201512345678"),
        ("0101234567", None),
        ("01312345678", None),
        ("abc", None),
    ],
)
def test_phones(text: str, expected: str | None) -> None:
    assert parse_phone(text) == expected


def test_names_and_codes() -> None:
    assert parse_name("اسمي محمد علي") == "محمد علي"
    assert parse_name("my name is Sara") == "Sara"
    assert parse_name("1234") is None
    assert parse_reservation_code("رقم الحجز R-48213") == "R-48213"
    assert parse_reservation_code("r48213") == "R-48213"
    assert parse_reservation_code("٤٨٢١٣") == "R-48213"
    assert parse_reservation_code("مش فاكر") is None


def test_dawn_is_morning_and_large_numbers_are_read() -> None:
    assert parse_time("3 الفجر") == time(3)
    assert parse_party_size("عشرين") == 20

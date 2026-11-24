"""Turn what a guest types (Arabic, Egyptian Arabic or English) into numbers, dates, times and phones.

Every function returns None when it cannot read the value with confidence. The bot then asks
again with an example instead of guessing.
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize(text: str | None) -> str:
    """Western digits, one spelling per Arabic letter, no diacritics or tatweel, single spaces."""
    text = (text or "").translate(_DIGITS).lower()
    text = re.sub(r"[ً-ْـ]", "", text)
    for old, new in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        text = text.replace(old, new)
    return " ".join(text.split())


NUMBER_WORDS = {
    1: ("واحد", "واحده", "شخص", "فرد", "one", "single", "لوحدي"),
    2: ("اتنين", "اثنين", "اثنان", "شخصين", "فردين", "اتنان", "two", "couple"),
    3: ("تلاته", "ثلاثه", "ثلاث", "تلات", "three"),
    4: ("اربعه", "اربع", "four"),
    5: ("خمسه", "خمس", "five"),
    6: ("سته", "ست", "six"),
    7: ("سبعه", "سبع", "seven"),
    8: ("تمانيه", "ثمانيه", "تمان", "ثماني", "eight"),
    9: ("تسعه", "تسع", "nine"),
    10: ("عشره", "عشر", "ten"),
    11: ("حداشر", "احدعشر", "eleven"),
    12: ("اتناشر", "اثناعشر", "twelve"),
    15: ("خمستاشر", "خمسةعشر", "fifteen"),
    20: ("عشرين", "عشرون", "twenty"),
    30: ("تلاتين", "ثلاثين", "ثلاثون", "thirty"),
}
_WORD_TO_NUMBER = {normalize(w): n for n, words in NUMBER_WORDS.items() for w in words}


def parse_party_size(text: str | None) -> int | None:
    """'4', '٤', 'أربعة', 'احنا تلاتة', 'table for two' -> int."""
    value = normalize(text)
    if match := re.search(r"\b(\d{1,3})\b", value):
        number = int(match.group(1))
        return number if number > 0 else None
    for token in re.findall(r"[\w]+", value):
        for candidate in (token, token.removeprefix("ل"), token.removeprefix("و")):
            if candidate in _WORD_TO_NUMBER:
                return _WORD_TO_NUMBER[candidate]
    return None


WEEKDAYS = {
    0: ("الاثنين", "الاتنين", "اثنين", "اتنين", "monday", "mon"),
    1: ("الثلاثاء", "التلات", "الثلاث", "تلات", "tuesday", "tue"),
    2: ("الاربعاء", "الاربع", "اربعاء", "wednesday", "wed"),
    3: ("الخميس", "خميس", "thursday", "thu"),
    4: ("الجمعه", "جمعه", "friday", "fri"),
    5: ("السبت", "سبت", "saturday", "sat"),
    6: ("الاحد", "الحد", "احد", "sunday", "sun"),
}
MONTHS = {
    1: ("يناير", "كانون الثاني", "january", "jan"),
    2: ("فبراير", "شباط", "february", "feb"),
    3: ("مارس", "اذار", "march", "mar"),
    4: ("ابريل", "نيسان", "april", "apr"),
    5: ("مايو", "ايار", "may"),
    6: ("يونيو", "حزيران", "june", "jun"),
    7: ("يوليو", "تموز", "july", "jul"),
    8: ("اغسطس", "اب", "august", "aug"),
    9: ("سبتمبر", "ايلول", "september", "sep", "sept"),
    10: ("اكتوبر", "تشرين الاول", "october", "oct"),
    11: ("نوفمبر", "تشرين الثاني", "november", "nov"),
    12: ("ديسمبر", "كانون الاول", "december", "dec"),
}
_RELATIVE = (
    (-1, ("امبارح", "امس", "البارحه", "yesterday")),
    (2, ("بعد بكره", "بعد بكرا", "بعد غد", "بعد الغد", "day after tomorrow")),
    (1, ("بكره", "بكرا", "غدا", "الغد", "tomorrow")),
    (0, ("النهارده", "النهارد", "النهاردا", "اليوم", "الليله", "today", "tonight")),
)


def _future_year(day: int, month: int, today: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def parse_date(text: str | None, today: date) -> date | None:
    """Relative days, weekday names (the next one, today included), '25/12', '2026-12-25', '25 ديسمبر'."""
    value = normalize(text)
    if not value:
        return None
    for offset, words in _RELATIVE:
        if any(normalize(w) in value for w in words):
            return today + timedelta(days=offset)
    if match := re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", value):
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    if match := re.search(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", value):
        day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
        if year:
            try:
                return date(int(year) + (2000 if len(year) == 2 else 0), month, day)
            except ValueError:
                return None
        return _future_year(day, month, today)
    for month, names in MONTHS.items():
        for name in names:
            pattern = rf"\b(\d{{1,2}})\s*{re.escape(normalize(name))}\b|\b{re.escape(normalize(name))}\s*(\d{{1,2}})\b"
            if match := re.search(pattern, value):
                return _future_year(int(match.group(1) or match.group(2)), month, today)
    next_week = any(w in value for w in ("الجاي", "القادم", "المقبل", "next"))
    for weekday, names in WEEKDAYS.items():
        if any(re.search(rf"(^|\s){re.escape(normalize(n))}($|\s)", value) for n in names):
            ahead = (weekday - today.weekday()) % 7
            if next_week and ahead == 0:
                ahead = 7
            return today + timedelta(days=ahead)
    return None


_PM = (
    "مساء",
    "مساءا",
    "م",
    "بالليل",
    "بليل",
    "الليل",
    "ليلا",
    "بعد الضهر",
    "بعد الظهر",
    "العصر",
    "pm",
    "p.m",
    "evening",
    "tonight",
)
_AM = ("صباحا", "صباح", "الصبح", "ص", "الفجر", "فجرا", "فجر", "am", "a.m", "morning")


def parse_time(text: str | None, opens: time = time(12), last_seating: time = time(22)) -> time | None:
    """'8', '8:30', '٨ مساءً', '9 بالليل', '8 ونص', '9 الا ربع', '20:00', '8pm'.

    A bare hour is read as the one inside opening hours, so '8' means 20:00 at a dinner restaurant.
    """
    value = normalize(text)
    if not value:
        return None
    match = re.search(r"\b(\d{1,2})(?:\s*[:.]\s*(\d{2}))?\s*(am|pm|a\.m|p\.m)?\b", value)
    if not match:
        for word, number in _WORD_TO_NUMBER.items():
            if re.search(rf"(^|\s|ال){re.escape(word)}($|\s)", value) and number <= 12:
                match = re.match(r"(\d+)", str(number))
                break
        if not match:
            return None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.lastindex and match.lastindex >= 2 and match.group(2) else 0
    if "الا ربع" in value or "quarter to" in value:
        hour, minute = hour - 1, 45
    elif "ونص" in value or "و نص" in value or "والنصف" in value or "half past" in value:
        minute = 30
    elif "وربع" in value or "و ربع" in value or "quarter past" in value:
        minute = 15
    if hour > 23 or minute > 59 or hour < 0:
        return None
    words = set(re.findall(r"[\w.]+", value))
    suffix = match.group(3) if match.re.groups >= 3 else None
    pm = bool(suffix and suffix.startswith("p")) or any((w in words) if " " not in w else (w in value) for w in _PM)
    am = bool(suffix and suffix.startswith("a")) or any((w in words) if " " not in w else (w in value) for w in _AM)
    if hour <= 12:
        if pm and hour < 12:
            hour += 12
        elif am and hour == 12:
            hour = 0
        elif not am and not pm:
            # No marker: prefer the reading that falls inside opening hours.
            candidates = [hour, hour + 12] if hour < 12 else [hour]
            inside = [h for h in candidates if opens <= time(h % 24, minute) <= last_seating]
            hour = inside[0] if inside else candidates[-1] % 24
    return time(hour, minute)


def parse_phone(text: str | None) -> str | None:
    """Egyptian mobile numbers in any common form -> '+201XXXXXXXXX'."""
    digits = re.sub(r"\D", "", normalize(text))
    if digits.startswith("0020"):
        digits = digits[4:]
    elif digits.startswith("20") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("1") and len(digits) == 10:
        digits = "0" + digits
    if re.fullmatch(r"01[0125]\d{8}", digits):
        return "+20" + digits[1:]
    return None


def parse_name(text: str | None) -> str | None:
    """A guest name: letters only, two to forty characters, common lead-ins removed."""
    value = " ".join((text or "").split())
    value = re.sub(
        r"^(اسمي|انا|أنا|الاسم|باسم|بإسم|على اسم|علي اسم|my name is|name is|i am|i'm|it's)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    if not 2 <= len(value) <= 40 or re.search(r"[\d@#/\\]", value):
        return None
    return value.strip(" .،,")


_CODE = re.compile(r"\b([A-Za-z]{1,2}-?\d{4,6}|\d{4,6})\b")


def parse_reservation_code(text: str | None) -> str | None:
    """'R-48213', 'r48213' or '48213' -> 'R-48213'."""
    match = _CODE.search(normalize(text))
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return f"R-{digits}"

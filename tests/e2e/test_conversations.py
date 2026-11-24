"""Whole conversations against a running bot and action server (REST channel).

Skipped unless RASA_URL is set, for example:
    rasa run actions & rasa run --credentials channels.yml --enable-api &
    RASA_URL=http://localhost:5005 pytest tests/e2e
"""

from __future__ import annotations

import json
import os
import urllib.request
import uuid

import pytest

RASA_URL = os.environ.get("RASA_URL")
pytestmark = pytest.mark.skipif(not RASA_URL, reason="set RASA_URL to run end-to-end conversations")


def say(sender: str, text: str) -> str:
    request = urllib.request.Request(
        f"{RASA_URL}/webhooks/rest/webhook",
        json.dumps({"sender": sender, "message": text}).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return "\n".join(m.get("text", "") for m in json.loads(response.read()))


def conversation(*turns: str) -> list[str]:
    sender = uuid.uuid4().hex
    return [say(sender, turn) for turn in turns]


def test_booking_in_egyptian_arabic_then_cancel() -> None:
    replies = conversation(
        "عايز أحجز ترابيزة", "احنا تلاتة", "بكرة", "الساعة تمانية ونص", "اسمي سارة", "01012345678", "أيوه"
    )
    assert "لكم شخص" in replies[0]
    assert "3 أشخاص" in replies[5] and "8:30 مساءً" in replies[5] and "سارة" in replies[5]
    assert "تم تأكيد حجزك" in replies[6]
    code = next(word.strip("،.") for word in replies[6].split() if word.startswith("R-"))

    cancel = conversation("عايز ألغي الحجز", code, "01099999999")
    assert "لم أجد حجزًا" in cancel[2]  # wrong phone: nothing revealed
    cancel = conversation("عايز ألغي الحجز", code, "01012345678")
    assert f"تم إلغاء الحجز {code}" in cancel[2]


def test_everything_in_one_message() -> None:
    replies = conversation("احجزلي ترابيزة لاتنين بكرة 9 بالليل", "منى", "01212345678", "لا")
    assert "رقم موبايلك" in replies[1]
    assert "لشخصين" in replies[2] and "9:00 مساءً" in replies[2]
    assert "لم أحجز شيئًا" in replies[3]


def test_unreadable_answers_are_asked_again() -> None:
    replies = conversation("عايز أحجز", "كتير", "4", "امبارح", "بكرة", "3 الفجر")
    assert "لم أفهم العدد" in replies[1]
    assert "هذا التاريخ مضى" in replies[3] or "لم أفهم التاريخ" in replies[3]
    assert "نستقبل الحجوزات من" in replies[5]


def test_party_larger_than_any_table() -> None:
    replies = conversation("عايز أحجز", "عشرين")
    assert "أكبر طاولة" in replies[1]


def test_opening_hours_in_the_middle_of_a_booking() -> None:
    replies = conversation("عايز أحجز", "4", "الجمعة", "مواعيدكم إيه", "8 ونص")
    assert "نستقبل الحجوزات يوميًا" in replies[3] and "في أي ساعة" in replies[3]
    assert "ما الاسم" in replies[4]

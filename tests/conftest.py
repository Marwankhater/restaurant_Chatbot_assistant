from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from restaurant.booking import BookingService
from restaurant.settings import Settings

# A fixed "now": Wednesday 2026-03-11, 10:00 in the restaurant's time zone.
NOW = datetime(2026, 3, 11, 10, 0)


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BookingService:
    settings = Settings(db_path=tmp_path / "test.db", tables=((1, 2), (2, 4), (3, 8)))
    svc = BookingService(settings)
    monkeypatch.setattr(svc, "now", lambda: NOW)
    return svc

"""Tests for per-user timezone handling.

The pure-function tests need no services. The set_timezone handler rejection
paths also avoid the DB (they return before any persistence), so they run
without MySQL.
"""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from nunzio.core import MessageHandler
from nunzio.database.models import DEFAULT_TZ, now_in_tz


def test_now_in_tz_is_naive():
    assert now_in_tz("Asia/Tokyo").tzinfo is None


def test_now_in_tz_matches_reference():
    ref = datetime.now(ZoneInfo("Asia/Tokyo")).replace(tzinfo=None)
    got = now_in_tz("Asia/Tokyo")
    assert abs((got - ref).total_seconds()) < 5


def test_now_in_tz_invalid_falls_back_to_default():
    got = now_in_tz("Not/ARealZone")
    ref = datetime.now(ZoneInfo(DEFAULT_TZ)).replace(tzinfo=None)
    assert abs((got - ref).total_seconds()) < 5


def test_compute_consistency_uses_supplied_today():
    today = date(2026, 5, 30)
    dates = [date(2026, 5, 28), date(2026, 5, 29), date(2026, 5, 30)]
    stats = MessageHandler._compute_consistency(dates, dates, today)
    assert stats["streak"] == 3
    assert stats["days_since_last"] == 0
    assert stats["count_30d"] == 3
    assert stats["count_90d"] == 3


def test_compute_consistency_streak_breaks_on_gap():
    today = date(2026, 5, 30)
    # worked out today and yesterday, then a gap
    dates = [date(2026, 5, 25), date(2026, 5, 29), date(2026, 5, 30)]
    stats = MessageHandler._compute_consistency(dates, dates, today)
    assert stats["streak"] == 2


async def test_set_timezone_requires_a_zone():
    handler = MessageHandler(verbose=False)
    intent = SimpleNamespace(intent="set_timezone", mentioned_timezone=None)
    resp = await handler._handle_set_timezone(intent, user_id=0)
    assert "which timezone" in resp.lower()


async def test_set_timezone_rejects_unknown_zone():
    handler = MessageHandler(verbose=False)
    intent = SimpleNamespace(intent="set_timezone", mentioned_timezone="Mars/Olympus")
    resp = await handler._handle_set_timezone(intent, user_id=0)
    assert "don't recognize" in resp.lower()

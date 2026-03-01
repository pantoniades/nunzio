"""Tests for body weight tracking."""

import re

import pytest

from nunzio.core import MessageHandler


@pytest.fixture
async def handler():
    h = MessageHandler(verbose=True)
    await h.initialize()
    yield h
    await h.close()


TEST_USER = 66600


@pytest.mark.asyncio
async def test_log_weight(handler: MessageHandler):
    """Log a body weight reading and verify response."""
    response = await handler.process("weighed 185 lbs", user_id=TEST_USER)
    assert "Logged" in response
    assert "185" in response


@pytest.mark.asyncio
async def test_log_weight_with_date(handler: MessageHandler):
    """Log weight with a relative date."""
    response = await handler.process("weighed 183 lbs yesterday", user_id=TEST_USER)
    assert "Logged" in response
    assert "183" in response


@pytest.mark.asyncio
async def test_log_weight_shows_delta(handler: MessageHandler):
    """Second weigh-in should show delta from previous."""
    # First reading
    await handler.process("weighed 190 lbs", user_id=TEST_USER + 1)
    # Second reading
    response = await handler.process("weighed 188 lbs", user_id=TEST_USER + 1)
    assert "Logged" in response
    # Should show a delta (↓ 2 lbs)
    assert "\u2193" in response or "\u2191" in response


@pytest.mark.asyncio
async def test_weight_trend(handler: MessageHandler):
    """View weight trend after logging entries."""
    uid = TEST_USER + 2
    await handler.process("weighed 192 lbs", user_id=uid)
    await handler.process("weighed 190 lbs", user_id=uid)

    response = await handler.process("what's my weight trend", user_id=uid)
    assert "Body Weight" in response or "weight" in response.lower()
    assert "190" in response

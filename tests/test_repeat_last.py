"""Tests for repeat-last-workout functionality."""

import pytest

from nunzio.core import MessageHandler


@pytest.fixture
async def handler():
    h = MessageHandler(verbose=True)
    await h.initialize()
    yield h
    await h.close()


@pytest.mark.asyncio
async def test_repeat_no_history(handler: MessageHandler):
    """Repeating with no prior workouts gives a friendly message."""
    response = await handler.process("again", user_id=66666)
    assert "Nothing to repeat" in response


@pytest.mark.asyncio
async def test_repeat_last_session(handler: MessageHandler):
    """Log a workout, repeat it, verify the new session matches."""
    # Log original
    response = await handler.process("did 2 sets of bench press 10 reps at 135 lbs", user_id=55555)
    assert "Logged" in response

    # Repeat
    response = await handler.process("repeat last", user_id=55555)
    assert "Repeated session" in response or "Repeated last" in response
    # Should mention bench press
    assert "Bench Press" in response or "bench press" in response.lower()

    # Clean up both sessions
    await handler.process("undo", user_id=55555)
    await handler.process("undo", user_id=55555)

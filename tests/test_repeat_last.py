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
async def test_repeat_last_workout(handler: MessageHandler):
    """Log a workout, repeat it, verify the new workout matches."""
    # Log original
    response = await handler.process("did 2 sets of bench press 10 reps at 135 lbs", user_id=55555)
    assert "Logged" in response

    # Repeat
    response = await handler.process("repeat last", user_id=55555)
    assert "Repeated #" in response
    # Should mention bench press
    assert "Bench Press" in response or "bench press" in response.lower()

    # Clean up both workouts
    await handler.process("undo", user_id=55555)
    await handler.process("undo", user_id=55555)


@pytest.mark.asyncio
async def test_repeat_with_weight_override(handler: MessageHandler):
    """'Again at 40 lbs' should repeat with the new weight."""
    response = await handler.process("did 1 set of lateral raise 10 reps at 30 lbs", user_id=55557)
    assert "Logged" in response

    response = await handler.process("again at 40 lbs", user_id=55557)
    assert "Repeated" in response
    assert "40" in response
    # Should NOT still show 30
    assert "30" not in response

    await handler.process("undo", user_id=55557)
    await handler.process("undo", user_id=55557)


@pytest.mark.asyncio
async def test_repeat_twice(handler: MessageHandler):
    """'Again twice' should create two new batches."""
    response = await handler.process("did 1 set of squat 5 reps at 225 lbs", user_id=55558)
    assert "Logged" in response

    response = await handler.process("again twice", user_id=55558)
    assert "Repeated" in response
    assert "x2" in response
    # Should have two copies of the set
    assert response.count("225") == 2

    await handler.process("undo", user_id=55558)
    await handler.process("undo", user_id=55558)
    await handler.process("undo", user_id=55558)

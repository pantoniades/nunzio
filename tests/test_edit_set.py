"""Tests for edit-set functionality."""

import re

import pytest

from nunzio.core import MessageHandler


@pytest.fixture
async def handler():
    h = MessageHandler(verbose=True)
    await h.initialize()
    yield h
    await h.close()


def _extract_batch_id(response: str) -> int:
    match = re.search(r"#(\d+)", response)
    assert match, f"Couldn't find batch ID in: {response}"
    return int(match.group(1))


@pytest.mark.asyncio
async def test_edit_last_set_reps(handler: MessageHandler):
    """Log a workout, then edit the reps on the last set."""
    response = await handler.process("did 1 set of bench press 10 reps at 135 lbs", user_id=60001)
    assert "Logged" in response
    batch_id = _extract_batch_id(response)

    response = await handler.process("change last set to 12 reps", user_id=60001)
    assert "Edited" in response
    assert str(batch_id) in response
    assert "12" in response

    # Clean up
    await handler.process(f"delete #{batch_id}", user_id=60001)


@pytest.mark.asyncio
async def test_edit_by_exercise_name(handler: MessageHandler):
    """Edit sets by exercise name — should target most recent batch for that exercise."""
    response = await handler.process("did 2 sets of squat 5 reps at 225 lbs", user_id=60002)
    assert "Logged" in response
    batch_id = _extract_batch_id(response)

    response = await handler.process("change squat to 8 reps", user_id=60002)
    assert "Edited" in response
    assert "2 sets" in response
    assert "8" in response

    # Clean up
    await handler.process(f"delete #{batch_id}", user_id=60002)


@pytest.mark.asyncio
async def test_edit_by_batch_and_set_number(handler: MessageHandler):
    """Edit a specific set within a batch by ID and set number."""
    response = await handler.process("did 2 sets of deadlift 5 reps at 315 lbs", user_id=60003)
    assert "Logged" in response
    batch_id = _extract_batch_id(response)

    response = await handler.process(f"change #{batch_id} set 1 to 405 lbs", user_id=60003)
    assert "Edited" in response
    assert "1 set" in response
    assert "405" in response

    # Clean up
    await handler.process(f"delete #{batch_id}", user_id=60003)


@pytest.mark.asyncio
async def test_edit_weight_before_after(handler: MessageHandler):
    """Verify the before/after display shows old and new values."""
    response = await handler.process("did 1 set of overhead press 8 reps at 95 lbs", user_id=60004)
    assert "Logged" in response
    batch_id = _extract_batch_id(response)

    response = await handler.process("fix weight to 105 lbs on last set", user_id=60004)
    assert "Edited" in response
    # Should show the old → new transition
    assert "→" in response
    assert "105" in response

    # Clean up
    await handler.process(f"delete #{batch_id}", user_id=60004)


@pytest.mark.asyncio
async def test_edit_no_workouts(handler: MessageHandler):
    """Editing when no workouts exist returns friendly message."""
    response = await handler.process("change last set to 12 reps", user_id=60005)
    assert "no workouts" in response.lower() or "nothing to edit" in response.lower()


@pytest.mark.asyncio
async def test_edit_wrong_user(handler: MessageHandler):
    """Can't edit another user's workout."""
    response = await handler.process("did 1 set of bench press 10 reps at 135 lbs", user_id=60006)
    assert "Logged" in response
    batch_id = _extract_batch_id(response)

    # Try to edit as different user
    response = await handler.process(f"change #{batch_id} to 12 reps", user_id=60007)
    assert "not found" in response.lower() or "not yours" in response.lower()

    # Clean up
    await handler.process(f"delete #{batch_id}", user_id=60006)

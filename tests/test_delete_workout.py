"""Tests for delete/undo workout functionality."""

import pytest

from nunzio.core import MessageHandler


# --- Unit tests for _parse_workout_id ---

def test_parse_workout_id_with_hash():
    assert MessageHandler._parse_workout_id("delete #42") == 42


def test_parse_workout_id_without_hash():
    assert MessageHandler._parse_workout_id("delete 42") == 42


def test_parse_workout_id_no_number():
    assert MessageHandler._parse_workout_id("delete last") is None


def test_parse_workout_id_embedded():
    assert MessageHandler._parse_workout_id("remove #7 please") == 7


# --- DB integration tests ---

@pytest.fixture
async def handler():
    h = MessageHandler(verbose=True)
    await h.initialize()
    yield h
    await h.close()


@pytest.mark.asyncio
async def test_delete_last_workout(handler: MessageHandler):
    """Create a workout, then undo it."""
    # Log a workout
    response = await handler.process("did 1 set of bench press 10 reps at 135 lbs", user_id=99999)
    assert "Logged" in response

    # Delete it
    response = await handler.process("undo", user_id=99999)
    assert "Deleted workout" in response
    assert "Bench Press" in response or "bench press" in response.lower()


@pytest.mark.asyncio
async def test_delete_nonexistent_user(handler: MessageHandler):
    """Deleting for a user with no workouts returns a friendly message."""
    response = await handler.process("undo", user_id=88888)
    assert "Nothing to delete" in response


@pytest.mark.asyncio
async def test_delete_wrong_user(handler: MessageHandler):
    """Can't delete another user's workout."""
    # Log as user 77777
    response = await handler.process("did 1 set of squat 5 reps at 225 lbs", user_id=77777)
    assert "Logged" in response

    # Extract batch ID from new format: "Logged workout (#N):"
    import re
    match = re.search(r"#(\d+)", response)
    assert match, f"Couldn't find batch ID in: {response}"
    batch_id = match.group(1)

    # Try to delete as user 77778
    response = await handler.process(f"delete #{batch_id}", user_id=77778)
    assert "not found" in response.lower() or "not yours" in response.lower()

    # Clean up: delete as correct user
    await handler.process("undo", user_id=77777)

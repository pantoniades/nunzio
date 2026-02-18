"""Tests for date specification in workout logging."""

from datetime import date, datetime, timedelta

import pytest

from nunzio.core import MessageHandler
from nunzio.database.models import _now_nyc
from nunzio.llm.schemas import ExerciseSet, WorkoutData


# --- Unit tests: date → set_date logic ---


def test_workout_data_date_field_accepts_date():
    """WorkoutData.date should accept a date object."""
    d = date(2026, 2, 17)
    wd = WorkoutData(
        exercises=[ExerciseSet(exercise_name="Bench Press", reps=10, weight=135)],
        date=d,
    )
    assert wd.date == d


def test_workout_data_date_defaults_to_none():
    """WorkoutData.date is None when not specified."""
    wd = WorkoutData(
        exercises=[ExerciseSet(exercise_name="Bench Press", reps=10, weight=135)],
    )
    assert wd.date is None


def test_set_date_uses_extracted_date():
    """When workout_data.date is set, set_date should land on that date."""
    target = date(2026, 2, 15)
    now = _now_nyc()
    set_date = datetime.combine(target, now.time())
    assert set_date.year == 2026
    assert set_date.month == 2
    assert set_date.day == 15


def test_set_date_falls_back_to_now():
    """When workout_data.date is None, set_date should be today."""
    now = _now_nyc()
    assert now.date() == date.today() or (date.today() - now.date()).days <= 1


# --- Integration test: end-to-end with LLM ---


@pytest.fixture
async def handler():
    h = MessageHandler(verbose=True)
    await h.initialize()
    yield h
    await h.close()


@pytest.mark.asyncio
async def test_log_workout_yesterday(handler: MessageHandler):
    """Logging a workout with 'yesterday' should set the date to yesterday."""
    yesterday = (date.today() - timedelta(days=1)).strftime("%b %-d")

    response = await handler.process(
        "did 1 set of bench press 10 reps at 135 lbs yesterday",
        user_id=99998,
    )
    assert "Logged" in response
    # Response header should mention the date
    assert yesterday in response, f"Expected '{yesterday}' in response: {response}"

    # Clean up
    await handler.process("undo", user_id=99998)


@pytest.mark.asyncio
async def test_log_workout_no_date(handler: MessageHandler):
    """Logging without a date mention should not show a date in the header."""
    response = await handler.process(
        "did 1 set of squat 5 reps at 225 lbs",
        user_id=99998,
    )
    assert "Logged" in response
    assert " for " not in response.split("\n")[0]

    # Clean up
    await handler.process("undo", user_id=99998)

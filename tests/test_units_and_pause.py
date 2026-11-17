"""Unit preference and nudge pause — the per-user settings added in v0.10."""

from datetime import timedelta

import pytest

from nunzio.core import MessageHandler
from nunzio.database.connection import db_manager
from nunzio.database.models import DEFAULT_UNIT, now_in_tz
from nunzio.database.repository import user_settings_repo
from nunzio.exercise_names import same_but_for_equipment

USER = 60010


@pytest.fixture
async def handler():
    h = MessageHandler(verbose=True)
    await h.initialize()
    yield h
    async with db_manager.get_session() as session:
        await user_settings_repo.set_weight_unit(session, USER, None)
        await user_settings_repo.set_nudges_paused_until(session, USER, None)
    await h.close()


def test_states_unit():
    states = MessageHandler._states_unit
    for msg in ["bench 10x55 lb", "12@20kg", "curls at 30 pounds", "55 LBS", "20 kilos"]:
        assert states(msg), msg
    for msg in ["bench 10x55", "low row 12@55", "bulb press 10x20", "again @40"]:
        assert not states(msg), msg


def test_fmt_weight_omits_only_the_preferred_unit():
    fmt = MessageHandler._fmt_weight
    assert fmt(55.0, "lbs", "lbs") == "55"
    assert fmt(55.0, "lbs", "kg") == "55 lbs"
    assert fmt(20.0, "kg", "kg") == "20"
    assert fmt(20.0, "kg", "lbs") == "20 kg"


def test_same_but_for_equipment():
    assert same_but_for_equipment("skull crushers", "Dumbbell Skull Crusher")
    assert same_but_for_equipment("bench press", "Incline Dumbbell Bench Press")
    assert not same_but_for_equipment("barbell skull crusher", "Dumbbell Skull Crusher")
    assert not same_but_for_equipment("skull crusher", "Skull Crusher")
    assert not same_but_for_equipment("curl", "Dumbbell Hammer Curl")


async def test_default_unit_is_metric_and_preference_is_saved(handler: MessageHandler):
    assert DEFAULT_UNIT == "kg"
    response = await handler.process("did 1 set of bench press 10 reps at 60", user_id=USER)
    assert "60.0 kg" in response

    response = await handler.process("Please give recommendations in lb, not kg, unless I ask", user_id=USER)
    assert "pounds" in response
    async with db_manager.get_session() as session:
        assert await user_settings_repo.get_weight_unit(session, USER) == "lbs"

    response = await handler.process("did 1 set of bench press 10 reps at 135", user_id=USER)
    assert "135.0 lbs" in response
    # A stated unit always wins over the preference.
    response = await handler.process("did 1 set of bench press 10 reps at 60 kg", user_id=USER)
    assert "60.0 kg" in response

    response = await handler.process("switch to kg", user_id=USER)
    assert "kilograms" in response

    for _ in range(3):
        await handler.process("undo", user_id=USER)


async def test_injury_pauses_nudges_until_the_date(handler: MessageHandler):
    """Nov 6: this message got coaching advice and the nudges kept coming."""
    today = now_in_tz("America/New_York").date()
    response = await handler.process(
        "I have an injury that will keep me from the gym for the next 5 days", user_id=USER
    )
    assert "no nudges" in response
    async with db_manager.get_session() as session:
        until = await user_settings_repo.get_nudges_paused_until(session, USER)
    assert until is not None
    assert today + timedelta(days=3) <= until <= today + timedelta(days=7)

    response = await handler.process("resume nudges", user_id=USER)
    assert "back on" in response
    async with db_manager.get_session() as session:
        assert await user_settings_repo.get_nudges_paused_until(session, USER) is None

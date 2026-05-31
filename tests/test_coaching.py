"""Tests for the coaching context pipeline and response generation.

Integration — needs MySQL + the LLM, like the rest of the suite. The coaching
pipeline shipped with zero tests originally; these are the smoke coverage.
"""

import pytest

from nunzio.core import MessageHandler
from nunzio.database.connection import db_manager
from nunzio.llm.context import build_coaching_context
from nunzio.llm.schemas import UserIntent


COACH_USER = 778899


@pytest.fixture
async def handler():
    h = MessageHandler(verbose=False)
    await h.initialize()
    yield h
    await h.close()


@pytest.mark.asyncio
async def test_context_includes_enriched_sections(handler: MessageHandler):
    """After logging, the coaching context surfaces principles, consistency, and history."""
    await handler.process(
        "did 3 sets of bench press 8 reps at 185 lbs", user_id=COACH_USER
    )
    try:
        intent = UserIntent(
            intent="coaching",
            confidence=0.9,
            mentioned_exercises=["Bench Press"],
        )
        async with db_manager.get_session() as session:
            ctx = await build_coaching_context(
                session, intent, "what next?", COACH_USER
            )
        assert "TRAINING PRINCIPLES:" in ctx
        assert "CONSISTENCY:" in ctx
        assert "EXERCISE: Bench Press" in ctx
    finally:
        await handler.process("undo", user_id=COACH_USER)


@pytest.mark.asyncio
async def test_coaching_response_is_nonempty(handler: MessageHandler):
    """A coaching question against real history returns a usable, non-error response."""
    await handler.process(
        "did 3 sets of squat 5 reps at 225 lbs", user_id=COACH_USER
    )
    try:
        resp = await handler.process(
            "what should I squat next session?", user_id=COACH_USER
        )
        assert resp and resp.strip()
        assert "couldn't generate" not in resp.lower()
    finally:
        await handler.process("undo", user_id=COACH_USER)

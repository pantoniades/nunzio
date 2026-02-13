#!/usr/bin/env python3
"""Test LLM integration: intent classification and workout extraction."""

import pytest

from nunzio.llm.client import LLMClient


@pytest.fixture
async def client():
    """Create and initialize an LLM client for testing."""
    c = LLMClient()
    await c.initialize()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_intent_classification(client: LLMClient):
    """Test intent classification accuracy."""
    test_cases = [
        ("I did 3 sets of bench press at 135 lbs", "log_workout"),
        ("What exercises should I do for chest?", "coaching"),
        ("How's my squat progress?", "view_stats"),
        ("Hello! How are you?", "coaching"),
        ("I want to track my gym workout", "log_workout"),
        ("Give me some exercise suggestions", "coaching"),
        ("Show me my workout stats", "view_stats"),
        ("Tell me about fitness", "coaching"),
        ("undo", "delete_workout"),
        ("delete last workout", "delete_workout"),
        ("delete session #42", "delete_workout"),
        ("again", "repeat_last"),
        ("repeat last workout", "repeat_last"),
        ("same as last time", "repeat_last"),
    ]

    passed = 0
    total = len(test_cases)

    for message, expected_intent in test_cases:
        result = await client.classify_intent(message)
        if result.intent == expected_intent:
            passed += 1

    # Allow some LLM fuzziness — 70% threshold
    assert passed >= total * 0.7, f"Intent classification: {passed}/{total} passed"


@pytest.mark.asyncio
async def test_workout_extraction(client: LLMClient):
    """Test workout data extraction."""
    test_workouts = [
        "3 sets of bench press: 135x10, 135x8, 135x6",
        "Squat: 5x5 at 225 lbs",
        "Deadlift: 3x3 at 315 lbs",
        "Pull-ups: 3 sets to failure, bodyweight",
    ]

    passed = 0
    total = len(test_workouts)

    for workout_desc in test_workouts:
        result = await client.extract_workout_data(workout_desc)
        if result and result.exercises:
            passed += 1

    # Allow some LLM fuzziness — 60% threshold
    assert passed >= total * 0.6, f"Workout extraction: {passed}/{total} passed"

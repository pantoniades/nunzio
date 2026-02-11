#!/usr/bin/env python3
"""Test LLM integration: intent classification and workout extraction."""

import asyncio
import sys

from nunzio.llm.client import LLMClient


async def test_intent_classification(client: LLMClient) -> bool:
    """Test intent classification accuracy."""
    print("Testing Intent Classification...")

    test_cases = [
        ("I did 3 sets of bench press at 135 lbs", "log_workout"),
        ("What exercises should I do for chest?", "coaching"),
        ("How's my squat progress?", "view_stats"),
        ("Hello! How are you?", "coaching"),
        ("I want to track my gym workout", "log_workout"),
        ("Give me some exercise suggestions", "coaching"),
        ("Show me my workout stats", "view_stats"),
        ("Tell me about fitness", "coaching"),
    ]

    passed = 0
    total = len(test_cases)

    for message, expected_intent in test_cases:
        try:
            result = await client.classify_intent(message)
            if result.intent == expected_intent:
                passed += 1
                print(f"  PASS '{message}' -> {result.intent} ({result.confidence:.2f})")
            else:
                print(f"  FAIL '{message}' -> {result.intent} (expected: {expected_intent})")
        except Exception as e:
            print(f"  ERROR '{message}': {e}")

    print(f"Intent Classification: {passed}/{total} passed")
    return passed >= total * 0.7


async def test_workout_extraction(client: LLMClient) -> bool:
    """Test workout data extraction."""
    print("\nTesting Workout Data Extraction...")

    test_workouts = [
        "3 sets of bench press: 135x10, 135x8, 135x6",
        "Squat: 5x5 at 225 lbs",
        "Deadlift: 3x3 at 315 lbs",
        "Pull-ups: 3 sets to failure, bodyweight",
    ]

    passed = 0
    total = len(test_workouts)

    for workout_desc in test_workouts:
        try:
            result = await client.extract_workout_data(workout_desc)
            if result and result.exercises:
                exercise_count = len(result.exercises)
                total_volume = sum(
                    (ex.weight or 0) * (ex.reps or 0) for ex in result.exercises
                )
                print(
                    f"  PASS '{workout_desc}' -> {exercise_count} exercises, {total_volume} lbs volume"
                )
                passed += 1
            else:
                print(f"  FAIL '{workout_desc}' -> No valid extraction")
        except Exception as e:
            print(f"  ERROR '{workout_desc}': {e}")

    print(f"Workout Extraction: {passed}/{total} passed")
    return passed >= total * 0.6


async def main() -> bool:
    """Run LLM integration tests."""
    print("LLM Integration Test Suite")
    print("=" * 50)

    client = LLMClient()
    await client.initialize()

    results = [
        await test_intent_classification(client),
        await test_workout_extraction(client),
    ]

    await client.close()

    passed = sum(results)
    total = len(results)
    print(f"\nFinal: {passed}/{total} suites passed")
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

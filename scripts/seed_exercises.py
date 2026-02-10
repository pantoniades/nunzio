#!/usr/bin/env python3
"""Seed the exercises table with common exercises."""

import asyncio
import sys

from nunzio.database.connection import db_manager
from nunzio.database.repository import exercise_repo

SAMPLE_EXERCISES = [
    # Chest
    {"name": "Bench Press", "muscle_group": "chest", "description": "Classic compound chest exercise"},
    {"name": "Incline Dumbbell Press", "muscle_group": "chest", "description": "Upper chest focus"},
    {"name": "Push-up", "muscle_group": "chest", "description": "Bodyweight chest exercise"},
    {"name": "Dumbbell Flyes", "muscle_group": "chest", "description": "Chest isolation exercise"},
    # Back
    {"name": "Pull-up", "muscle_group": "back", "description": "Compound back exercise"},
    {"name": "Barbell Row", "muscle_group": "back", "description": "Horizontal pulling movement"},
    {"name": "Deadlift", "muscle_group": "back", "description": "Full body posterior chain"},
    {"name": "Lat Pulldown", "muscle_group": "back", "description": "Vertical pulling movement"},
    # Shoulders
    {"name": "Overhead Press", "muscle_group": "shoulders", "description": "Compound shoulder exercise"},
    {"name": "Lateral Raises", "muscle_group": "shoulders", "description": "Shoulder isolation"},
    {"name": "Face Pulls", "muscle_group": "shoulders", "description": "Rear delt and shoulder health"},
    # Arms
    {"name": "Bicep Curls", "muscle_group": "biceps", "description": "Bicep isolation"},
    {"name": "Tricep Pushdowns", "muscle_group": "triceps", "description": "Tricep isolation"},
    {"name": "Hammer Curls", "muscle_group": "biceps", "description": "Brachioradialis and biceps"},
    {"name": "Skull Crushers", "muscle_group": "triceps", "description": "Tricep isolation exercise"},
    # Legs
    {"name": "Squat", "muscle_group": "legs", "description": "King of leg exercises"},
    {"name": "Romanian Deadlift", "muscle_group": "legs", "description": "Hamstring and glute focus"},
    {"name": "Leg Press", "muscle_group": "legs", "description": "Machine leg exercise"},
    {"name": "Bulgarian Split Squats", "muscle_group": "legs", "description": "Unilateral leg exercise"},
    # Core
    {"name": "Plank", "muscle_group": "core", "description": "Core stability exercise"},
    {"name": "Russian Twists", "muscle_group": "core", "description": "Rotational core work"},
    {"name": "Hanging Leg Raises", "muscle_group": "core", "description": "Lower abs focus"},
    {"name": "Crunches", "muscle_group": "core", "description": "Classic ab exercise"},
    # Cardio
    {"name": "Running", "muscle_group": "cardio", "description": "Cardiovascular exercise"},
    {"name": "Cycling", "muscle_group": "cardio", "description": "Low impact cardio"},
    {"name": "Rowing Machine", "muscle_group": "cardio", "description": "Full body cardio"},
    # Flexibility
    {"name": "Yoga", "muscle_group": "flexibility", "description": "Flexibility and mobility"},
    {"name": "Stretching", "muscle_group": "flexibility", "description": "Static stretching"},
    {"name": "Foam Rolling", "muscle_group": "flexibility", "description": "Self-myofascial release"},
]


async def create_sample_exercises():
    """Seed exercise data into the database."""
    print("Seeding exercise data...")

    try:
        await db_manager.initialize()

        async with db_manager.get_session() as session:
            existing = await exercise_repo.get_multi(session, limit=1)
            if existing:
                print("Exercises already exist. Skipping.")
                return True

            created = 0
            for data in SAMPLE_EXERCISES:
                try:
                    exercise = await exercise_repo.create(session, obj_in=data)
                    created += 1
                    print(f"  Created: {exercise.name} ({exercise.muscle_group})")
                except Exception as e:
                    if "Duplicate entry" in str(e):
                        print(f"  Skipped duplicate: {data['name']}")
                    else:
                        print(f"  Failed: {data['name']}: {e}")

            print(f"Created {created} exercises.")
            return True

    except Exception as e:
        print(f"Failed to seed exercises: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    success = asyncio.run(create_sample_exercises())
    sys.exit(0 if success else 1)

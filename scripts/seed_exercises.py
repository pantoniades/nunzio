#!/usr/bin/env python3
"""Seed the exercises table with common exercises and coaching guidance."""

import asyncio
import sys

from nunzio.database.connection import db_manager
from nunzio.database.models import Exercise
from nunzio.database.repository import exercise_repo

SAMPLE_EXERCISES = [
    # Chest
    {
        "name": "Bench Press",
        "muscle_group": "chest",
        "description": "Classic compound chest exercise",
        "guidance": (
            "Compound chest movement. Strength: 3-5x3-5, heavy. Hypertrophy: 3-4x8-12, moderate. "
            "Progress +5 lbs when all sets hit target reps. Stalled 2+ sessions → deload 10%. "
            "Rest 2-3 min (strength) or 60-90s (hypertrophy). Retract shoulder blades, plant feet."
        ),
    },
    {
        "name": "Incline Dumbbell Press",
        "muscle_group": "chest",
        "description": "Upper chest focus",
        "guidance": (
            "Upper chest emphasis. Hypertrophy: 3-4x8-12. Progress +5 lbs per hand when all sets "
            "hit target reps. 30-45 degree incline. Control the eccentric, press to lockout without "
            "clanging dumbbells. Rest 60-90s."
        ),
    },
    {
        "name": "Push-up",
        "muscle_group": "chest",
        "description": "Bodyweight chest exercise",
        "guidance": (
            "Bodyweight push. Progress by adding reps (3 sets to failure), then move to harder "
            "variations: incline → flat → decline → weighted. Keep core tight, full ROM chest to "
            "floor. Rest 60s between sets."
        ),
    },
    {
        "name": "Dumbbell Flyes",
        "muscle_group": "chest",
        "description": "Chest isolation exercise",
        "guidance": (
            "Chest isolation, stretch emphasis. 3-4x10-15 with light-moderate weight. Do NOT go "
            "heavy — shoulder injury risk. Slight bend in elbows, control the stretch at bottom. "
            "Progress +5 lbs per hand conservatively. Rest 60s."
        ),
    },
    # Back
    {
        "name": "Pull-up",
        "muscle_group": "back",
        "description": "Compound back exercise",
        "guidance": (
            "Compound vertical pull. Can't do full reps → use band assistance or negatives. "
            "Progress by adding reps, then add weight via belt. Strength: 5x3-5 weighted. "
            "Hypertrophy: 3-4x6-12. Full hang to chin over bar. Rest 2-3 min."
        ),
    },
    {
        "name": "Barbell Row",
        "muscle_group": "back",
        "description": "Horizontal pulling movement",
        "guidance": (
            "Compound horizontal pull. Strength: 3-5x5. Hypertrophy: 3-4x8-12. Progress +5 lbs "
            "when all sets hit target. Keep back at ~45 degrees, pull to lower chest. No excessive "
            "body English. Rest 2-3 min (strength) or 60-90s (hypertrophy)."
        ),
    },
    {
        "name": "Deadlift",
        "muscle_group": "back",
        "description": "Full body posterior chain",
        "guidance": (
            "Full posterior chain compound. Strength: 1-3x3-5, heavy. Hypertrophy: 3x6-8. "
            "Progress +5-10 lbs when form is solid. Hinge at hips, neutral spine, bar close to "
            "body. Very taxing — typically 1x/week. Rest 3-5 min between heavy sets."
        ),
    },
    {
        "name": "Lat Pulldown",
        "muscle_group": "back",
        "description": "Vertical pulling movement",
        "guidance": (
            "Vertical pull, lat focus. Good pull-up substitute or supplement. 3-4x8-12. "
            "Progress by increasing weight when all sets complete. Pull to upper chest, squeeze "
            "lats at bottom. Avoid leaning too far back. Rest 60-90s."
        ),
    },
    # Shoulders
    {
        "name": "Overhead Press",
        "muscle_group": "shoulders",
        "description": "Compound shoulder exercise",
        "guidance": (
            "Compound shoulder press. Strength: 3-5x3-5. Hypertrophy: 3-4x8-12. Progress +5 lbs "
            "when all sets hit target — slowest progressing barbell lift. Brace core, press straight "
            "up, lock out overhead. Rest 2-3 min (strength) or 60-90s (hypertrophy)."
        ),
    },
    {
        "name": "Lateral Raises",
        "muscle_group": "shoulders",
        "description": "Shoulder isolation",
        "guidance": (
            "Side delt isolation. 3-4x12-20, light weight. Progress +2.5-5 lbs very slowly — "
            "ego weight kills form. Slight lean forward, raise to shoulder height, control descent. "
            "High frequency tolerant — can do 3-4x/week. Rest 45-60s."
        ),
    },
    {
        "name": "Face Pulls",
        "muscle_group": "shoulders",
        "description": "Rear delt and shoulder health",
        "guidance": (
            "Rear delt and rotator cuff health. 3-4x15-20, light weight. Not a strength exercise — "
            "focus on squeeze and external rotation at top. Do every upper body day for shoulder "
            "health. Progress slowly. Rest 45-60s."
        ),
    },
    # Arms
    {
        "name": "Bicep Curls",
        "muscle_group": "biceps",
        "description": "Bicep isolation",
        "guidance": (
            "Bicep isolation. 3-4x8-12. Progress +5 lbs per hand when all sets hit target. "
            "Full ROM, no swinging. Barbell or dumbbell — dumbbells allow supination. "
            "Rest 60s. Biceps recover fast, can train 2-3x/week."
        ),
    },
    {
        "name": "Tricep Pushdowns",
        "muscle_group": "triceps",
        "description": "Tricep isolation",
        "guidance": (
            "Tricep isolation, cable. 3-4x10-15. Progress by increasing weight when all sets "
            "complete. Keep elbows pinned to sides, full extension at bottom. Rope attachment "
            "allows better peak contraction. Rest 60s."
        ),
    },
    {
        "name": "Hammer Curls",
        "muscle_group": "biceps",
        "description": "Brachioradialis and biceps",
        "guidance": (
            "Targets brachioradialis and bicep long head. 3-4x8-12. Neutral grip (palms facing "
            "each other). Progress +5 lbs per hand. Good complement to regular curls for complete "
            "arm development. Rest 60s."
        ),
    },
    {
        "name": "Skull Crushers",
        "muscle_group": "triceps",
        "description": "Tricep isolation exercise",
        "guidance": (
            "Tricep isolation, long head emphasis. 3-4x8-12. Lower bar to forehead or just behind "
            "head. Progress +5 lbs when all sets hit target. Watch for elbow pain — switch to "
            "overhead extension if it flares. Rest 60-90s."
        ),
    },
    # Legs
    {
        "name": "Squat",
        "muscle_group": "legs",
        "description": "King of leg exercises",
        "guidance": (
            "Compound quad/glute dominant. Strength: 3-5x3-5, heavy. Hypertrophy: 3-4x8-12. "
            "Progress +5-10 lbs when all sets hit target. Depth: hip crease below knee. Brace "
            "core, chest up, knees tracking toes. Rest 3-5 min (strength) or 2 min (hypertrophy)."
        ),
    },
    {
        "name": "Romanian Deadlift",
        "muscle_group": "legs",
        "description": "Hamstring and glute focus",
        "guidance": (
            "Hamstring and glute emphasis. 3-4x8-12. Hinge at hips, slight knee bend, feel the "
            "hamstring stretch. Progress +5-10 lbs when form stays clean. Bar stays close to legs. "
            "Don't round the back. Rest 90s-2 min."
        ),
    },
    {
        "name": "Leg Press",
        "muscle_group": "legs",
        "description": "Machine leg exercise",
        "guidance": (
            "Machine compound leg exercise. Good for volume after squats. 3-4x8-15. Progress by "
            "adding weight when all sets complete. Don't lock out knees at top. Foot placement "
            "varies emphasis — high = glutes, low = quads. Rest 90s-2 min."
        ),
    },
    {
        "name": "Bulgarian Split Squats",
        "muscle_group": "legs",
        "description": "Unilateral leg exercise",
        "guidance": (
            "Unilateral leg exercise, fixes imbalances. 3x8-12 per leg. Progress +5 lbs per hand "
            "when stable and hitting target reps. Rear foot elevated on bench. Keep torso upright. "
            "Brutal but effective. Rest 60-90s per leg."
        ),
    },
    # Core
    {
        "name": "Plank",
        "muscle_group": "core",
        "description": "Core stability exercise",
        "guidance": (
            "Core stability, anti-extension. Hold 3x30-60s. Progress by adding time (up to 2 min), "
            "then add difficulty: weighted plate on back, or switch to ab wheel rollouts. "
            "Squeeze glutes, don't let hips sag. Rest 60s."
        ),
    },
    {
        "name": "Russian Twists",
        "muscle_group": "core",
        "description": "Rotational core work",
        "guidance": (
            "Rotational core exercise. 3x15-20 per side. Progress by adding weight (plate or "
            "dumbbell). Lean back slightly, feet off ground for harder variation. Control the "
            "rotation, don't just swing. Rest 60s."
        ),
    },
    {
        "name": "Hanging Leg Raises",
        "muscle_group": "core",
        "description": "Lower abs focus",
        "guidance": (
            "Lower ab emphasis. 3x8-15. Progress: knee raises → straight leg raises → toes to bar. "
            "No swinging — controlled movement. Curl pelvis up, don't just lift legs with hip "
            "flexors. Rest 60-90s."
        ),
    },
    {
        "name": "Crunches",
        "muscle_group": "core",
        "description": "Classic ab exercise",
        "guidance": (
            "Basic ab exercise. 3x15-25. Progress by adding weight (plate on chest) or switching to "
            "cable crunches. Short ROM — lift shoulder blades off ground, squeeze. Don't pull on "
            "neck. Rest 45-60s."
        ),
    },
    # Cardio
    {
        "name": "Running",
        "muscle_group": "cardio",
        "description": "Cardiovascular exercise",
        "guidance": (
            "Steady state: 20-45 min at conversational pace (RPE 4-6). Intervals: 6-10 rounds of "
            "30s hard / 60-90s easy. Progress by adding 5 min/week to steady state or 1 round to "
            "intervals. Track duration and distance, not weight. Rest days between hard sessions. "
            "Easy runs should feel genuinely easy."
        ),
    },
    {
        "name": "Cycling",
        "muscle_group": "cardio",
        "description": "Low impact cardio",
        "guidance": (
            "Steady state: 30-60 min at moderate effort (RPE 4-6). Intervals: 8-12 rounds of "
            "30s sprint / 90s easy. Progress by adding 5-10 min/week or increasing resistance. "
            "Low impact — good for active recovery days. Track duration and distance."
        ),
    },
    {
        "name": "Rowing Machine",
        "muscle_group": "cardio",
        "description": "Full body cardio",
        "guidance": (
            "Full body cardio, works back/legs/core. Steady state: 20-30 min at 18-22 strokes/min. "
            "Intervals: 8x250m with 60s rest. Progress by adding duration or lowering split times. "
            "Drive with legs first, then lean back, then pull arms. Track distance and split time."
        ),
    },
    # Flexibility
    {
        "name": "Yoga",
        "muscle_group": "flexibility",
        "description": "Flexibility and mobility",
        "guidance": (
            "Flexibility and mobility work. 20-60 min sessions. Progress by increasing session "
            "length or trying more advanced poses. Focus on breathing. Good on rest days or as "
            "a cooldown. No weight tracking needed."
        ),
    },
    {
        "name": "Stretching",
        "muscle_group": "flexibility",
        "description": "Static stretching",
        "guidance": (
            "Static stretching for flexibility. Hold each stretch 30-60s, 2-3 rounds. Best done "
            "after workout when muscles are warm. Progress by increasing hold time or deepening "
            "the stretch. Don't bounce."
        ),
    },
    {
        "name": "Foam Rolling",
        "muscle_group": "flexibility",
        "description": "Self-myofascial release",
        "guidance": (
            "Self-myofascial release. Spend 1-2 min per muscle group, rolling slowly over tight "
            "spots. Before workout: quick passes to warm up tissue. After workout: slower, deeper "
            "work. Not a replacement for stretching."
        ),
    },
]


async def create_sample_exercises():
    """Seed exercise data into the database."""
    print("Seeding exercise data...")

    try:
        await db_manager.initialize()

        async with db_manager.get_session() as session:
            existing = await exercise_repo.get_multi(session, limit=1)
            if existing:
                # Update existing exercises with guidance text
                print("Exercises exist. Updating guidance text...")
                updated = 0
                for data in SAMPLE_EXERCISES:
                    exercise = await exercise_repo.get_by_name(session, data["name"])
                    if exercise and not exercise.guidance:
                        exercise.guidance = data["guidance"]
                        updated += 1
                        print(f"  Updated guidance: {exercise.name}")
                print(f"Updated {updated} exercises with guidance.")
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

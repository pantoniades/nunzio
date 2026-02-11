#!/usr/bin/env python3
"""Seed the training_principles table with coaching knowledge."""

import asyncio
import sys

from nunzio.database.connection import db_manager
from nunzio.database.repository import training_principle_repo

TRAINING_PRINCIPLES = [
    {
        "category": "progression",
        "title": "Linear Progression",
        "content": (
            "Add weight every session when all sets hit target reps. Barbell compounds: +5 lbs. "
            "Dumbbell movements: +5 lbs per hand. Isolation exercises: +2.5 lbs or add reps first. "
            "When you can't add weight, add reps within the target range before increasing."
        ),
        "priority": 1,
    },
    {
        "category": "deload",
        "title": "Deload Protocol",
        "content": (
            "Deload when stalled 2+ sessions on a lift or after 4-6 weeks of hard training. "
            "Reduce weight by 10%, keep reps and sets the same. Work back up over 2-3 sessions. "
            "Deload week: reduce volume by 40-50%, keep intensity moderate. Don't skip deloads — "
            "they prevent injury and allow recovery."
        ),
        "priority": 2,
    },
    {
        "category": "rep_ranges",
        "title": "Rep Ranges and Goals",
        "content": (
            "Strength: 3-5 reps, 3-5 sets, heavy weight, rest 2-5 min. "
            "Hypertrophy: 8-12 reps, 3-4 sets, moderate weight, rest 60-90s. "
            "Endurance: 15-20+ reps, 2-3 sets, light weight, rest 30-60s. "
            "Most people benefit from a mix, with compounds in the strength range and "
            "accessories in the hypertrophy range."
        ),
        "priority": 3,
    },
    {
        "category": "volume",
        "title": "Weekly Volume Targets",
        "content": (
            "Target 10-20 hard sets per muscle group per week for growth. Beginners: start at "
            "10 sets/week. Advanced: up to 20. Spread volume across 2-3 sessions per muscle group. "
            "More than 10 sets in a single session has diminishing returns. If recovery is poor, "
            "cut volume before cutting frequency."
        ),
        "priority": 4,
    },
    {
        "category": "warmup",
        "title": "Warm-up Sets",
        "content": (
            "Before working sets, do 2-3 ramp-up sets. Example for 185 lb bench: empty bar x10, "
            "95 x8, 135 x5, then working sets at 185. Warm-ups should not be fatiguing — just "
            "enough to groove the movement and prep joints. Skip warm-ups for isolation exercises "
            "if compounds were already done for that muscle."
        ),
        "priority": 5,
    },
    {
        "category": "exercise_selection",
        "title": "Exercise Selection",
        "content": (
            "Do compound movements first when fresh (squat, bench, deadlift, OHP, rows). "
            "Follow with isolation work. Balance push and pull volume roughly 1:1. "
            "Don't do more than 5-6 exercises per session. Pick exercises you can do "
            "pain-free with good form — no exercise is mandatory."
        ),
        "priority": 6,
    },
    {
        "category": "stalling",
        "title": "Breaking Through Plateaus",
        "content": (
            "Stalled on a lift? In order, try: 1) Eat and sleep more. 2) Deload 10% and build "
            "back up. 3) Change rep scheme (e.g., 5x5 → 3x8). 4) Add a variation (e.g., pause "
            "bench, tempo squat). 5) Increase frequency for that lift. Don't just keep grinding "
            "the same weight — that's how you get hurt."
        ),
        "priority": 7,
    },
    {
        "category": "new_exercise",
        "title": "Starting a New Exercise",
        "content": (
            "New exercise? Start light — ego is the enemy. Use 50-60% of what you think you can "
            "do. Focus on form for 2-3 sessions. Add weight only when the movement feels natural. "
            "Film yourself or use mirrors to check form. It's better to start too light than too "
            "heavy."
        ),
        "priority": 8,
    },
    {
        "category": "cardio",
        "title": "Cardio Programming",
        "content": (
            "If lifting is the priority, do 2-3 cardio sessions per week. Keep most cardio low "
            "intensity (can hold a conversation). 1 HIIT session per week max. Do cardio after "
            "lifting or on separate days — not before. Progress by adding 5 min/week to steady "
            "state. Cardio doesn't kill gains if recovery and nutrition are adequate."
        ),
        "priority": 9,
    },
]


async def seed_principles():
    """Seed training principles into the database."""
    print("Seeding training principles...")

    try:
        await db_manager.initialize()

        async with db_manager.get_session() as session:
            existing = await training_principle_repo.get_multi(session, limit=1)
            if existing:
                print("Training principles already exist. Skipping.")
                return True

            created = 0
            for data in TRAINING_PRINCIPLES:
                try:
                    principle = await training_principle_repo.create(session, obj_in=data)
                    created += 1
                    print(f"  Created: [{principle.category}] {principle.title}")
                except Exception as e:
                    print(f"  Failed: {data['title']}: {e}")

            print(f"Created {created} training principles.")
            return True

    except Exception as e:
        print(f"Failed to seed training principles: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    success = asyncio.run(seed_principles())
    sys.exit(0 if success else 1)

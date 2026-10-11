#!/usr/bin/env python3
"""v0.9 data cleanup: merge duplicate exercises and backfill muscle groups.

Dry run by default — prints what it would change. Pass --apply to write. Idempotent:
merges whose source exercise no longer exists are skipped, and the muscle-group
backfill only touches exercises still marked 'general'.

  python scripts/migrate_v09.py            # show the plan
  python scripts/migrate_v09.py --apply    # do it
"""

import asyncio
import sys

from sqlalchemy import text

from nunzio.database.connection import db_manager
from nunzio.exercise_names import guess_muscle_group

# (source name, target name): move every set from source onto target, delete source.
MERGES: list[tuple[str, str]] = [
    ("Band Pull-Apart", "Band Pull Apart"),
    ("Face Pull", "Face Pulls"),        # keep the catalog row (has guidance) ...
    ("Dumbbell Curls", "Dumbbell Curl"),
    ("Dumbbell Fly", "Dumbbell Flyes"),  # catalog row has guidance
    ("Pushups", "Pushup"),
]

# Rename after merging (the unique name is free once the source is deleted).
RENAMES: list[tuple[str, str]] = [
    ("Face Pulls", "Face Pull"),         # ... under the name actually used
]

# (raw name the user typed, wrongly matched exercise, new exercise to split them into)
SPLITS: list[tuple[str, str, str]] = [
    ("Dumbbell Bench Press", "Bench Press", "Dumbbell Bench Press"),
    ("Incline Dumbbell Curls", "Dumbbell Curls", "Incline Dumbbell Curl"),
    ("Incline Dumbbell Curls", "Dumbbell Curl", "Incline Dumbbell Curl"),
]


async def _exercise_id(conn, name: str) -> int | None:
    r = await conn.execute(text("SELECT id FROM exercises WHERE name = :n"), {"n": name})
    row = r.first()
    return row[0] if row else None


async def _ensure_exercise(conn, name: str, apply: bool) -> int | None:
    ex_id = await _exercise_id(conn, name)
    if ex_id is None:
        group = guess_muscle_group(name)
        print(f"  create exercise '{name}' ({group})")
        if apply:
            await conn.execute(
                text("INSERT INTO exercises (name, muscle_group, created_at) "
                     "VALUES (:n, :g, NOW())"),
                {"n": name, "g": group},
            )
            ex_id = await _exercise_id(conn, name)
    return ex_id


async def migrate(apply: bool) -> bool:
    print(f"v0.9 exercise cleanup ({'APPLY' if apply else 'dry run'})")
    await db_manager.initialize()
    try:
        async with db_manager._engine.begin() as conn:
            # 1. Split wrongly merged sets out by what the user actually typed.
            #    Runs first so the curl split happens before the curl merge.
            for raw, wrong, new in SPLITS:
                wrong_id = await _exercise_id(conn, wrong)
                if wrong_id is None:
                    continue
                r = await conn.execute(
                    text("SELECT COUNT(*) FROM workout_sets "
                         "WHERE exercise_id = :e AND raw_exercise_name = :raw"),
                    {"e": wrong_id, "raw": raw},
                )
                n = r.scalar()
                if not n:
                    continue
                print(f"split: {n} '{raw}' sets out of '{wrong}' into '{new}'")
                new_id = await _ensure_exercise(conn, new, apply)
                if apply:
                    await conn.execute(
                        text("UPDATE workout_sets SET exercise_id = :new "
                             "WHERE exercise_id = :e AND raw_exercise_name = :raw"),
                        {"new": new_id, "e": wrong_id, "raw": raw},
                    )

            # 2. Merge duplicates.
            for src, dst in MERGES:
                src_id = await _exercise_id(conn, src)
                dst_id = await _exercise_id(conn, dst)
                if src_id is None or dst_id is None:
                    continue
                r = await conn.execute(
                    text("SELECT COUNT(*) FROM workout_sets WHERE exercise_id = :s"),
                    {"s": src_id},
                )
                print(f"merge: '{src}' (#{src_id}, {r.scalar()} sets) -> '{dst}' (#{dst_id})")
                if apply:
                    await conn.execute(
                        text("UPDATE workout_sets SET exercise_id = :d WHERE exercise_id = :s"),
                        {"d": dst_id, "s": src_id},
                    )
                    await conn.execute(text("DELETE FROM exercises WHERE id = :s"), {"s": src_id})

            # 3. Renames.
            for old, new in RENAMES:
                old_id = await _exercise_id(conn, old)
                if old_id is None:
                    continue
                if await _exercise_id(conn, new) is not None and not apply:
                    print(f"rename: '{old}' -> '{new}' (after merge frees the name)")
                    continue
                print(f"rename: '{old}' -> '{new}'")
                if apply:
                    await conn.execute(
                        text("UPDATE exercises SET name = :n WHERE id = :i"),
                        {"n": new, "i": old_id},
                    )

            # 4. Backfill muscle groups on exercises still marked 'general'.
            r = await conn.execute(
                text("SELECT id, name FROM exercises WHERE muscle_group = 'general' ORDER BY name")
            )
            for ex_id, name in r.fetchall():
                group = guess_muscle_group(name)
                if group == "general":
                    print(f"group: '{name}' stays general (no rule matched)")
                    continue
                print(f"group: '{name}' general -> {group}")
                if apply:
                    await conn.execute(
                        text("UPDATE exercises SET muscle_group = :g WHERE id = :i"),
                        {"g": group, "i": ex_id},
                    )

            if not apply:
                await conn.rollback()
        print("done." if apply else "dry run only — re-run with --apply to write.")
        return True
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    ok = asyncio.run(migrate(apply="--apply" in sys.argv))
    sys.exit(0 if ok else 1)

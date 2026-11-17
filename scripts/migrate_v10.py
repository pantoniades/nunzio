#!/usr/bin/env python3
"""v0.10 migration: per-user unit + nudge-pause columns, and an exercise cleanup.

Dry run by default — prints what it would change. Pass --apply to write. Idempotent:
columns that exist are left alone, and splits/merges whose source is gone are skipped.
Back up `exercises` and `workout_sets` first (see deploy/README.md).

  python scripts/migrate_v10.py            # show the plan
  python scripts/migrate_v10.py --apply    # do it
"""

import asyncio
import sys

from sqlalchemy import text

from nunzio.database.connection import db_manager
from nunzio.exercise_names import guess_muscle_group

# New nullable columns on user_settings: (name, DDL type).
COLUMNS: list[tuple[str, str]] = [
    ("weight_unit", "VARCHAR(10) NULL"),
    ("nudges_paused_until", "DATE NULL"),
]

# (raw name the user typed, wrongly matched exercise, exercise the sets belong to)
SPLITS: list[tuple[str, str, str]] = [
    ("Scapular Pushups", "Pushup", "Scapular Push-Up"),
    ("Dumbbell Hammer Curl", "Dumbbell Curl", "Hammer Curls"),
]

# (source name, target name): move every set from source onto target, delete source.
# The target inherits the source's guidance/description when it has none of its own.
MERGES: list[tuple[str, str]] = [
    ("Pushup", "Push-up"),                         # catalog row has guidance
    ("Lateral Raise", "Lateral Raises"),           # catalog row has guidance ...
    ("Skull Crushers", "Dumbbell Skull Crusher"),  # both logged with dumbbells
]

# Rename after merging (the unique name is free once the source is deleted).
RENAMES: list[tuple[str, str]] = [
    ("Lateral Raises", "Lateral Raise"),           # ... under the name actually used
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
    print(f"v0.10 migration ({'APPLY' if apply else 'dry run'})")
    await db_manager.initialize()
    try:
        # 1. Schema. DDL autocommits in MySQL, so it gets its own connection.
        async with db_manager._engine.begin() as conn:
            for column, ddl in COLUMNS:
                r = await conn.execute(
                    text("SELECT COUNT(*) FROM information_schema.columns "
                         "WHERE table_schema = DATABASE() "
                         "AND table_name = 'user_settings' AND column_name = :c"),
                    {"c": column},
                )
                if r.scalar():
                    continue
                print(f"schema: add user_settings.{column} {ddl}")
                if apply:
                    await conn.execute(
                        text(f"ALTER TABLE user_settings ADD COLUMN {column} {ddl}")
                    )

        async with db_manager._engine.begin() as conn:
            # 2. Split wrongly merged sets out by what the user actually typed.
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

            # 3. Merge duplicates.
            for src, dst in MERGES:
                src_id = await _exercise_id(conn, src)
                dst_id = await _exercise_id(conn, dst)
                if src_id is None or dst_id is None or src_id == dst_id:
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
                    await conn.execute(
                        text("UPDATE exercises d JOIN exercises s ON s.id = :s "
                             "SET d.guidance = COALESCE(d.guidance, s.guidance), "
                             "d.description = COALESCE(d.description, s.description) "
                             "WHERE d.id = :d"),
                        {"d": dst_id, "s": src_id},
                    )
                    await conn.execute(text("DELETE FROM exercises WHERE id = :s"), {"s": src_id})

            # 4. Renames.
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

            # 5. Orphans: ad-hoc exercises (no guidance) that no set points at — left
            #    behind when a mislogged workout was deleted.
            r = await conn.execute(
                text("SELECT e.id, e.name FROM exercises e "
                     "WHERE e.guidance IS NULL AND NOT EXISTS "
                     "(SELECT 1 FROM workout_sets ws WHERE ws.exercise_id = e.id) "
                     "ORDER BY e.name")
            )
            for ex_id, name in r.fetchall():
                print(f"orphan: delete '{name}' (#{ex_id}, no sets, no guidance)")
                if apply:
                    await conn.execute(text("DELETE FROM exercises WHERE id = :i"), {"i": ex_id})

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

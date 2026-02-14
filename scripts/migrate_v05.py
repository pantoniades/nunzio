#!/usr/bin/env python3
"""v0.5 migration: flatten workout_sessions into workout_sets.

Adds user_id, set_date, batch_id to workout_sets (backfilled from workout_sessions),
then drops session_id column and workout_sessions table.

Each old session_id becomes a batch_id (1-based, ordered by session date).
"""

import asyncio
import sys

from sqlalchemy import text

from nunzio.database.connection import db_manager


async def migrate():
    print("Running v0.5 migration: flatten data model...")

    try:
        await db_manager.initialize()

        async with db_manager.get_session() as session:
            # 1. Add new columns (idempotent)
            for col, col_def in [
                ("user_id", "BIGINT NOT NULL DEFAULT 0"),
                ("set_date", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
                ("batch_id", "INTEGER NOT NULL DEFAULT 0"),
            ]:
                try:
                    await session.execute(text(
                        f"ALTER TABLE workout_sets ADD COLUMN {col} {col_def}"
                    ))
                    print(f"  Added {col} column")
                except Exception as e:
                    if "Duplicate column" in str(e):
                        print(f"  {col} column already exists — skipping")
                    else:
                        raise

            # 2. Backfill from workout_sessions
            await session.execute(text("""
                UPDATE workout_sets ws
                JOIN workout_sessions s ON ws.session_id = s.id
                SET ws.user_id = s.user_id,
                    ws.set_date = s.date
            """))
            print("  Backfilled user_id and set_date from workout_sessions")

            # 3. Assign batch_ids: each distinct session_id becomes a batch_id,
            #    numbered per-user in chronological order
            await session.execute(text("""
                UPDATE workout_sets ws
                JOIN (
                    SELECT ws2.session_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY s2.user_id
                               ORDER BY s2.date, s2.id
                           ) AS new_batch_id
                    FROM (SELECT DISTINCT session_id FROM workout_sets) ws2
                    JOIN workout_sessions s2 ON ws2.session_id = s2.id
                ) mapping ON ws.session_id = mapping.session_id
                SET ws.batch_id = mapping.new_batch_id
            """))
            print("  Assigned batch_ids from session ordering")

            # 4. Add indexes
            for idx_name, idx_cols in [
                ("idx_workout_sets_user_id", "user_id"),
                ("idx_workout_sets_batch_id", "batch_id"),
                ("idx_workout_sets_set_date", "set_date"),
                ("idx_workout_sets_user_batch", "user_id, batch_id"),
            ]:
                try:
                    await session.execute(text(
                        f"CREATE INDEX {idx_name} ON workout_sets ({idx_cols})"
                    ))
                    print(f"  Created index {idx_name}")
                except Exception as e:
                    if "Duplicate key name" in str(e):
                        print(f"  Index {idx_name} already exists — skipping")
                    else:
                        raise

            # 5. Drop session_id FK and column
            try:
                # Find and drop the FK constraint
                fk_result = await session.execute(text("""
                    SELECT CONSTRAINT_NAME
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_NAME = 'workout_sets'
                      AND COLUMN_NAME = 'session_id'
                      AND REFERENCED_TABLE_NAME = 'workout_sessions'
                """))
                fk_rows = fk_result.fetchall()
                for row in fk_rows:
                    await session.execute(text(
                        f"ALTER TABLE workout_sets DROP FOREIGN KEY {row[0]}"
                    ))
                    print(f"  Dropped FK {row[0]}")

                # Drop old indexes that reference session_id
                for idx in ["idx_workout_sets_session", "idx_workout_sets_session_exercise"]:
                    try:
                        await session.execute(text(f"DROP INDEX {idx} ON workout_sets"))
                        print(f"  Dropped index {idx}")
                    except Exception:
                        pass

                await session.execute(text(
                    "ALTER TABLE workout_sets DROP COLUMN session_id"
                ))
                print("  Dropped session_id column")
            except Exception as e:
                if "check that column" in str(e).lower() or "Unknown column" in str(e):
                    print("  session_id column already removed — skipping")
                else:
                    raise

            # 6. Drop workout_sessions table
            await session.execute(text("DROP TABLE IF EXISTS workout_sessions"))
            print("  Dropped workout_sessions table")

        print("v0.5 migration complete!")
        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    success = asyncio.run(migrate())
    sys.exit(0 if success else 1)

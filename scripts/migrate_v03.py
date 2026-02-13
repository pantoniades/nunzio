#!/usr/bin/env python3
"""v0.3 migration: add raw_exercise_name column, create message_log table."""

import asyncio
import sys

from sqlalchemy import text

from nunzio.database.connection import db_manager


async def migrate():
    print("Running v0.3 migration...")

    try:
        await db_manager.initialize()

        async with db_manager.get_session() as session:
            # 1. Add raw_exercise_name to workout_sets (idempotent)
            try:
                await session.execute(text(
                    "ALTER TABLE workout_sets ADD COLUMN raw_exercise_name TEXT NULL"
                ))
                print("  Added raw_exercise_name column to workout_sets")
            except Exception as e:
                if "Duplicate column" in str(e):
                    print("  raw_exercise_name column already exists — skipping")
                else:
                    raise

            # 2. Create message_log table (idempotent)
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS message_log (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    user_id BIGINT NOT NULL,
                    raw_message TEXT NOT NULL,
                    classified_intent VARCHAR(50) NOT NULL,
                    confidence FLOAT NOT NULL,
                    extracted_data TEXT,
                    response_summary TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    INDEX idx_message_log_user_id (user_id),
                    INDEX idx_message_log_created_at (created_at)
                )
            """))
            print("  Created message_log table")

        print("v0.3 migration complete!")
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

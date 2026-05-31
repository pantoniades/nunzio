#!/usr/bin/env python3
"""v0.7 migration: add the user_settings table (per-user timezone).

Non-destructive and idempotent — only creates the new table if it doesn't
already exist. Safe to run against a live database with real data; it never
drops or alters existing tables.
"""

import asyncio
import sys

from nunzio.database.connection import db_manager
from nunzio.database.models import UserSettings


async def migrate():
    print("Running v0.7 migration: add user_settings table...")

    try:
        await db_manager.initialize()

        # checkfirst=True → CREATE TABLE IF NOT EXISTS semantics; existing tables
        # are left untouched.
        async with db_manager._engine.begin() as conn:
            await conn.run_sync(
                UserSettings.__table__.create, checkfirst=True
            )

        print("  user_settings table is present.")
        print("v0.7 migration complete!")
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

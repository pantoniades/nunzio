#!/usr/bin/env python3
"""Clear all data and re-seed exercises."""

import asyncio
import sys

from sqlalchemy import text

from nunzio.database.connection import db_manager
from scripts.seed_exercises import create_sample_exercises


async def clear_and_reseed():
    """Drop all data then seed fresh exercises."""
    print("Clearing existing data...")

    try:
        await db_manager.initialize()

        async with db_manager.get_session() as session:
            await session.execute(text("DELETE FROM workout_sets"))
            await session.execute(text("DELETE FROM workout_sessions"))
            await session.execute(text("DELETE FROM exercises"))
            await session.commit()
            print("Cleared all data.")

        # db_manager is still initialized; seed script will reuse it
        await db_manager.close()
        return await create_sample_exercises()

    except Exception as e:
        print(f"Failed to clear and reseed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    success = asyncio.run(clear_and_reseed())
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""Test database connectivity and basic CRUD operations."""

import asyncio
import sys

from nunzio.database.connection import db_manager
from nunzio.database.repository import exercise_repo, workout_set_repo


async def test_database():
    """Test database connectivity and basic operations."""
    print("Testing database connectivity...")

    try:
        # Test basic connectivity
        await db_manager.initialize()
        healthy = await db_manager.health_check()
        print(f"Database healthy: {healthy}")

        if not healthy:
            print("Database health check failed!")
            return False

        # Test basic query operations
        async with db_manager.get_session() as session:
            exercises = await exercise_repo.get_multi(session, limit=5)
            sets = await workout_set_repo.get_multi(session, limit=5)

            print(f"Found {len(exercises)} exercises")
            print(f"Found {len(sets)} workout sets")

            # Test create operation
            test_exercise = await exercise_repo.create(
                session, obj_in={"name": "Test Push-up", "muscle_group": "chest"}
            )
            print(f"Created exercise: {test_exercise}")

            # Test update operation
            updated_exercise = await exercise_repo.update(
                session,
                db_obj=test_exercise,
                obj_in={"description": "Classic push-up exercise"},
            )
            print(f"Updated exercise: {updated_exercise}")

            # Test get by name
            found_exercise = await exercise_repo.get_by_name(session, "Test Push-up")
            print(f"Found exercise by name: {found_exercise}")

            # Test delete operation
            deleted_exercise = await exercise_repo.delete(session, id=test_exercise.id)
            print(f"Deleted exercise: {deleted_exercise}")

        print("All database tests passed!")
        return True

    except Exception as e:
        print(f"Database test failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    success = asyncio.run(test_database())
    sys.exit(0 if success else 1)

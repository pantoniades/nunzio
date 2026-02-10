#!/usr/bin/env python3
"""Create (or recreate) database schema using SQLAlchemy models."""

import asyncio
import sys

from nunzio.database.connection import db_manager
from nunzio.database.models import Base


async def create_tables():
    """Drop and recreate all tables."""
    print("Creating database tables...")

    try:
        await db_manager.initialize()

        async with db_manager._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        print("Database tables created successfully!")

        from sqlalchemy import text

        async with db_manager.get_session() as session:
            result = await session.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            print(f"Tables: {tables}")

        return True

    except Exception as e:
        print(f"Failed to create tables: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    success = asyncio.run(create_tables())
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""Container health check for Nunzio — verifies the database is reachable."""
import asyncio
import sys

from nunzio.database.connection import db_manager


async def check_health():
    try:
        await db_manager.initialize()
        is_healthy = await db_manager.health_check()
        await db_manager.close()
        return 0 if is_healthy else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(check_health()))

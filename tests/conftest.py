import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://mcp:mcp_dev_password@localhost:5432/nba",
)

import asyncpg
import pytest_asyncio

from src import server


@pytest_asyncio.fixture(scope="session", autouse=True)
async def db_pool():
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=3)
    server._pool = pool
    try:
        yield pool
    finally:
        await pool.close()
        server._pool = None

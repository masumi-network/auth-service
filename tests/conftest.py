"""Shared test fixtures."""

import os

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/auth_service_test")
os.environ.setdefault("SOKOSUMI_OAUTH_CLIENT_ID", "test_client_id")
os.environ.setdefault("SOKOSUMI_OAUTH_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("SOKOSUMI_ENVIRONMENT", "preprod")
os.environ.setdefault("AUTH_SERVICE_URL", "http://localhost:8000")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_pool():
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def clean_tables(db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM channel_identities")
        await conn.execute("DELETE FROM tokens")
        await conn.execute("DELETE FROM oauth_state")
        await conn.execute("DELETE FROM users")
        await conn.execute("DELETE FROM agents")
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    from src.main import app
    from src.db import init_pool
    await init_pool()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

"""Test API key authentication."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src import repository
from src.db import init_pool
from src.main import app


@pytest_asyncio.fixture(autouse=True)
async def setup():
    await init_pool()
    await repository.create_agent("nori", "nori-secret-key", "Nori")


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_missing_api_key_returns_422(client):
    resp = await client.get("/api/v1/lookup", params={"channel": "email", "channel_id": "test"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401(client):
    resp = await client.get(
        "/api/v1/lookup",
        params={"channel": "email", "channel_id": "test"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401

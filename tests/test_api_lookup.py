"""Test the /api/v1/lookup endpoint."""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import ASGITransport, AsyncClient

from src import repository
from src.db import init_pool
from src.main import app

API_KEY = "nori-secret-key"
HEADERS = {"X-API-Key": API_KEY}


@pytest_asyncio.fixture(autouse=True)
async def setup():
    await init_pool()
    await repository.create_agent("nori", API_KEY, "Nori")


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_lookup_unknown_user(client):
    resp = await client.get(
        "/api/v1/lookup",
        params={"channel": "email", "channel_id": "nobody@test.com"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False
    assert "oauth_url" in data
    assert "channel=email" in data["oauth_url"]
    assert "agent_id=nori" in data["oauth_url"]


@pytest.mark.asyncio
async def test_lookup_authenticated_user(client):
    await repository.upsert_user("soko_abc", name="Alice", email="alice@test.com")
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    await repository.upsert_token("soko_abc", "access_tok", "refresh_tok", expires, "personal", None)
    await repository.link_channel("soko_abc", "email", "alice@test.com")
    resp = await client.get(
        "/api/v1/lookup",
        params={"channel": "email", "channel_id": "alice@test.com"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["sokosumi_user_id"] == "soko_abc"
    assert data["access_token"] == "access_tok"
    assert data["user"]["name"] == "Alice"


@pytest.mark.asyncio
async def test_lookup_case_insensitive(client):
    await repository.upsert_user("soko_abc")
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    await repository.upsert_token("soko_abc", "tok", "ref", expires)
    await repository.link_channel("soko_abc", "email", "Alice@Test.com")
    resp = await client.get(
        "/api/v1/lookup",
        params={"channel": "email", "channel_id": "alice@test.com"},
        headers=HEADERS,
    )
    assert resp.json()["authenticated"] is True


@pytest.mark.asyncio
async def test_get_user_by_id(client):
    await repository.upsert_user("soko_abc", name="Alice")
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    await repository.upsert_token("soko_abc", "tok", "ref", expires)
    resp = await client.get("/api/v1/users/soko_abc", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True


@pytest.mark.asyncio
async def test_get_unknown_user_returns_404(client):
    resp = await client.get("/api/v1/users/nonexistent", headers=HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_link_channel(client):
    await repository.upsert_user("soko_abc")
    resp = await client.post(
        "/api/v1/users/soko_abc/link",
        json={"channel": "telegram", "channel_identifier": "12345"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    user_id = await repository.lookup_by_channel("telegram", "12345")
    assert user_id == "soko_abc"


@pytest.mark.asyncio
async def test_get_oauth_url(client):
    resp = await client.get(
        "/api/v1/oauth-url",
        params={"channel": "telegram", "channel_id": "12345"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    url = resp.json()["oauth_url"]
    assert "channel=telegram" in url
    assert "channel_id=12345" in url
    assert "agent_id=nori" in url

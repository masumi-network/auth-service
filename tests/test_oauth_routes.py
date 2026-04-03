"""Test OAuth routes."""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient

from src import repository
from src.db import init_pool
from src.main import app


@pytest_asyncio.fixture(autouse=True)
async def setup():
    await init_pool()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as c:
        yield c


@pytest.mark.asyncio
async def test_oauth_start_redirects(client):
    resp = await client.get(
        "/oauth/start",
        params={"channel": "email", "channel_id": "alice@test.com", "agent_id": "nori"},
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "authorize" in location
    assert "code_challenge" in location
    assert "state" in location


@pytest.mark.asyncio
async def test_callback_missing_params(client):
    resp = await client.get("/oauth/callback")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_callback_expired_state(client):
    resp = await client.get("/oauth/callback", params={"code": "abc", "state": "nonexistent"})
    assert resp.status_code == 400
    assert "Expired" in resp.text


@pytest.mark.asyncio
async def test_confirm_stores_user_and_token():
    await init_pool()
    await repository.save_oauth_state("test_state", {
        "access_token": "acc_tok",
        "refresh_token": "ref_tok",
        "sokosumi_user_id": "soko_123",
        "token_expires_at": "2026-12-31T00:00:00+00:00",
        "channel": "telegram",
        "channel_id": "99999",
        "agent_id": "nori",
    })

    mock_profile = {"id": "soko_123", "name": "Alice", "email": "alice@test.com", "image": None}

    with patch("src.oauth.routes.fetch_user_profile", return_value=mock_profile):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
            resp = await client.get(
                "/oauth/confirm",
                params={"state": "test_state", "account_type": "personal"},
            )
            assert resp.status_code == 200
            assert "All Set" in resp.text

    user = await repository.get_user("soko_123")
    assert user.name == "Alice"
    assert user.email == "alice@test.com"

    token = await repository.get_token("soko_123")
    assert token.access_token == "acc_tok"
    assert token.workspace_type == "personal"

    assert await repository.lookup_by_channel("telegram", "99999") == "soko_123"
    assert await repository.lookup_by_channel("email", "alice@test.com") == "soko_123"
    assert await repository.lookup_by_channel("sokosumi", "soko_123") == "soko_123"


@pytest.mark.asyncio
async def test_confirm_links_email_from_profile():
    await init_pool()
    await repository.save_oauth_state("test_state2", {
        "access_token": "tok",
        "refresh_token": "ref",
        "sokosumi_user_id": "soko_456",
        "token_expires_at": "2026-12-31T00:00:00+00:00",
        "channel": "telegram",
        "channel_id": "77777",
        "agent_id": "xavi",
    })

    mock_profile = {"id": "soko_456", "name": "Bob", "email": "bob@test.com", "image": None}

    with patch("src.oauth.routes.fetch_user_profile", return_value=mock_profile):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/oauth/confirm", params={"state": "test_state2", "account_type": "personal"})

    assert await repository.lookup_by_channel("email", "bob@test.com") == "soko_456"
    assert await repository.lookup_by_channel("telegram", "77777") == "soko_456"

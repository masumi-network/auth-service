"""Test repository operations."""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from src import repository
from src.db import init_pool


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def setup_pool():
    await init_pool()


@pytest.mark.asyncio
async def test_create_and_verify_agent():
    await repository.create_agent("nori", "test-key-123", "Nori")
    agent_id = await repository.verify_api_key("test-key-123")
    assert agent_id == "nori"


@pytest.mark.asyncio
async def test_verify_invalid_api_key():
    result = await repository.verify_api_key("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_upsert_and_get_user():
    await repository.upsert_user("soko_abc", name="Alice", email="alice@example.com")
    user = await repository.get_user("soko_abc")
    assert user is not None
    assert user.name == "Alice"
    assert user.email == "alice@example.com"


@pytest.mark.asyncio
async def test_upsert_user_preserves_existing_fields():
    await repository.upsert_user("soko_abc", name="Alice", email="alice@example.com")
    await repository.upsert_user("soko_abc", name="Alice Updated")
    user = await repository.get_user("soko_abc")
    assert user.name == "Alice Updated"
    assert user.email == "alice@example.com"


@pytest.mark.asyncio
async def test_upsert_and_get_token():
    await repository.upsert_user("soko_abc")
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    token_id = await repository.upsert_token(
        "soko_abc", "access_123", "refresh_456", expires, "personal", None
    )
    assert token_id > 0
    token = await repository.get_token("soko_abc")
    assert token is not None
    assert token.access_token == "access_123"
    assert token.refresh_token == "refresh_456"
    assert token.status == "active"


@pytest.mark.asyncio
async def test_token_is_expiring():
    await repository.upsert_user("soko_abc")
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    await repository.upsert_token("soko_abc", "access_123", "refresh_456", expires)
    token = await repository.get_token("soko_abc")
    assert token.is_expiring(buffer_seconds=300) is True


@pytest.mark.asyncio
async def test_link_and_lookup_channel():
    await repository.upsert_user("soko_abc")
    created = await repository.link_channel("soko_abc", "email", "alice@example.com")
    assert created is True
    user_id = await repository.lookup_by_channel("email", "alice@example.com")
    assert user_id == "soko_abc"


@pytest.mark.asyncio
async def test_lookup_unknown_channel():
    result = await repository.lookup_by_channel("email", "nobody@example.com")
    assert result is None


@pytest.mark.asyncio
async def test_channel_lookup_case_insensitive():
    await repository.upsert_user("soko_abc")
    await repository.link_channel("soko_abc", "email", "Alice@Example.com")
    result = await repository.lookup_by_channel("email", "alice@example.com")
    assert result == "soko_abc"


@pytest.mark.asyncio
async def test_oauth_state_lifecycle():
    await repository.save_oauth_state("state123", {"code_verifier": "cv", "channel": "email"})
    data = await repository.load_oauth_state("state123")
    assert data is not None
    assert data["code_verifier"] == "cv"
    await repository.delete_oauth_state("state123")
    data = await repository.load_oauth_state("state123")
    assert data is None


@pytest.mark.asyncio
async def test_mark_token_refresh_failed():
    await repository.upsert_user("soko_abc")
    await repository.upsert_token("soko_abc", "access_123", "refresh_456")
    token = await repository.get_token("soko_abc")
    await repository.mark_token_refresh_failed(token.id, "error1")
    await repository.mark_token_refresh_failed(token.id, "error2")
    token = await repository.get_token("soko_abc")
    assert token.status == "expired"
    assert token.refresh_failure_count == 2
    await repository.mark_token_refresh_failed(token.id, "error3")
    token = await repository.get_token("soko_abc")
    assert token.status == "refresh_failed"
    assert token.refresh_failure_count == 3

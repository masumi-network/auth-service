"""Test token refresh logic."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src import repository
from src.db import init_pool
from src.token_refresh import ensure_valid_token


@pytest_asyncio.fixture(autouse=True)
async def setup_pool():
    await init_pool()


@pytest.mark.asyncio
async def test_valid_token_returned_as_is():
    await repository.upsert_user("soko_abc")
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    await repository.upsert_token("soko_abc", "valid_token", "refresh", expires)
    token = await repository.get_token("soko_abc")
    result = await ensure_valid_token(token)
    assert result.access_token == "valid_token"


@pytest.mark.asyncio
async def test_expiring_token_triggers_refresh():
    await repository.upsert_user("soko_abc")
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    await repository.upsert_token("soko_abc", "old_token", "refresh_tok", expires)
    token = await repository.get_token("soko_abc")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_token",
        "refresh_token": "new_refresh",
        "expires_in": 7200,
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await ensure_valid_token(token)
    assert result.access_token == "new_token"
    db_token = await repository.get_token("soko_abc")
    assert db_token.access_token == "new_token"
    assert db_token.status == "active"


@pytest.mark.asyncio
async def test_refresh_failed_raises():
    await repository.upsert_user("soko_abc")
    expires = datetime.now(timezone.utc) - timedelta(hours=1)
    await repository.upsert_token("soko_abc", "dead", "refresh", expires)
    token = await repository.get_token("soko_abc")
    for _ in range(3):
        await repository.mark_token_refresh_failed(token.id, "err")
    token = await repository.get_token("soko_abc")
    with pytest.raises(RuntimeError, match="permanently failed"):
        await ensure_valid_token(token)


@pytest.mark.asyncio
async def test_no_refresh_token_raises():
    await repository.upsert_user("soko_abc")
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    await repository.upsert_token("soko_abc", "access", None, expires)
    token = await repository.get_token("soko_abc")
    with pytest.raises(RuntimeError, match="No refresh token"):
        await ensure_valid_token(token)

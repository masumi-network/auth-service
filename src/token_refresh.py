"""Transparent Sokosumi token refresh."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from src.config import settings
from src.models import TokenRecord
from src import repository

logger = logging.getLogger(__name__)

_refresh_locks: dict[str, asyncio.Lock] = {}

REFRESH_BUFFER_SECONDS = 300


async def ensure_valid_token(token: TokenRecord) -> TokenRecord:
    """Return a valid token, refreshing if needed."""
    if not token.is_expiring(buffer_seconds=REFRESH_BUFFER_SECONDS):
        return token

    if token.status == "refresh_failed":
        raise RuntimeError(f"Token refresh permanently failed for {token.sokosumi_user_id}")

    if not token.refresh_token:
        raise RuntimeError(f"No refresh token for {token.sokosumi_user_id}")

    lock = _refresh_locks.setdefault(token.sokosumi_user_id, asyncio.Lock())
    async with lock:
        refreshed = await repository.get_token(token.sokosumi_user_id)
        if refreshed and not refreshed.is_expiring(buffer_seconds=REFRESH_BUFFER_SECONDS):
            return refreshed
        return await _do_refresh(token)


async def _do_refresh(token: TokenRecord) -> TokenRecord:
    """Execute the token refresh against Sokosumi."""
    logger.info(f"Refreshing token for {token.sokosumi_user_id}")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": token.refresh_token,
        "client_id": settings.sokosumi_oauth_client_id,
        "client_secret": settings.sokosumi_oauth_client_secret,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                settings.sokosumi_token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                error_msg = f"Token refresh failed: {resp.status_code} - {resp.text}"
                logger.error(error_msg)
                await repository.mark_token_refresh_failed(token.id, error_msg)
                raise RuntimeError(error_msg)
            result = resp.json()
    except httpx.RequestError as e:
        error_msg = f"Token refresh request error: {e}"
        logger.error(error_msg)
        await repository.mark_token_refresh_failed(token.id, error_msg)
        raise RuntimeError(error_msg) from e

    new_access = result.get("access_token")
    if not new_access:
        error_msg = "Refresh response missing access_token"
        await repository.mark_token_refresh_failed(token.id, error_msg)
        raise RuntimeError(error_msg)

    new_refresh = result.get("refresh_token", token.refresh_token)
    expires_in = result.get("expires_in", 7200)
    new_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    await repository.update_token_after_refresh(token.id, new_access, new_refresh, new_expires)
    logger.info(f"Token refreshed for {token.sokosumi_user_id}")
    return await repository.get_token(token.sokosumi_user_id)

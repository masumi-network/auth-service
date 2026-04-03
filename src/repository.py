"""Database operations for users, tokens, channel identities, and agents."""

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

from src.db import get_pool
from src.models import TokenRecord, UserInfo

logger = logging.getLogger(__name__)


async def verify_api_key(api_key: str) -> Optional[str]:
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT agent_id FROM agents WHERE api_key_hash = $1", key_hash,
        )
    return row["agent_id"] if row else None


async def create_agent(agent_id: str, api_key: str, display_name: str = None) -> None:
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO agents (agent_id, api_key_hash, display_name)
               VALUES ($1, $2, $3)
               ON CONFLICT (agent_id) DO UPDATE SET api_key_hash = $2, display_name = $3""",
            agent_id, key_hash, display_name,
        )


async def upsert_user(
    sokosumi_user_id: str, name: str = None, email: str = None, image_url: str = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO users (sokosumi_user_id, name, email, image_url)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (sokosumi_user_id) DO UPDATE SET
                   name = COALESCE($2, users.name),
                   email = COALESCE($3, users.email),
                   image_url = COALESCE($4, users.image_url),
                   updated_at = NOW()""",
            sokosumi_user_id, name, email, image_url,
        )


async def get_user(sokosumi_user_id: str) -> Optional[UserInfo]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name, email, image_url FROM users WHERE sokosumi_user_id = $1",
            sokosumi_user_id,
        )
    if not row:
        return None
    return UserInfo(name=row["name"], email=row["email"], image_url=row["image_url"])


async def upsert_token(
    sokosumi_user_id: str, access_token: str, refresh_token: str = None,
    token_expires_at: datetime = None, workspace_type: str = None, default_org_slug: str = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO tokens (
                   sokosumi_user_id, access_token, refresh_token,
                   token_expires_at, workspace_type, default_org_slug,
                   status, refresh_failure_count, last_refreshed_at
               ) VALUES ($1, $2, $3, $4, $5, $6, 'active', 0, NOW())
               ON CONFLICT (sokosumi_user_id) DO UPDATE SET
                   access_token = $2,
                   refresh_token = COALESCE($3, tokens.refresh_token),
                   token_expires_at = $4,
                   workspace_type = COALESCE($5, tokens.workspace_type),
                   default_org_slug = COALESCE($6, tokens.default_org_slug),
                   status = 'active',
                   refresh_failure_count = 0,
                   last_refreshed_at = NOW(),
                   updated_at = NOW()
               RETURNING id""",
            sokosumi_user_id, access_token, refresh_token,
            token_expires_at, workspace_type, default_org_slug,
        )
    return row["id"]


async def get_token(sokosumi_user_id: str) -> Optional[TokenRecord]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, sokosumi_user_id, access_token, refresh_token,
                      token_expires_at, workspace_type, default_org_slug,
                      status, refresh_failure_count, last_refreshed_at
               FROM tokens WHERE sokosumi_user_id = $1""",
            sokosumi_user_id,
        )
    if not row:
        return None
    return TokenRecord(**dict(row))


async def update_token_after_refresh(
    token_id: int, access_token: str, refresh_token: str = None, token_expires_at: datetime = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE tokens SET
                   access_token = $2,
                   refresh_token = COALESCE($3, refresh_token),
                   token_expires_at = $4,
                   status = 'active',
                   refresh_failure_count = 0,
                   last_refreshed_at = NOW(),
                   updated_at = NOW()
               WHERE id = $1""",
            token_id, access_token, refresh_token, token_expires_at,
        )


async def mark_token_refresh_failed(token_id: int, error: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE tokens SET
                   refresh_failure_count = refresh_failure_count + 1,
                   status = CASE
                       WHEN refresh_failure_count + 1 >= 3 THEN 'refresh_failed'
                       ELSE 'expired'
                   END,
                   updated_at = NOW()
               WHERE id = $1""",
            token_id,
        )


async def link_channel(
    sokosumi_user_id: str, channel: str, channel_identifier: str,
) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """INSERT INTO channel_identities (sokosumi_user_id, channel, channel_identifier)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (channel, channel_identifier) DO NOTHING""",
                sokosumi_user_id, channel, channel_identifier.lower(),
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to link channel {channel}:{channel_identifier}: {e}")
            return False


async def lookup_by_channel(channel: str, channel_identifier: str) -> Optional[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT sokosumi_user_id FROM channel_identities
               WHERE channel = $1 AND channel_identifier = $2""",
            channel, channel_identifier.lower(),
        )
    return row["sokosumi_user_id"] if row else None


async def save_oauth_state(state: str, data: dict) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO oauth_state (state, data, expires_at)
               VALUES ($1, $2::jsonb, NOW() + INTERVAL '30 minutes')
               ON CONFLICT (state) DO UPDATE SET
                   data = $2::jsonb, expires_at = NOW() + INTERVAL '30 minutes'""",
            state, json.dumps(data),
        )


async def load_oauth_state(state: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT data FROM oauth_state WHERE state = $1 AND expires_at > NOW()",
            state,
        )
    if not row:
        return None
    data = row["data"]
    return json.loads(data) if isinstance(data, str) else data


async def delete_oauth_state(state: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM oauth_state WHERE state = $1", state)

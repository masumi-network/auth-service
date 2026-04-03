"""Agent API routes."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query

from src import repository
from src.api.auth import require_agent
from src.config import settings
from src.models import LookupResult, UserInfo, LinkRequest
from src.token_refresh import ensure_valid_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _build_oauth_url(channel: str, channel_id: str, agent_id: str) -> str:
    params = urlencode({
        "channel": channel,
        "channel_id": channel_id,
        "agent_id": agent_id,
    })
    return f"{settings.auth_service_url}/oauth/start?{params}"


@router.get("/lookup")
async def lookup(
    channel: str = Query(),
    channel_id: str = Query(),
    agent_id: str = Depends(require_agent),
) -> LookupResult:
    sokosumi_user_id = await repository.lookup_by_channel(channel, channel_id)
    if not sokosumi_user_id:
        return LookupResult(
            authenticated=False,
            oauth_url=_build_oauth_url(channel, channel_id, agent_id),
        )

    token = await repository.get_token(sokosumi_user_id)
    if not token or token.status == "refresh_failed":
        return LookupResult(
            authenticated=False,
            oauth_url=_build_oauth_url(channel, channel_id, agent_id),
        )

    try:
        token = await ensure_valid_token(token)
    except RuntimeError:
        return LookupResult(
            authenticated=False,
            oauth_url=_build_oauth_url(channel, channel_id, agent_id),
        )

    user = await repository.get_user(sokosumi_user_id)
    return LookupResult(
        authenticated=True,
        sokosumi_user_id=sokosumi_user_id,
        access_token=token.access_token,
        workspace_type=token.workspace_type,
        default_org_slug=token.default_org_slug,
        user=user,
    )


@router.get("/users/{sokosumi_user_id}")
async def get_user(
    sokosumi_user_id: str,
    agent_id: str = Depends(require_agent),
) -> LookupResult:
    user = await repository.get_user(sokosumi_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    token = await repository.get_token(sokosumi_user_id)
    if not token:
        raise HTTPException(status_code=404, detail="No token for user")
    try:
        token = await ensure_valid_token(token)
    except RuntimeError:
        raise HTTPException(status_code=502, detail="Token refresh failed")
    return LookupResult(
        authenticated=True,
        sokosumi_user_id=sokosumi_user_id,
        access_token=token.access_token,
        workspace_type=token.workspace_type,
        default_org_slug=token.default_org_slug,
        user=user,
    )


@router.post("/users/{sokosumi_user_id}/link")
async def link_channel_identity(
    sokosumi_user_id: str,
    body: LinkRequest,
    agent_id: str = Depends(require_agent),
):
    user = await repository.get_user(sokosumi_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await repository.link_channel(sokosumi_user_id, body.channel, body.channel_identifier)
    return {"status": "linked"}


@router.get("/oauth-url")
async def get_oauth_url(
    channel: str = Query(),
    channel_id: str = Query(),
    agent_id: str = Depends(require_agent),
):
    return {"oauth_url": _build_oauth_url(channel, channel_id, agent_id)}

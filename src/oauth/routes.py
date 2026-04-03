"""OAuth routes: start, callback, select-account, confirm."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from src import repository
from src.oauth.sokosumi import (
    generate_pkce, build_authorize_url, exchange_code_for_tokens,
    fetch_user_profile, fetch_organizations, decode_id_token,
)
from src.oauth.pages import error_page, success_page, select_account_page

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/oauth")


@router.get("/start")
async def start(channel: str, channel_id: str, agent_id: str = "unknown", callback_url: str = None):
    pkce = generate_pkce()
    await repository.save_oauth_state(pkce["state"], {
        "code_verifier": pkce["code_verifier"],
        "channel": channel,
        "channel_id": channel_id,
        "agent_id": agent_id,
        "callback_url": callback_url,
    })
    url = build_authorize_url(pkce["code_challenge"], pkce["state"])
    logger.info(f"OAuth start: channel={channel}, agent={agent_id}, state={pkce['state'][:8]}...")
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
async def callback(code: str = None, state: str = None, error: str = None, error_description: str = None):
    if error:
        return HTMLResponse(error_page("OAuth Error", error_description or error))
    if not code or not state:
        return HTMLResponse(error_page("Missing Parameters", "Missing code or state."), status_code=400)

    oauth_state = await repository.load_oauth_state(state)
    if not oauth_state:
        return HTMLResponse(error_page("Session Expired", "Please start the connection again."), status_code=400)

    if "code_verifier" not in oauth_state:
        return RedirectResponse(f"/oauth/select-account?state={state}")

    try:
        tokens = await exchange_code_for_tokens(code, oauth_state["code_verifier"])
    except RuntimeError as e:
        return HTMLResponse(error_page("Token Exchange Failed", str(e)), status_code=500)

    access_token = tokens.get("access_token")
    if not access_token:
        return HTMLResponse(error_page("No Access Token", "Token exchange returned no access token."), status_code=500)

    sokosumi_user_id = None
    id_token = tokens.get("id_token")
    if id_token:
        claims = decode_id_token(id_token)
        if claims:
            sokosumi_user_id = claims.get("sub")

    expires_in = tokens.get("expires_in", 7200)
    token_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()

    flow_data = {
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token"),
        "sokosumi_user_id": sokosumi_user_id,
        "token_expires_at": token_expires_at,
        "channel": oauth_state["channel"],
        "channel_id": oauth_state["channel_id"],
        "agent_id": oauth_state.get("agent_id"),
        "callback_url": oauth_state.get("callback_url"),
    }
    await repository.save_oauth_state(state, flow_data)
    return RedirectResponse(f"/oauth/select-account?state={state}")


@router.get("/select-account")
async def select_account(state: str = None):
    if not state:
        return HTMLResponse(error_page("Missing State", "No state parameter."), status_code=400)

    flow_data = await repository.load_oauth_state(state)
    if not flow_data or "access_token" not in flow_data:
        return HTMLResponse(error_page("Session Expired", "Please start again."), status_code=400)

    access_token = flow_data["access_token"]

    try:
        if not flow_data.get("sokosumi_user_id"):
            profile = await fetch_user_profile(access_token)
            flow_data["sokosumi_user_id"] = profile["id"]
            await repository.save_oauth_state(state, flow_data)

        orgs = await fetch_organizations(access_token)
        if not orgs:
            return RedirectResponse(f"/oauth/confirm?state={state}&account_type=personal")
    except Exception as e:
        logger.error(f"Failed to fetch account data: {e}")
        orgs = []

    html = select_account_page(state, 0.0, orgs)
    return HTMLResponse(html)


@router.get("/confirm")
async def confirm(state: str, account_type: str, org_id: str = None):
    if account_type not in ("personal", "organization"):
        return HTMLResponse(error_page("Invalid Type", "Must be personal or organization."), status_code=400)

    flow_data = await repository.load_oauth_state(state)
    if not flow_data or "access_token" not in flow_data:
        return HTMLResponse(error_page("Session Expired", "Please start again."), status_code=400)

    access_token = flow_data["access_token"]
    refresh_token = flow_data.get("refresh_token")
    sokosumi_user_id = flow_data.get("sokosumi_user_id")
    channel = flow_data["channel"]
    channel_id = flow_data["channel_id"]
    callback_url = flow_data.get("callback_url")

    if not sokosumi_user_id:
        try:
            profile = await fetch_user_profile(access_token)
            sokosumi_user_id = profile["id"]
        except Exception as e:
            return HTMLResponse(error_page("Profile Fetch Failed", str(e)), status_code=500)

    try:
        profile = await fetch_user_profile(access_token)
    except Exception:
        profile = {"id": sokosumi_user_id, "name": "", "email": "", "image": None}

    org_slug = None
    org_name = None
    if account_type == "organization" and org_id:
        try:
            orgs = await fetch_organizations(access_token)
            for org in orgs:
                if str(org["id"]) == str(org_id):
                    org_slug = org["slug"]
                    org_name = org["name"]
                    break
        except Exception:
            pass

    token_expires_at = None
    if flow_data.get("token_expires_at"):
        token_expires_at = datetime.fromisoformat(flow_data["token_expires_at"])

    await repository.upsert_user(
        sokosumi_user_id, name=profile.get("name"),
        email=profile.get("email"), image_url=profile.get("image"),
    )
    await repository.upsert_token(
        sokosumi_user_id, access_token, refresh_token,
        token_expires_at, account_type, org_slug,
    )
    await repository.link_channel(sokosumi_user_id, channel, channel_id)

    if profile.get("email") and (channel != "email" or profile["email"].lower() != channel_id.lower()):
        await repository.link_channel(sokosumi_user_id, "email", profile["email"])

    await repository.link_channel(sokosumi_user_id, "sokosumi", sokosumi_user_id)
    await repository.delete_oauth_state(state)

    logger.info(f"OAuth complete: user={sokosumi_user_id}, channel={channel}:{channel_id}, workspace={account_type}")

    workspace_name = org_name if account_type == "organization" and org_name else "Personal Workspace"
    return HTMLResponse(success_page(workspace_name, redirect_url=callback_url))

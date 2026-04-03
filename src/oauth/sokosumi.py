"""Sokosumi OAuth helpers: PKCE, token exchange, user profile fetch."""

import base64
import hashlib
import json
import logging
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


def generate_pkce() -> dict:
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    return {
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "state": state,
    }


def build_authorize_url(code_challenge: str, state: str) -> str:
    params = {
        "client_id": settings.sokosumi_oauth_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{settings.sokosumi_authorize_url}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oauth_redirect_uri,
        "client_id": settings.sokosumi_oauth_client_id,
        "code_verifier": code_verifier,
    }
    if settings.sokosumi_oauth_client_secret:
        data["client_secret"] = settings.sokosumi_oauth_client_secret

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            settings.sokosumi_token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        logger.error(f"Token exchange failed: {resp.status_code} - {resp.text}")
        raise RuntimeError(f"Token exchange failed: {resp.status_code}")
    return resp.json()


async def fetch_user_profile(access_token: str) -> dict:
    url = f"{settings.sokosumi_api_base_url}/users/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"User profile fetch failed: {resp.status_code}")
    data = resp.json().get("data", {})
    return {
        "id": data.get("id", ""),
        "name": data.get("name", ""),
        "email": data.get("email", ""),
        "image": data.get("image"),
    }


async def fetch_organizations(access_token: str) -> list[dict]:
    url = f"{settings.sokosumi_api_base_url}/users/me/organizations"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    data = resp.json().get("data", [])
    orgs = []
    for org in data:
        credits_val = org.get("credits", 0)
        if isinstance(credits_val, dict):
            credits_val = credits_val.get("total", 0)
        orgs.append({
            "id": org.get("id", ""),
            "name": org.get("name", ""),
            "slug": org.get("slug", ""),
            "role": org.get("role", ""),
            "credits": float(credits_val) if credits_val else 0.0,
        })
    return orgs


def decode_id_token(id_token: str) -> Optional[dict]:
    try:
        parts = id_token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None

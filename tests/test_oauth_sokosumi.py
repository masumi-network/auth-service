"""Test OAuth Sokosumi helpers."""

import pytest
from src.oauth.sokosumi import generate_pkce, build_authorize_url, decode_id_token
from src.config import settings


def test_generate_pkce():
    pkce = generate_pkce()
    assert "code_verifier" in pkce
    assert "code_challenge" in pkce
    assert "state" in pkce
    assert len(pkce["code_verifier"]) > 40
    assert "=" not in pkce["code_challenge"]


def test_generate_pkce_unique():
    a = generate_pkce()
    b = generate_pkce()
    assert a["state"] != b["state"]
    assert a["code_verifier"] != b["code_verifier"]


def test_build_authorize_url():
    url = build_authorize_url("challenge123", "state456")
    assert settings.sokosumi_oauth_client_id in url
    assert "code_challenge=challenge123" in url
    assert "state=state456" in url
    assert "response_type=code" in url
    assert "S256" in url


def test_decode_id_token():
    import base64, json
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "user123"}).encode()).decode().rstrip("=")
    fake_token = f"header.{payload}.signature"
    claims = decode_id_token(fake_token)
    assert claims["sub"] == "user123"


def test_decode_invalid_id_token():
    assert decode_id_token("not.a.valid.token.at.all") is None
    assert decode_id_token("") is None

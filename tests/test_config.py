"""Test configuration loading."""

from src.config import settings


def test_settings_loaded():
    assert settings.sokosumi_oauth_client_id == "test_client_id"
    assert settings.sokosumi_environment == "preprod"


def test_sokosumi_urls_preprod():
    assert "preprod" in settings.sokosumi_authorize_url
    assert "preprod" in settings.sokosumi_token_url
    assert "preprod" in settings.sokosumi_api_base_url


def test_oauth_redirect_uri():
    assert settings.oauth_redirect_uri == "http://localhost:8000/oauth/callback"

"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    sokosumi_oauth_client_id: str
    sokosumi_oauth_client_secret: str
    sokosumi_environment: str = "production"
    auth_service_url: str = "http://localhost:8000"

    @property
    def sokosumi_authorize_url(self) -> str:
        if self.sokosumi_environment == "preprod":
            return "https://api.preprod.sokosumi.com/auth/oauth2/authorize"
        return "https://app.sokosumi.com/api/auth/oauth2/authorize"

    @property
    def sokosumi_token_url(self) -> str:
        if self.sokosumi_environment == "preprod":
            return "https://api.preprod.sokosumi.com/auth/oauth2/token"
        return "https://app.sokosumi.com/api/auth/oauth2/token"

    @property
    def sokosumi_api_base_url(self) -> str:
        if self.sokosumi_environment == "preprod":
            return "https://api.preprod.sokosumi.com/v1"
        return "https://api.sokosumi.com/v1"

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.auth_service_url}/oauth/callback"

    model_config = {"env_file": ".env"}


settings = Settings()

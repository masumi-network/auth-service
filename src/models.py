"""Pydantic models for request/response schemas."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from pydantic import BaseModel


class UserInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    image_url: Optional[str] = None


class LookupResult(BaseModel):
    authenticated: bool
    sokosumi_user_id: Optional[str] = None
    access_token: Optional[str] = None
    workspace_type: Optional[str] = None
    default_org_slug: Optional[str] = None
    user: Optional[UserInfo] = None
    oauth_url: Optional[str] = None


class LinkRequest(BaseModel):
    channel: str
    channel_identifier: str


class TokenRecord(BaseModel):
    """Internal model for token DB rows."""
    id: int
    sokosumi_user_id: str
    access_token: str
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    workspace_type: Optional[str] = None
    default_org_slug: Optional[str] = None
    status: str = "active"
    refresh_failure_count: int = 0
    last_refreshed_at: Optional[datetime] = None

    def is_expiring(self, buffer_seconds: int = 300) -> bool:
        if not self.token_expires_at:
            return False
        threshold = datetime.now(timezone.utc) + timedelta(seconds=buffer_seconds)
        return self.token_expires_at <= threshold

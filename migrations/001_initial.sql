-- Users table: one row per Sokosumi user
CREATE TABLE users (
    sokosumi_user_id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    image_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tokens table: one token per user (1:1)
CREATE TABLE tokens (
    id SERIAL PRIMARY KEY,
    sokosumi_user_id TEXT NOT NULL UNIQUE REFERENCES users(sokosumi_user_id) ON DELETE CASCADE,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,
    workspace_type TEXT,
    default_org_slug TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    refresh_failure_count INTEGER NOT NULL DEFAULT 0,
    last_refreshed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Channel identities: maps channel+identifier to a user
CREATE TABLE channel_identities (
    id SERIAL PRIMARY KEY,
    sokosumi_user_id TEXT NOT NULL REFERENCES users(sokosumi_user_id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    channel_identifier TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(channel, channel_identifier)
);

CREATE INDEX idx_channel_identities_lookup ON channel_identities(channel, channel_identifier);

-- Agents table: registered agents with API keys
CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY,
    api_key_hash TEXT NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- OAuth state: temporary storage for in-progress OAuth flows
CREATE TABLE oauth_state (
    state TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '30 minutes',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_oauth_state_expires ON oauth_state(expires_at);

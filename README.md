# Masumi Auth Service

Centralized Sokosumi OAuth and identity management for Masumi agents. Instead of each agent implementing its own OAuth flow, agents call this service to check if a user is authenticated and to get their current Sokosumi access token.

**Preprod:** `https://masumi-auth-service-preprod.up.railway.app`

## How it works

![Auth Flow Diagram](docs/auth-flow.png)

*[Open in Excalidraw](docs/auth-flow.excalidraw) for an editable version.*

### Detailed flow

```
User contacts agent          Agent                      Auth Service              Sokosumi
     |                         |                            |                       |
     |--- message ------------>|                            |                       |
     |                         |--- GET /api/v1/lookup ---->|                       |
     |                         |    channel=telegram        |                       |
     |                         |    channel_id=12345        |                       |
     |                         |    x-api-key: agent_key    |                       |
     |                         |                            |                       |
     |                         |<-- { authenticated: false, |                       |
     |                         |      oauth_url: "..." }    |                       |
     |                         |                            |                       |
     |<-- "Connect Sokosumi:   |                            |                       |
     |     <oauth_url>"        |                            |                       |
     |                         |                            |                       |
     |--- clicks link ---------|--------------------------->|                       |
     |                         |                            |--- authorize -------->|
     |                         |                            |<-- code --------------|
     |                         |                            |--- exchange code ---->|
     |                         |                            |<-- access_token ------|
     |                         |                            |                       |
     |                         |                            | stores: user, token,  |
     |                         |                            |   channel_identities  |
     |<-- "All set!" ----------|----------------------------|                       |
     |                         |                            |                       |
     |--- next message ------->|                            |                       |
     |                         |--- GET /api/v1/lookup ---->|                       |
     |                         |<-- { authenticated: true,  |                       |
     |                         |      access_token: "..." } |                       |
     |                         |                            |                       |
     |<-- normal response -----|                            |                       |
```

The user authenticates **once per channel**. After that, the auth service stores the token and returns it on every lookup. Token refresh is handled transparently by the auth service.

## Integrating your agent

### 1. Register your agent

Ask the auth-service admin to create an agent row in the database:

```sql
INSERT INTO agents (agent_id, api_key_hash, display_name)
VALUES (
    'your_agent',
    encode(sha256('your_secret_api_key'::bytea), 'hex'),
    'Your Agent Name'
);
```

Save the API key (`your_secret_api_key`) — the database only stores the hash.

### 2. Call the lookup endpoint

When a user contacts your agent, call the lookup endpoint to check if they're authenticated:

```bash
curl -H "x-api-key: your_secret_api_key" \
  "https://masumi-auth-service-preprod.up.railway.app/api/v1/lookup?channel=telegram&channel_id=12345"
```

**Response when user is NOT authenticated:**

```json
{
  "authenticated": false,
  "sokosumi_user_id": null,
  "access_token": null,
  "workspace_type": null,
  "default_org_slug": null,
  "user": null,
  "oauth_url": "https://masumi-auth-service-preprod.up.railway.app/oauth/start?channel=telegram&channel_id=12345&agent_id=your_agent"
}
```

Show the `oauth_url` to the user so they can connect their Sokosumi account.

**Response when user IS authenticated:**

```json
{
  "authenticated": true,
  "sokosumi_user_id": "soko_abc123",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "workspace_type": "personal",
  "default_org_slug": null,
  "user": {
    "name": "Alice",
    "email": "alice@example.com",
    "image_url": null
  },
  "oauth_url": null
}
```

Use the `access_token` to make Sokosumi API calls on behalf of the user. The auth service refreshes expired tokens automatically — the token you receive is always current.

### 3. Handle the response in your code

```python
import httpx

AUTH_SERVICE_URL = "https://masumi-auth-service-preprod.up.railway.app"
API_KEY = "your_secret_api_key"

async def check_user(channel: str, channel_id: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{AUTH_SERVICE_URL}/api/v1/lookup",
            headers={"x-api-key": API_KEY},
            params={"channel": channel, "channel_id": channel_id},
        )
        data = resp.json()

    if data["authenticated"]:
        # User is connected — proceed with their access_token
        token = data["access_token"]
        user_name = data["user"]["name"]
        print(f"Hello {user_name}!")
    else:
        # User needs to connect — show them the link
        print(f"Please connect: {data['oauth_url']}")
```

## API reference

All agent endpoints require the `x-api-key` header.

### `GET /api/v1/lookup`

Look up a user's authentication status by channel identity.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `channel` | query | yes | Channel name: `telegram`, `email`, `sokosumi`, or any custom string |
| `channel_id` | query | yes | User's identifier on that channel (telegram user ID, email address, etc.) |

Returns `LookupResult` (see response examples above).

### `GET /api/v1/users/{sokosumi_user_id}`

Get a specific user by their Sokosumi user ID (useful when you already know the ID).

Returns `LookupResult` with `authenticated: true`, or 404 if not found.

### `POST /api/v1/users/{sokosumi_user_id}/link`

Manually link a new channel identity to an existing user.

```json
{
  "channel": "discord",
  "channel_identifier": "alice#1234"
}
```

Returns `{"status": "linked"}`.

### `GET /api/v1/oauth-url`

Generate an OAuth URL without performing a lookup. Useful when you want to build a "connect" button without checking auth status first.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `channel` | query | yes | Channel name |
| `channel_id` | query | yes | User's channel identifier |

Returns `{"oauth_url": "https://..."}`.

### `GET /health`

Health check. Returns `{"status": "ok"}`.

## Supported channels

The `channel` parameter is a free-form string — you can use any value. Common ones:

| Channel | `channel_id` format | Example |
|---------|---------------------|---------|
| `telegram` | Telegram user ID (numeric string) | `"308759795"` |
| `email` | Email address | `"alice@example.com"` |
| `sokosumi` | Sokosumi user ID | `"soko_abc123"` |
| `discord` | Discord user ID | `"123456789012345678"` |
| `whatsapp` | Phone number | `"+1234567890"` |

## Cross-channel identity linking

When a user completes OAuth via any channel, the auth service automatically links their **email from the Sokosumi profile** as an additional channel identity. This means:

- User authenticates via Telegram -> their email is also linked
- Another agent later receives an email from the same address -> lookup finds them, no re-auth needed

**Limitation:** The reverse doesn't work automatically. If a user authenticates via email first and later contacts via Telegram, the auth service has no way to know their Telegram user ID until they authenticate on that channel. Each channel requires one-time OAuth unless the agent manually links identities via `POST /api/v1/users/{id}/link`.

## Environment variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/dbname` |
| `SOKOSUMI_OAUTH_CLIENT_ID` | OAuth client ID from Sokosumi | `yHatDzZU...` |
| `SOKOSUMI_OAUTH_CLIENT_SECRET` | OAuth client secret from Sokosumi | `soko_client_secret_...` |
| `SOKOSUMI_ENVIRONMENT` | `preprod` or `production` | `preprod` |
| `AUTH_SERVICE_URL` | Public URL of this service (used to build OAuth callback URLs) | `https://masumi-auth-service-preprod.up.railway.app` |

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your values
uvicorn src.main:app --reload
```

The service runs on port 8000 by default (or `$PORT` if set).

## Running tests

```bash
pip install pytest pytest-asyncio
pytest -v
```

## Deployment

Deployed on Railway. The `Dockerfile` and `railway.toml` are ready for Railway's auto-deploy.

**Important:** Railway sets `PORT` dynamically (usually 8080). Make sure the service's **target port** in Railway networking matches what uvicorn binds to (check the deploy logs for "Uvicorn running on http://0.0.0.0:XXXX").

### Registering a Sokosumi OAuth client

Before deploying, register an OAuth client in the Sokosumi dashboard:

1. Go to Sokosumi dashboard (preprod or production)
2. Create a new OAuth application
3. Set the callback URL to: `https://<your-railway-domain>/oauth/callback`
4. Copy the client ID and secret into the Railway environment variables

## Database

Uses PostgreSQL. Migrations run automatically on startup.

### Tables

| Table | Purpose |
|-------|---------|
| `agents` | Registered agents with hashed API keys |
| `users` | Sokosumi user profiles (id, name, email) |
| `tokens` | OAuth tokens (access, refresh, expiry, workspace type) |
| `channel_identities` | Maps (channel, channel_id) to sokosumi_user_id |
| `oauth_state` | Temporary PKCE state during OAuth flow (auto-expires) |

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

## Connecting a new agent (step-by-step)

Follow these steps to connect any agent — in any language, on any platform — to the auth service.

### Step 1: Generate an API key

Generate a random, URL-safe API key for your agent. Example using Python:

```bash
python3 -c "import secrets; print('myagent_' + secrets.token_urlsafe(32))"
# Output: myagent_Ab3xK9mP7qR2sT5vW8yZ...
```

Save this key somewhere safe. You will need it in steps 2 and 4.

### Step 2: Register your agent in the auth-service database

Ask the auth-service admin to run this SQL against the auth-service Postgres:

```sql
INSERT INTO agents (agent_id, api_key_hash, display_name)
VALUES (
    'myagent',
    encode(sha256('myagent_Ab3xK9mP7qR2sT5vW8yZ...'::bytea), 'hex'),
    'My Agent'
);
```

Replace `myagent` with your agent's ID and the key string with your actual key from Step 1. The database stores only the SHA-256 hash — the plaintext key is never persisted.

### Step 3: Verify your key works

```bash
curl -H "x-api-key: myagent_Ab3xK9mP7qR2sT5vW8yZ..." \
  "https://masumi-auth-service-production.up.railway.app/api/v1/lookup?channel=test&channel_id=test123"
```

Expected response (user doesn't exist yet, so `authenticated: false`):

```json
{
  "authenticated": false,
  "oauth_url": "https://masumi-auth-service-production.up.railway.app/oauth/start?channel=test&channel_id=test123&agent_id=myagent"
}
```

If you get `401`, your key doesn't match the hash in the database. Re-check Step 2.

### Step 4: Add the auth check to your agent code

In your agent's message handler, before processing any user message, call the lookup endpoint:

```python
import httpx

AUTH_SERVICE_URL = "https://masumi-auth-service-production.up.railway.app"
API_KEY = "myagent_Ab3xK9mP7qR2sT5vW8yZ..."  # from Step 1

async def handle_message(channel: str, channel_id: str, message: str):
    """Called when a user sends your agent a message."""
    
    # 1. Check if user is authenticated
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{AUTH_SERVICE_URL}/api/v1/lookup",
            headers={"x-api-key": API_KEY},
            params={"channel": channel, "channel_id": channel_id},
        )
        auth = resp.json()

    # 2. Handle unauthenticated users
    if not auth["authenticated"]:
        return f"Please connect your Sokosumi account first: {auth['oauth_url']}"

    # 3. Proceed normally — user is authenticated
    sokosumi_user_id = auth["sokosumi_user_id"]
    access_token = auth["access_token"]  # fresh Sokosumi token, ready to use
    user_name = auth["user"]["name"]
    
    return f"Hello {user_name}! Processing: {message}"
```

The `channel` and `channel_id` parameters identify the user on whatever platform your agent runs on:

| If your agent runs on... | `channel` | `channel_id` |
|---|---|---|
| Telegram | `"telegram"` | Telegram user ID (e.g., `"308759795"`) |
| Email | `"email"` | Email address (e.g., `"alice@example.com"`) |
| Discord | `"discord"` | Discord user ID |
| Slack | `"slack"` | Slack user ID |
| Web app | `"web"` | Session ID or user ID from your app |
| Sokosumi task board | `"sokosumi"` | Sokosumi user ID from `X-Sokosumi-User-Id` header |

### Step 5: That's it

The auth service handles everything else:
- **First-time users** get an OAuth link. They click it, log in to Sokosumi, and return to a confirmation page. The auth service stores their token and links their channel identity.
- **Returning users** are found instantly by `(channel, channel_id)` lookup. The auth service returns a fresh `access_token` (refresh is handled server-side).
- **Cross-channel linking** happens automatically: when a user authenticates via any channel, their email from the Sokosumi profile is also linked. So if they later contact a different agent via email, they're already authenticated.

### Quick checklist

- [ ] Generated an API key (Step 1)
- [ ] Agent row seeded in auth-service DB (Step 2)
- [ ] Verified the key works with curl (Step 3)
- [ ] Added auth check to your message handler (Step 4)
- [ ] Stored `AUTH_SERVICE_URL` and your API key as env vars (not hardcoded)

---

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

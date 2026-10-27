# Plane MCP Connect web portal

Plane MCP Connect is a public setup surface at `/mcp-connect/`. It lets a user validate a Plane Personal API Key, create a revocable bearer URL, inspect the live MCP tool registry, execute tools, and watch sanitized request activity.

## Architecture

```text
Public HTTPS gateway
  -> /mcp-connect/          Plane web app
  -> /api/mcp-connect/*     Django connection API
  -> /mcp/c/<opaque token>  existing Plane Streamable HTTP MCP server
  -> /api/v1/*              Plane REST API
  -> PostgreSQL             Plane data and connection metadata
```

The portal does not create a second MCP server. Personal URLs are routed to the existing stateless MCP application. Before dispatch, the URL token is hashed and looked up, its Plane credential is decrypted, and the request receives that connection's credential. There is no process-wide mutable API key.

## Credential model

- The connection token is 256 bits of cryptographically random data.
- PostgreSQL stores only its SHA-256 lookup hash.
- The Plane Personal API Key is encrypted with Fernet using key material derived from Django `SECRET_KEY` and a portal-specific context string.
- The browser receives the bearer URL once and keeps the active token in an HttpOnly, SameSite=Strict cookie. It is never written to localStorage.
- API keys and personal MCP URLs are excluded from activity events.
- Connections expire after `MCP_CONNECTION_TTL_HOURS`, which defaults to 168 hours, and can be revoked or regenerated immediately.

Changing Django `SECRET_KEY` invalidates encrypted credentials. Recreate demo connections after such a rotation.

## Start locally on Windows with Docker Desktop

From PowerShell at the repository root:

```powershell
./setup.sh
docker compose up --build
```

If using the repository's local development stack, start its dependencies and run the normal web and API development commands described in the root README. Open the configured Plane URL and append `/mcp-connect/`.

For the default HTTP configuration, the page is commonly available at `http://localhost/mcp-connect/`. The API is proxied under `/api/`, and `/mcp/*` is sent only to the API container.

Apply migrations before first use:

```powershell
docker compose run --rm api python manage.py migrate
```

## Cloudflare Tunnel

Do not expose PostgreSQL, Redis, Docker Desktop, MinIO, or administration ports. The tunnel origin must be the Plane reverse proxy only, so the public hostname exposes the web portal, `/api/*`, and `/mcp/*` through one HTTPS origin.

After the operator explicitly approves public exposure:

```powershell
cloudflared tunnel login
cloudflared tunnel create plane-mcp-demo
cloudflared tunnel route dns plane-mcp-demo plane-demo.example.edu
cloudflared tunnel run --url http://localhost:80 plane-mcp-demo
```

Use a named tunnel configuration for repeatable demonstrations. Set Plane's public `WEB_URL` to the HTTPS hostname, add the hostname to `MCP_ALLOWED_HOSTS`, restart the API service, and create new personal URLs after the public hostname is active.

## API surface

- `POST /api/mcp-connect/test/`
- `POST /api/mcp-connect/connections/`
- `GET /api/mcp-connect/status/`
- `POST /api/mcp-connect/regenerate/`
- `POST /api/mcp-connect/revoke/`
- `GET /api/mcp-connect/tools/`
- `POST /api/mcp-connect/tools/test/`
- `GET /api/mcp-connect/activity/`

Write tools require `confirm_write: true`. Portal tool tests are restricted to the workspace saved with the connection.

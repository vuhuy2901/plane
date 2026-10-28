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
- Connections expire after `MCP_CONNECTION_TTL_HOURS`, which defaults to 168 hours, and can be revoked or regenerated immediately. Each connection may store its own public base URL; changing it never rotates the connection token or Plane credential.

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

Use a named tunnel configuration for repeatable demonstrations. Set Plane's public `WEB_URL` to the HTTPS hostname and add the exact hostname to `MCP_ALLOWED_HOSTS`. If the client sends an `Origin` header, add that exact origin to `MCP_ALLOWED_ORIGINS` (for ChatGPT web, `https://chatgpt.com`). Keep the local origins needed by your web client in the list as well. Recreate the API container after changing its `.env`; a plain `docker compose restart` retains the old environment. Create new personal URLs after the public hostname is active.

When Plane itself remains at localhost, set `MCP_PUBLIC_BASE_URL` to the tunnel's HTTPS origin as the server-wide default. A user can override that default while creating a connection or later through **Dashboard → Edit Public URL**. The saved per-connection value takes precedence and survives refreshes. Clearing it returns the connection to the server default. The generated URL is always `{public-base}/mcp/c/{connection-token}`.

For the local development stack, the API service already runs `plane.asgi:application` with Uvicorn. A separate host `manage.py runserver` on port 8000 can intercept requests and does not route `/mcp/c/*` to MCP. Stop any duplicate host server, then send the tunnel to the API service's port 8000. A quick tunnel hostname changes when the tunnel is restarted, so update the exact host allowlist and recreate the API service each time.

If ChatGPT says the server cannot complete MCP setup, check the HTTP response to `initialize` and `tools/list` through the public URL. `Invalid Host header` in the API log means the tunnel hostname is missing from `MCP_ALLOWED_HOSTS`; HTTP 403 with an `Origin` header means the client origin is missing from `MCP_ALLOWED_ORIGINS`. A successful probe returns HTTP 200 with Plane server information and a nonempty tools list.

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

# Plane MCP server

Plane exposes a Model Context Protocol server over Streamable HTTP at
`https://<your-plane-host>/mcp/`. It uses the same API v1 permissions,
validation, rate limits, activity logging, and webhook behavior as other Plane
API clients.

## Authentication

Create a Plane Personal Access Token and send it as a bearer token:

```http
Authorization: Bearer <plane-personal-access-token>
```

`X-Api-Key` is also accepted for compatibility with existing Plane API
clients. If both headers are present, they must contain the same token. Do not
commit a token to the repository or a shared MCP configuration.

## Client configuration

Use an HTTP MCP client and point it at the public Plane URL. The exact config
file varies by client; the connection values are:

```json
{
  "url": "https://plane.example.com/mcp/",
  "headers": {
    "Authorization": "Bearer ${PLANE_API_TOKEN}"
  }
}
```

The server exposes tools for listing workspaces; listing, reading, creating,
and updating projects; and listing, reading, creating, and updating work
items. Mutations only succeed when the PAT owner has the corresponding Plane
role.

## Deployment settings

DNS rebinding protection is enabled. Plane derives allowed MCP hosts from
`WEB_URL`, `APP_BASE_URL`, and `API_BASE_URL`, and derives browser origins from
`CORS_ALLOWED_ORIGINS`. Override the derived values when needed:

```dotenv
MCP_ALLOWED_HOSTS="plane.example.com,plane.example.com:*"
MCP_ALLOWED_ORIGINS="https://agent.example.com"
```

`MCP_ALLOWED_ORIGINS` is only needed for browser-based clients that send an
`Origin` header. Non-browser MCP clients normally omit it.

# Plane MCP Connect test results

This file records commands and observed results for the current working tree. It must not be interpreted as proof of a ChatGPT connection unless an actual ChatGPT workspace test is recorded explicitly.

## Automated coverage

The backend suite covers credential validation, invalid keys, invalid workspaces, encrypted storage, hashed token lookup, browser refresh through the HttpOnly cookie, revocation, expiry, credential isolation across concurrent connection records, and MCP initialization through a generated personal route.

The existing MCP tests continue to cover tool registration, schemas, payload mapping, API-key authentication, and direct `/mcp/` initialization.

## Verification log

- `docker compose -f docker-compose-test.yml run --rm --build api-tests pytest plane/tests/unit/mcp/test_connections.py -q`
  - Result: 11 passed, including per-connection public URL persistence/update, token and credential stability, invalid URL rejection, connection isolation, expired/revoked behavior, and MCP initialization.
- Live ngrok protocol probe through `https://geopolitical-anthropomorphously-rosena.ngrok-free.dev`
  - Result: MCP `initialize` succeeded and `tools/list` returned 14 tools. The ephemeral connection was deleted after the probe.
- `python manage.py migrate`
  - Result: migration `db.0135_mcp_connection_public_base_url` applied successfully to the local development database.

- `docker compose -f docker-compose-local.yml exec -T api pytest plane/tests/unit/mcp -q`
  - Result: 19 passed in the initial portal verification run; the project-picker regression test also passes in the focused connection suite.
- `docker compose -f docker-compose-local.yml exec -T api python manage.py makemigrations --check --dry-run`
  - Result: no model changes detected.
- `docker compose -f docker-compose-local.yml exec -T api python manage.py migrate db 0134`
  - Result: migration command completed successfully against the local development database.
- `uv run ruff check` on the changed backend modules and tests
  - Result: all checks passed.
- `pnpm exec oxlint apps/web/app/mcp-connect/page.tsx apps/web/app/layout.tsx --deny-warnings`
  - Result: no warnings or errors.
- `pnpm exec oxfmt --check` on the changed frontend files
  - Result: formatting check passed.
- `pnpm --filter web run check:types`
  - Result: passed. The local Node.js 22.19.0 installation is older than the repository's requested 22.22.0 minimum, but type checking completed successfully.
- `pnpm --filter web run build`
  - Result: client and SSR builds passed, with the same Node.js version warning and existing bundle-size warnings.
- `GET http://localhost:8000/api/mcp-connect/status/`
  - Result: HTTP 200 with the expected disconnected response.
- Invalid API-key request to `POST http://localhost:8000/api/mcp-connect/test/`
  - Result: HTTP 401 as expected.
- `git diff --check`
  - Result: passed; Git reported only existing line-ending conversion notices.

The native browser automation bridge was unavailable during verification, so no visual browser click-through is claimed. The responsive layout was covered by implementation review and frontend compilation only.

## Public ChatGPT MCP setup diagnosis

On 27 October 2026, the public Cloudflare tunnel initially reached the MCP application but `initialize` was rejected because the tunnel hostname was absent from `MCP_ALLOWED_HOSTS`. A probe with `Origin: https://chatgpt.com` then returned HTTP 403 because that origin was absent from `MCP_ALLOWED_ORIGINS`. After adding both exact values and recreating the API container, an ephemeral test connection returned HTTP 200 for `initialize` and HTTP 200 with 14 tools for `tools/list` through the public HTTPS tunnel. The ephemeral connection was revoked after the test. This does not assert that ChatGPT's own connection setup has been retried successfully.

Later on 27 October 2026, the configured default and allowlists were moved to the fixed ngrok hostname. A fresh ephemeral personal connection completed the full MCP handshake and discovered 14 tools through that ngrok URL. This verifies public routing and MCP protocol behavior, but not ChatGPT workspace policy or UI setup.

## Manual checks still required for a deployed demo

- Real task creation and retrieval in the disposable project
- Actual ChatGPT plan access, tool scan, and invocation
- Desktop and mobile review in the target browsers

ChatGPT integration has not been claimed solely from unit or Inspector tests.

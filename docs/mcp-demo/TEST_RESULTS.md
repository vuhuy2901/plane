# Plane MCP Connect test results

This file records commands and observed results for the current working tree. It must not be interpreted as proof of a ChatGPT connection unless an actual ChatGPT workspace test is recorded explicitly.

## Automated coverage

The backend suite covers credential validation, invalid keys, invalid workspaces, encrypted storage, hashed token lookup, browser refresh through the HttpOnly cookie, revocation, expiry, credential isolation across concurrent connection records, and MCP initialization through a generated personal route.

The existing MCP tests continue to cover tool registration, schemas, payload mapping, API-key authentication, and direct `/mcp/` initialization.

## Verification log

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

## Manual checks still required for a deployed demo

- Public HTTPS routing through the approved tunnel hostname
- MCP Inspector against that public generated URL
- Real task creation and retrieval in the disposable project
- Actual ChatGPT plan access, tool scan, and invocation
- Desktop and mobile review in the target browsers

ChatGPT integration has not been claimed solely from unit or Inspector tests.

# Plane database and MCP setup for agents

This is the operational guide for an AI agent working with the local Plane
database. It covers Docker PostgreSQL, the checked-in SQL seed, and the Plane
MCP bridge. It does not grant access to production data.

## Safety rules

1. Treat `backups/plane_database_backup.sql` as a local development seed, not
   a production backup. It may contain users, email addresses, password
   hashes, and historical API-token rows.
2. Never commit a Personal API Token, MCP bearer URL, `.env`, or database
   password. The checked-in MCP config uses `${PLANE_API_TOKEN}` and the value
   must be supplied only in the local process environment.
3. Restore only into the local Docker database after confirming the target
   container and database name. Restore uses `--clean --if-exists`.
4. Prefer MCP read tools first. MCP is an application API, not a raw SQL
   console. Do not edit PostgreSQL tables directly from an agent.

## Local services

`docker-compose-local.yml` defines:

| Service       | Purpose                               | Local port |
| ------------- | ------------------------------------- | ---------- |
| `plane-db`    | PostgreSQL database `plane`           | `5432`     |
| `api`         | Django/ASGI API and HTTP MCP endpoint | `8000`     |
| `worker`      | Celery background jobs and automation | internal   |
| `beat-worker` | Scheduled jobs                        | internal   |

Start the local stack:

```powershell
docker compose -f docker-compose-local.yml up -d plane-db api worker beat-worker
```

The API reads `apps/api/.env`. Create it from `.env.example` as described by
the repository setup instructions. Never commit the generated file.

## Exporting the database

Use the repository scripts; they wait for PostgreSQL and run `pg_dump` inside
the `plane-db` container:

```powershell
pnpm db:backup
# or .\backups\backup_docker_data.ps1
```

```bash
pnpm db:backup
# or bash backups/backup_docker_data.sh
```

The output is `backups/plane_database_backup.sql`. The repository scripts
exclude data from API-token, MCP-connection, session, webhook, integration,
and API-activity-log tables while retaining their schema. Review the file
size, diff, and secret scan before committing. Other local user/project data
may still be present.

## Restoring a local database

Restore is destructive to the target local database:

```powershell
.\backups\restore_docker_data.ps1
```

```bash
bash backups/restore_docker_data.sh
```

Restart API and workers after restore:

```powershell
docker compose -f docker-compose-local.yml restart api worker beat-worker
```

If model code is newer than the dump, apply migrations from the API image:

```powershell
docker compose -f docker-compose-local.yml exec -T api uv run python manage.py migrate
```

Never restore against a production `DATABASE_URL` or an unknown Docker volume.

## MCP configuration

`.agents/mcp_config.json` is a checked-in template and contains no token. Set
the token in the agent process environment:

```powershell
$env:PLANE_API_TOKEN = "<local-personal-api-token>"
uv run --directory apps/api python -m scripts.plane_stdio_mcp
```

The stdio bridge forwards registered Plane tools to `http://localhost:8000/mcp/`.
It fails explicitly when `PLANE_API_TOKEN` is missing; it has no repository
fallback credential. Use the least-privileged token possible and revoke any
token that has appeared in source, logs, or a shared backup.

## Agent read/write protocol

Before a mutation, an agent must:

1. Call `plane_list_workspaces` and confirm the workspace slug.
2. Call `plane_list_projects` and confirm the project UUID.
3. Read states, members, and the target work item.
4. Use the narrowest MCP write tool and read the object again to verify it.
5. For schema changes, edit code and migrations first; never patch tables
   directly.

An agent may run backup scripts and report the resulting file size/checksum. It
must not publish credentials or silently restore over an existing database.

## Verification

```powershell
docker compose -f docker-compose-local.yml exec -T plane-db pg_isready -U plane
docker compose -f docker-compose-local.yml exec -T api uv run python manage.py showmigrations --plan
git diff --check
git status --short
```

For backend tests involving changed model fields, use the isolated test
database with `--create-db`; the reused test database may have an old schema:

```powershell
docker compose -f docker-compose-local.yml exec -T api `
  pytest plane/tests/unit -q --create-db
```

## Git handoff

Commit only intended source, documentation, and backup files. Do not add
`.env`, local MCP configs, token files, or unrelated database dumps:

```powershell
git diff --check
git add backups/plane_database_backup.sql backups/README.md `
  docs/database/AGENT_DATABASE_SETUP.md .agents/mcp_config.json `
  apps/api/scripts/plane_stdio_mcp.py .gitignore
git commit -m "docs: add agent database and MCP setup"
git push origin <branch-name>
```

If a full SQL dump is not approved for the remote repository, keep the dump
local and push only the scripts and this guide.

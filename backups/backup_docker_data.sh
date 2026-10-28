#!/usr/bin/env bash
# ==============================================================================
# Script backup Plane Postgres database to SQL backup (Linux / macOS / WSL)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_FILE="$SCRIPT_DIR/plane_database_backup.sql"

echo "======================================================"
echo " BACKING UP PLANE DOCKER DATABASE"
echo "======================================================"

cd "$PROJECT_ROOT"
echo "[1/2] Starting plane-db container..."
docker compose -f docker-compose-local.yml up -d plane-db

echo "Waiting for PostgreSQL to be ready..."
until docker compose -f docker-compose-local.yml exec -T plane-db pg_isready -U plane > /dev/null 2>&1; do
    sleep 1
done

echo "[2/2] Dumping database to $BACKUP_FILE..."
CONTAINER_ID=$(docker compose -f docker-compose-local.yml ps -q plane-db | tr -d '[:space:]')
SENSITIVE_TABLES=(
    api_tokens api_activity_logs mcp_connections mcp_connection_events sessions
    social_login_connections integrations workspace_integrations
    github_repositories github_repository_syncs github_issue_syncs github_comment_syncs
    slack_project_syncs webhooks webhook_logs project_webhooks
)
DUMP_ARGS=(pg_dump -U plane -d plane --clean --if-exists)
for table in "${SENSITIVE_TABLES[@]}"; do
    DUMP_ARGS+=("--exclude-table-data=$table")
done
DUMP_ARGS+=(-f /tmp/plane_backup_temp.sql)
docker exec "$CONTAINER_ID" "${DUMP_ARGS[@]}"
docker cp "${CONTAINER_ID}:/tmp/plane_backup_temp.sql" "$BACKUP_FILE"
docker exec "$CONTAINER_ID" rm -f /tmp/plane_backup_temp.sql

SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "======================================================"
echo " BACKUP COMPLETED SUCCESSFULLY!"
echo " File: $BACKUP_FILE ($SIZE)"
echo "======================================================"

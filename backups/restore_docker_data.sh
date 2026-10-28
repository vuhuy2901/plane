#!/usr/bin/env bash
# ==============================================================================
# Script restore Plane Postgres database from SQL backup (Linux / macOS / WSL)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_FILE="$SCRIPT_DIR/plane_database_backup.sql"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found at $BACKUP_FILE"
    exit 1
fi

echo "======================================================"
echo " RESTORING PLANE DOCKER DATABASE FROM SEED BACKUP"
echo "======================================================"

cd "$PROJECT_ROOT"
echo "[1/2] Starting plane-db container..."
docker compose -f docker-compose-local.yml up -d plane-db

echo "Waiting for PostgreSQL to be ready..."
until docker compose -f docker-compose-local.yml exec -T plane-db pg_isready -U plane > /dev/null 2>&1; do
    sleep 1
done

echo "[2/2] Restoring database from $BACKUP_FILE..."
CONTAINER_ID=$(docker compose -f docker-compose-local.yml ps -q plane-db | tr -d '[:space:]')
docker cp "$BACKUP_FILE" "${CONTAINER_ID}:/tmp/plane_restore_temp.sql"
docker exec "$CONTAINER_ID" psql -U plane -d plane -f /tmp/plane_restore_temp.sql > /dev/null 2>&1
docker exec "$CONTAINER_ID" rm -f /tmp/plane_restore_temp.sql

echo "======================================================"
echo " DATABASE RESTORE COMPLETED SUCCESSFULLY!"
echo " Pre-seeded data (Workspaces, Projects, Issues, Users) is ready."
echo "======================================================"

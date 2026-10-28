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
docker exec "$CONTAINER_ID" pg_dump -U plane -d plane --clean --if-exists -f /tmp/plane_backup_temp.sql
docker cp "${CONTAINER_ID}:/tmp/plane_backup_temp.sql" "$BACKUP_FILE"
docker exec "$CONTAINER_ID" rm -f /tmp/plane_backup_temp.sql

SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "======================================================"
echo " BACKUP COMPLETED SUCCESSFULLY!"
echo " File: $BACKUP_FILE ($SIZE)"
echo "======================================================"

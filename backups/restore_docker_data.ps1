# ==============================================================================
# Script phục hồi toàn bộ Cơ sở dữ liệu Plane từ file SQL backup
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$BackupFile = "$ScriptDir\plane_database_backup.sql"

if (-not (Test-Path "$BackupFile")) {
    Write-Host "Loi: Khong tim thay file backup tai: $BackupFile" -ForegroundColor Red
    exit 1
}

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " BAT DAU PHUC HOI DU LIEU DOCKER PLANE" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

Set-Location -LiteralPath $ProjectRoot
Write-Host "[1/2] Khoi dong container plane-db..." -ForegroundColor Yellow
docker compose -f docker-compose-local.yml up -d plane-db

# Cho database san sang
Write-Host "Doi PostgreSQL khoi dong..." -ForegroundColor Gray
$retries = 30
$ready = $false
while ($retries -gt 0) {
    $check = docker compose -f docker-compose-local.yml exec -T plane-db pg_isready -U plane 2>&1
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
    $retries--
}

if (-not $ready) {
    Write-Host "Loi: Khong the ket noi den PostgreSQL container." -ForegroundColor Red
    exit 1
}

Write-Host "[2/2] Dang nap du lieu tu $BackupFile vao database 'plane'..." -ForegroundColor Yellow
$containerId = (docker compose -f docker-compose-local.yml ps -q plane-db).Trim()
docker cp "$BackupFile" "${containerId}:/tmp/plane_restore_temp.sql"
docker exec $containerId psql -U plane -d plane -f /tmp/plane_restore_temp.sql
docker exec $containerId rm -f /tmp/plane_restore_temp.sql

Write-Host "======================================================" -ForegroundColor Green
Write-Host " PHUC HOI HOAN TAT THANH CONG!" -ForegroundColor Green
Write-Host " Data da san sang (Workspaces, Projects, Issues, Users)" -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green

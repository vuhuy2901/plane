# ==============================================================================
# Script sao lưu toàn bộ Cơ sở dữ liệu và dữ liệu Docker của Plane
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\.."

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " BAT DAU SAO LUU DU LIEU DOCKER PLANE" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# 1. Kiem tra Docker daemon
Write-Host "[1/3] Kiem tra Docker Daemon..." -ForegroundColor Yellow
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker chua san sang."
    }
    Write-Host "Docker da san sang!" -ForegroundColor Green
} catch {
    Write-Host "LOI: Docker Desktop chua duoc bat hoac chua khoi dong xong!" -ForegroundColor Red
    Write-Host "Vui long mo ung dung Docker Desktop tren Windows va chay lai script nay." -ForegroundColor Yellow
    exit 1
}

# 2. Khoi dong plane-db neu chua chay
Write-Host "[2/3] Khoi dong container plane-db..." -ForegroundColor Yellow
Set-Location -LiteralPath $ProjectRoot
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

# 3. Xuat file SQL Backup (Chuan UTF-8 khong bi loi font qua docker cp)
$BackupFile = "$ScriptDir\plane_database_backup.sql"
Write-Host "[3/3] Dang xuat PostgreSQL Database ra: $BackupFile ..." -ForegroundColor Yellow

$containerId = (docker compose -f docker-compose-local.yml ps -q plane-db).Trim()
docker exec $containerId pg_dump -U plane -d plane --clean --if-exists -f /tmp/plane_backup_temp.sql
docker cp "${containerId}:/tmp/plane_backup_temp.sql" "$BackupFile"
docker exec $containerId rm -f /tmp/plane_backup_temp.sql

if (Test-Path "$BackupFile") {
    $size = (Get-Item "$BackupFile").Length
    Write-Host "======================================================" -ForegroundColor Green
    Write-Host " SAO LUU THANH CONG!" -ForegroundColor Green
    Write-Host " File: $BackupFile" -ForegroundColor Green
    Write-Host " Dung luong: $([math]::Round($size / 1MB, 2)) MB" -ForegroundColor Green
    Write-Host "======================================================" -ForegroundColor Green
} else {
    Write-Host "Loi: Khong tim thay file backup sau khi xuat." -ForegroundColor Red
    exit 1
}

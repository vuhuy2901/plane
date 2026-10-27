# ==============================================================================
# Script Khoi Dong Toan Bo Du An Plane (Database + Backend + Frontend)
# ==============================================================================
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location -LiteralPath $Root

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "                KHOI DONG DU AN PLANE                     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Kiem tra Docker & khoi dong Database
Write-Host "[1/3] Kiem tra Docker Daemon..." -ForegroundColor Yellow
$dockerReady = $false
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerReady = $true
    }
} catch {}

if ($dockerReady) {
    Write-Host "-> Docker da san sang. Dang khoi dong Database Postgres..." -ForegroundColor Green
    docker compose -f docker-compose-local.yml up -d plane-db plane-redis plane-mq plane-minio
    Write-Host "-> Cac container da khoi dong xong!" -ForegroundColor Green
} else {
    Write-Host "-> CANH BAO: Docker Desktop chua duoc bat tren Windows!" -ForegroundColor Red
    Write-Host "   Hay nhap dup vao bieu tuong Docker Desktop tren man hinh de bat Database." -ForegroundColor Yellow
}

# 2. Khoi dong Backend API (Port 8000)
Write-Host "`n[2/3] Khoi dong Backend API (Port 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location -LiteralPath '$Root\apps\api'; .\start-core.ps1" -WindowStyle Normal
Write-Host "-> Da mo cua so PowerShell khoi chay Backend API tai: http://localhost:8000" -ForegroundColor Green

# 3. Khoi dong Frontend Web (Port 3000, 3001)
Write-Host "`n[3/3] Khoi dong Frontend Web Server (Port 3000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location -LiteralPath '$Root'; pnpm dev" -WindowStyle Normal
Write-Host "-> Da mo cua so PowerShell khoi chay Frontend tai: http://localhost:3000" -ForegroundColor Green

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "                 CAC DUONG DAN DICH VU                    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  - Web App:      http://localhost:3000" -ForegroundColor Green
Write-Host "  - Admin Panel:  http://localhost:3001" -ForegroundColor Green
Write-Host "  - Backend API:  http://localhost:8000" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# ==============================================================================
# Script Bat Ngrok Tunnel Cho Plane Backend API (Port 8000)
# ==============================================================================
$ErrorActionPreference = "Continue"

$NGROK_DOMAIN = "geopolitical-anthropomorphously-rosena.ngrok-free.dev"
$LOCAL_PORT = 8000

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "             BAT NGROK TUNNEL CHO PLANE API               " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Domain: https://$NGROK_DOMAIN" -ForegroundColor Green
Write-Host "Target: http://localhost:$LOCAL_PORT" -ForegroundColor Green
Write-Host "Web UI: http://127.0.0.1:4040" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------" -ForegroundColor Gray

# Chay ngrok voi domain co dinh
ngrok http $LOCAL_PORT --url="https://$NGROK_DOMAIN"

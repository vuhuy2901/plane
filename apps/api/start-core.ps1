$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath ".env")) {
    throw "Missing apps/api/.env. Run setup.sh or create it from .env.example first."
}

# DEBUG can be set to a non-boolean value by an unrelated Windows process.
# Keep the local API lightweight and let uv load the stable SECRET_KEY and URLs.
$env:DEBUG = "0"
$env:PLANE_CORE_MODE = "1"
$env:DJANGO_SETTINGS_MODULE = "plane.settings.local"
if (-not $env:DATABASE_URL -or $env:DATABASE_URL -match "plane-db") {
    $env:DATABASE_URL = "postgresql://plane:plane@127.0.0.1:5432/plane"
}
$env:FORWARDED_ALLOW_IPS = "*"
uv run --env-file .env uvicorn plane.asgi:application --host 0.0.0.0 --port 8000 --proxy-headers

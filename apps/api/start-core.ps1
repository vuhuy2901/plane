$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath ".env")) {
    throw "Missing apps/api/.env. Run setup.sh or create it from .env.example first."
}

# DEBUG can be set to a non-boolean value by an unrelated Windows process.
# Keep the local API lightweight and let uv load the stable SECRET_KEY and URLs.
$env:DEBUG = "0"
$env:PLANE_CORE_MODE = "1"
uv run --env-file .env python manage.py runserver 127.0.0.1:8000 --settings=plane.settings.local

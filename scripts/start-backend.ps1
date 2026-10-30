$ErrorActionPreference = 'Stop'
$locusRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $locusRoot 'backend'
Set-Location -LiteralPath $locusRoot
& (Join-Path $locusRoot '.venv/Scripts/python.exe') -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers
exit $LASTEXITCODE

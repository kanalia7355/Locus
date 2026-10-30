$ErrorActionPreference = 'Stop'
$locusRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $locusRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    & py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 virtual environment creation failed' }
}
& .venv/Scripts/python.exe -m pip install -r backend/requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
& .venv/Scripts/python.exe -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Loop engine dependency installation failed' }
Push-Location -LiteralPath frontend
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
    & npx.cmd playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Browser installation failed' }
} finally { Pop-Location }
Write-Output 'Development dependencies installed. Run scripts/verify.py --e2e --audit next.'

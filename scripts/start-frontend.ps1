$ErrorActionPreference = 'Stop'
$locusRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $locusRoot 'frontend')
& npm.cmd run dev
exit $LASTEXITCODE

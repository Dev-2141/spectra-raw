# Offline installer for SPECTRA-SCAN AI (Windows). Requires Python 3.11+ and Node 20+.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> backend venv"
python -m venv backend\.venv
# air-gapped: & backend\.venv\Scripts\pip install --no-index --find-links .\wheelhouse -r backend\requirements.txt
& backend\.venv\Scripts\pip install -r backend\requirements.txt

if (-not (Test-Path frontend\dist)) {
  Write-Host "==> frontend build"
  Push-Location frontend; npm ci; npm run build; Pop-Location
}

Write-Host @'

==> done.

Dev:
  backend\.venv\Scripts\python -m uvicorn app.main:app --port 8000   (from backend\)
  npm run dev                                                        (from frontend\)

Production (set every env, then):
  $env:SPECTRA_PRODUCTION="1"; $env:SPECTRA_SEED_USERS="0"; $env:SPECTRA_SERVE_FRONTEND="1"
  $env:SPECTRA_JWT_KEY=[Convert]::ToBase64String((1..48 | % {Get-Random -Max 256}))
  $env:SPECTRA_TLS_CERT="C:\certs\cert.pem"; $env:SPECTRA_TLS_KEY="C:\certs\key.pem"
  $env:SPECTRA_CORS_ORIGINS="https://spectra.internal"
  $env:SPECTRA_DF_NODE_KEY="<lan-key>"
  backend\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8443 `
    --ssl-certfile $env:SPECTRA_TLS_CERT --ssl-keyfile $env:SPECTRA_TLS_KEY

Air-gap check:
  backend\.venv\Scripts\python -m scripts.preflight   (from backend\)
'@

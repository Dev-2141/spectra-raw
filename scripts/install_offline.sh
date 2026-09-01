#!/usr/bin/env bash
# Offline installer for SPECTRA-SCAN AI. Run on a machine that already has
# Python 3.11+ and Node 20+ (or a pre-built frontend/dist). No network calls
# beyond the local package indexes you point pip/npm at.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> backend venv"
python3 -m venv backend/.venv
# point --no-index at a local wheelhouse for a truly air-gapped install:
#   PIP_ARGS="--no-index --find-links ./wheelhouse"
backend/.venv/bin/pip install ${PIP_ARGS:-} -r backend/requirements.txt

if [ ! -d frontend/dist ]; then
  echo "==> frontend build"
  ( cd frontend && npm ci --offline 2>/dev/null || npm ci ) && ( cd frontend && npm run build )
fi

cat <<'NOTE'

==> done.

Dev:
  cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000
  cd frontend && npm run dev

Production (all envs required):
  export SPECTRA_PRODUCTION=1 SPECTRA_SEED_USERS=0 SPECTRA_SERVE_FRONTEND=1
  export SPECTRA_JWT_KEY=$(head -c48 /dev/urandom | base64)
  export SPECTRA_TLS_CERT=/path/cert.pem SPECTRA_TLS_KEY=/path/key.pem
  export SPECTRA_CORS_ORIGINS=https://spectra.internal
  export SPECTRA_DF_NODE_KEY=$(head -c24 /dev/urandom | base64)
  cd backend && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8443 \
      --ssl-certfile "$SPECTRA_TLS_CERT" --ssl-keyfile "$SPECTRA_TLS_KEY"

Air-gap check:
  cd backend && .venv/bin/python -m scripts.preflight
NOTE

# SPECTRA-SCAN AI — single-image build (backend serves the built frontend).
# Air-gapped: nothing is fetched at run time. Build once with network, run offline.

# --- frontend build ------------------------------------------------------- #
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- backend + static ---------------------------------------------------- #
FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/spectra

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY docs/ docs/
COPY --from=web /web/dist/ frontend/dist/

# Production defaults: no seed users, serve the built UI, TLS handled by the
# reverse proxy or uvicorn --ssl-* (see docker-compose.yml).
ENV SPECTRA_PRODUCTION=1 \
    SPECTRA_SEED_USERS=0 \
    SPECTRA_SERVE_FRONTEND=1 \
    SPECTRA_DATA_DIR=/srv/spectra/data

WORKDIR /srv/spectra/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

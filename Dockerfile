# SECPulse API (+ optional built SPA) for Railway / Docker.
# Build: docker build -t secpulse .
# Run:   docker run -p 8000:8000 -e SEC_USER_AGENT="Name you@example.com" \
#          -e CORS_ORIGINS="https://secpulse-ui.netlify.app" secpulse

FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin API when the SPA is served by FastAPI on Railway.
# For Netlify → Railway, rebuild Netlify with VITE_API_URL instead.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DATABASE_URL=sqlite:////data/secpulse.db

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY backend ./backend
COPY data ./data
COPY scripts ./scripts
COPY pyproject.toml README.md ./
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Persist SQLite (and ticker cache) on a Railway volume mounted at /data
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["python", "-m", "backend.main"]

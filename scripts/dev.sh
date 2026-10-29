#!/usr/bin/env bash
# Single-command local dev: FastAPI (:8000) + Vite (:5173, proxies /api)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — set SEC_USER_AGENT before real SEC polling."
fi

export SECPULSE_SKIP_FRONTEND=1
API_PID=""
cleanup() {
  if [[ -n "$API_PID" ]] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

.venv/bin/python -m backend.main &
API_PID=$!
echo "API pid=$API_PID on http://127.0.0.1:8000"
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173

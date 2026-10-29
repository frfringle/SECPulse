# Durable API hosting vs GitHub push

## Two different “cloud” asks

| Goal | What it is | What you need |
|------|------------|---------------|
| **Push to GitHub** | Source code on `frfringle/SECPulse` + PR | `gh auth` / device login |
| **Durable public API** | FastAPI (poller, SSE, SQLite) reachable 24/7 for Netlify | Railway / Fly / Render / VPS — **not** Netlify |

Netlify only serves the static SPA. Cloudflare `*.trycloudflare.com` tunnels from a Cloud Agent VM are demo-only and die when the VM stops.

## Recommended: Railway

This repo is Railway-ready:

| File | Role |
|------|------|
| `Dockerfile` | Multi-stage: build SPA + Python 3.12 runtime |
| `railway.toml` | Docker builder, `/api/health` check, restart policy |
| `Procfile` | `web: python -m backend.main` |
| `docs/railway-deploy.md` | Full checklist |

### Minimum env

```bash
SEC_USER_AGENT="Your Name you@example.com"
PORT=8080                          # Railway sets automatically; app reads PORT
CORS_ORIGINS="https://secpulse-ui.netlify.app"
DATABASE_URL="sqlite:////data/secpulse.db"
```

### Volume (required for SQLite)

Mount a Railway volume at **`/data`**. Without it, alerts and filings reset on every redeploy.

### After deploy

1. Copy the Railway HTTPS URL  
2. Rebuild Netlify with `VITE_API_URL=https://YOUR-SERVICE.up.railway.app`  
3. Confirm `GET /api/health` → `"status":"ok"`

CLI: `railway login` (browser/device URL — never invent tokens) → link repo → `railway up`. Details in `docs/railway-deploy.md`.

## Other hosts

Same Docker image works on Fly.io / Render / any container host. Set `PORT`, `SEC_USER_AGENT`, `CORS_ORIGINS`, and a persistent disk for SQLite (or switch `DATABASE_URL` to Postgres later).

## Tunnel fallback (demos only)

```bash
cloudflared tunnel --url http://127.0.0.1:8000
# rebuild Netlify with that ephemeral VITE_API_URL
```

# Durable API hosting vs GitHub push

## Two different “cloud” asks

| Goal | What it is | What you need |
|------|------------|---------------|
| **Push to GitHub** | Source code on `frfringle/SECPulse` + PR | `gh auth` / device login |
| **Durable public API** | FastAPI (poller, SSE, SQLite) reachable 24/7 for Netlify | Railway / Render / Fly / VPS — **not** Netlify |

Netlify only serves the static SPA. Cloudflare `*.trycloudflare.com` tunnels from a Cloud Agent VM are demo-only and die when the VM stops.

## Option A — Railway

| File | Role |
|------|------|
| `Dockerfile` | Multi-stage: build SPA + Python 3.12 runtime |
| `railway.toml` | Docker builder, `/api/health` check |
| `Procfile` | `web: python -m backend.main` |
| `docs/railway-deploy.md` | Full checklist |

Mount a volume at **`/data`**. Env: `SEC_USER_AGENT`, `CORS_ORIGINS`, `PORT` (auto), `DATABASE_URL=sqlite:////data/secpulse.db`.

## Option B — Render

| File | Role |
|------|------|
| `Dockerfile` | Same image as Railway |
| `render.yaml` | Blueprint: Docker web service + disk at `/data` |
| `docs/render-deploy.md` | Dashboard Blueprint steps |

1. Render Dashboard → **New** → **Blueprint** → `frfringle/SECPulse`  
2. Set `SEC_USER_AGENT` (+ `CORS_ORIGINS` for Netlify) when prompted  
3. Disk **`/data`** is declared in `render.yaml`  
4. Point Netlify `VITE_API_URL` at `https://….onrender.com`

## Shared minimum env

```bash
SEC_USER_AGENT="Your Name you@example.com"
PORT=8000                          # platform usually injects PORT; app reads it
CORS_ORIGINS="https://secpulse-ui.netlify.app"
DATABASE_URL="sqlite:////data/secpulse.db"
```

## After either host is live

1. Copy the public HTTPS URL  
2. Rebuild Netlify with `VITE_API_URL=https://your-api.example.com`  
3. Confirm `GET /api/health` → `"status":"ok"`

Never invent platform API tokens in agents — use the dashboard or a local CLI login.

## Tunnel fallback (demos only)

```bash
cloudflared tunnel --url http://127.0.0.1:8000
# rebuild Netlify with that ephemeral VITE_API_URL
```

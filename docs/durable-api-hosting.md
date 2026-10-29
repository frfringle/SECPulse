# Durable API hosting vs GitHub push

## Two different “cloud” asks

| Goal | What it is | What you need |
|------|------------|---------------|
| **Push to GitHub** | Source code on `frfringle/SECPulse` + PR | `GH_TOKEN` / `gh auth` in the agent VM |
| **Durable public API** | FastAPI (poller, SSE, SQLite/DB) reachable 24/7 for Netlify | A host: Railway, Fly.io, Render, a VPS — **not** Netlify |

Netlify only serves the static SPA. The current wiring uses an ephemeral Cloudflare quick tunnel (`*.trycloudflare.com`) from this Cloud Agent VM. When the VM or `cloudflared` stops, the Netlify UI loses its backend until a new tunnel URL is baked into a rebuild.

## Options for a durable API (no credentials in this environment)

1. **Railway / Render / Fly.io** — Deploy `python -m backend.main` (or Docker) with env:
   - `SEC_USER_AGENT`
   - `CORS_ORIGINS=https://secpulse-ui.netlify.app`
   - persistent volume or managed DB if you outgrow SQLite
2. **Rebuild Netlify** with `VITE_API_URL=https://your-stable-api.example.com`
3. **Keep tunnel for demos only** — fine for short sessions; refresh URL + redeploy when it dies

## This environment

- GitHub: needs `GH_TOKEN` (repo scope) or `gh auth login` — connecting GitHub in Cursor UI alone has not injected tokens here.
- Railway/Fly/Render: no deploy tokens present; document-only until you add them.

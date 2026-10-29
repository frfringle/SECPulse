# Deploy SECPulse API on Railway

The FastAPI backend (EDGAR poller, SSE, optional USPTO, SQLite) can run on Railway via the repo `Dockerfile`.

## 1. Create the service

From the [Railway](https://railway.app) dashboard (or CLI):

1. **New Project** → Deploy from GitHub → `frfringle/SECPulse`
2. Railway detects `railway.toml` / `Dockerfile`
3. Attach a **Volume** with mount path **`/data`** (required for durable SQLite)
4. Set environment variables (below)
5. Deploy → copy the public HTTPS URL (e.g. `https://secpulse-production.up.railway.app`)

### CLI (optional)

```bash
# https://docs.railway.com/guides/cli
npm i -g @railway/cli   # or: npx @railway/cli
railway login           # opens browser / prints auth URL — do not invent tokens
railway init
railway up
```

This agent will **not** invent `RAILWAY_TOKEN` values. If login is required, run `railway login` and complete the browser/device flow.

## 2. Environment variables

| Variable | Required | Example / notes |
|----------|----------|-----------------|
| `SEC_USER_AGENT` | **yes** | `Justin Feng you@example.com` |
| `PORT` | no | Railway sets this; app reads `PORT` (default 8000) |
| `CORS_ORIGINS` | yes if Netlify UI | `https://secpulse-ui.netlify.app` |
| `DATABASE_URL` | recommended | `sqlite:////data/secpulse.db` (matches volume) |
| `POLL_INTERVAL_SECONDS` | no | `30` |
| `USPTO_API_KEY` | no | Enables patent poller |
| `OLLAMA_BASE_URL` | no | Only if you run Ollama somewhere reachable |
| `SECPULSE_SKIP_FRONTEND` | no | `1` if API-only (SPA on Netlify) |

Dockerfile default: `DATABASE_URL=sqlite:////data/secpulse.db`.

## 3. Volume (SQLite)

Without a volume, the container filesystem is ephemeral — polls and alerts reset on every deploy/restart.

1. Railway service → **Volumes** → Add  
2. Mount path: `/data`  
3. Keep `DATABASE_URL=sqlite:////data/secpulse.db`

Ticker cache also lands under project `data/`; for a fully durable cache you can point `ASSIGNEE_ALIAS_PATH` at the image path (aliases are read-only in-image) and leave SQLite on the volume.

## 4. Point Netlify at Railway

```bash
cd frontend
export VITE_API_URL=https://YOUR-SERVICE.up.railway.app   # no trailing slash
npm run build
npx netlify deploy --dir=dist --prod
```

On Railway:

```bash
CORS_ORIGINS=https://secpulse-ui.netlify.app
```

## 5. Health check

`GET /api/health` should return `"status":"ok"`. `railway.toml` sets `healthcheckPath = "/api/health"`.

## Local Docker smoke

```bash
docker build -t secpulse .
docker run --rm -p 8000:8000 \
  -e SEC_USER_AGENT="Your Name you@example.com" \
  -e CORS_ORIGINS="http://localhost:5173" \
  -v secpulse-data:/data \
  secpulse
curl -s http://127.0.0.1:8000/api/health
```

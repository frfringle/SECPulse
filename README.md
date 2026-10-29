# SECPulse

Personal SEC EDGAR alert dashboard: poll filings → parse → score with local **Ollama** → enrich prices → live dark UI.

Alerts only. **Not financial advice. Experimental alerts.**

## Quick start

```bash
cd SECPulse
cp .env.example .env
# edit .env — required:
#   SEC_USER_AGENT="Your Name you@example.com"
# optional: OLLAMA_MODEL, ALERT_THRESHOLD

# Local scoring model
ollama pull qwen2.5:1.5b-instruct

make install          # Python venv + npm deps
make seed             # optional demo alerts for UI smoke
make dev              # API :8000 + Vite :5173 (proxies /api)
```

Open **http://127.0.0.1:5173**

Production-style (SPA built into FastAPI):

```bash
make run              # builds frontend, serves everything on :8000
```

## Environment

See `.env.example`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEC_USER_AGENT` | _(required)_ | `"Name email@example.com"` — refuse to start if missing |
| `DATABASE_URL` | `sqlite:///./data/secpulse.db` | SQLModel/SQLite |
| `POLL_INTERVAL_SECONDS` | `30` | Atom feed poll |
| `SEC_MAX_REQUESTS_PER_SECOND` | `8` | Fair-access rate limit |
| `TOKEN_BUDGET` | `4000` | Truncate filing text for Ollama |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local only |
| `OLLAMA_MODEL` | `qwen2.5:1.5b-instruct` | Pull with `ollama pull …` |
| `ALERT_THRESHOLD` | `65` | Non-neutral + confidence ≥ threshold → alert |
| `PORT` | `8000` | Listen port (Railway/Render inject `PORT`) |
| `CORS_ORIGINS` | — | Comma-separated browser origins (e.g. Netlify URL) |
| `SECPULSE_DISABLE_BACKGROUND` | — | Skip poller (tests) |
| `SECPULSE_SKIP_FRONTEND` | — | API-only when using Vite |
| `USPTO_API_KEY` | — | Optional USPTO ODP key for patent watch |

## What it does

1. **Ingestion** — Atom poll, accession dedupe, CIK→ticker cache, watched forms only  
2. **Form 4** — XML parse; officer/director open-market buys (`P`) alert by rule  
3. **8-K / SC 13D** — item extract, Exhibit 99.1 / no press release, Item 4, priority queue  
4. **Ollama** — JSON score; retry once; queue if down (never drop)  
5. **Prices** — yfinance (60s cache): latency, % since accepted, market-cap bucket  
6. **API** — alerts filters, ticker + history, SSE `/api/stream`, health  
7. **UI** — live feed, ticker chart, drawer, filters, watchlist, notify/sound  
8. **Patents (optional)** — USPTO ODP poll when `USPTO_API_KEY` is set; grants alert, apps stay quiet  

## API

- `GET /api/health`
- `GET /api/alerts` — `ticker`, `direction`, `form_type`, `min_confidence`, `market_cap_bucket`
- `GET /api/alerts/{id}`
- `GET /api/filings/non-alerts`
- `GET /api/patents` — `ticker`, `event_type`, `actionable`
- `GET /api/tickers/{ticker}`
- `GET /api/stream` — SSE `event: alert`

### USPTO key

```bash
# https://data.uspto.gov/apis — free ODP API key
export USPTO_API_KEY=your_key_here
# optional: USPTO_POLL_INTERVAL_SECONDS=600
```

Without the key, EDGAR keeps running and patent poller stays off. Assignee→ticker aliases live in `data/assignee_aliases.json`.

## Static / Netlify UI (optional)

Netlify can host the **React SPA only**. The FastAPI backend (SEC poller, SSE, scoring) must run elsewhere.

```bash
cd frontend
# Point the build at your public API (no trailing slash)
export VITE_API_URL=https://your-api.example.com
npm run build          # → frontend/dist
# Deploy dist with Netlify CLI or connect the frontend/ folder as the site root
```

On the API host, allow the Netlify origin:

```bash
export CORS_ORIGINS=https://your-site.netlify.app
```

Full steps: see `docs/netlify-deploy.md` in the project agent store, or `frontend/netlify.toml`.

## Durable API (Railway or Render)

Ship the FastAPI poller with Docker. Persist SQLite on a volume/disk at **`/data`**.

```bash
# Required service env:
#   SEC_USER_AGENT="Name email@example.com"
#   CORS_ORIGINS="https://secpulse-ui.netlify.app"
#   DATABASE_URL="sqlite:////data/secpulse.db"
#   PORT is injected by the host; app reads PORT
```

| Host | Config | Guide |
|------|--------|-------|
| Railway | `Dockerfile`, `railway.toml`, `Procfile` | [`docs/railway-deploy.md`](docs/railway-deploy.md) |
| Render | `Dockerfile`, `render.yaml` (disk `/data`) | [`docs/render-deploy.md`](docs/render-deploy.md) |

```bash
docker build -t secpulse .
docker run --rm -p 8000:8000 \
  -e SEC_USER_AGENT="Your Name you@example.com" \
  -v secpulse-data:/data \
  secpulse
```

## Tests

```bash
make test             # pytest (mocked SEC / Ollama / yfinance)
cd frontend && npm run build
```

## Layout

```
SECPulse/
  backend/            FastAPI, poller, parsers, scoring, prices, API
  frontend/           Vite + React + Tailwind UI
  scripts/dev.sh      make dev
  scripts/seed_demo_alerts.py
  tests/
  data/               SQLite + caches (gitignored runtime files)
```

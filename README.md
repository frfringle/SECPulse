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
| `SECPULSE_DISABLE_BACKGROUND` | — | Skip poller (tests) |
| `SECPULSE_SKIP_FRONTEND` | — | API-only when using Vite |

## What it does

1. **Ingestion** — Atom poll, accession dedupe, CIK→ticker cache, watched forms only  
2. **Form 4** — XML parse; officer/director open-market buys (`P`) alert by rule  
3. **8-K / SC 13D** — item extract, Exhibit 99.1 / no press release, Item 4, priority queue  
4. **Ollama** — JSON score; retry once; queue if down (never drop)  
5. **Prices** — yfinance (60s cache): latency, % since accepted, market-cap bucket  
6. **API** — alerts filters, ticker + history, SSE `/api/stream`, health  
7. **UI** — live feed, ticker chart, drawer, filters, watchlist, notify/sound  

## API

- `GET /api/health`
- `GET /api/alerts` — `ticker`, `direction`, `form_type`, `min_confidence`, `market_cap_bucket`
- `GET /api/alerts/{id}`
- `GET /api/tickers/{ticker}`
- `GET /api/stream` — SSE `event: alert`

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

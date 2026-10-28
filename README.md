# SECPulse

Personal SEC EDGAR alert dashboard: poll filings → score with local Ollama → live feed.  
**Stage 1 (this tree): ingestion + SQLite only.**

## Requirements

- Python 3.11+
- A valid SEC fair-access User-Agent (`Name email@example.com`)

## Setup

```bash
cd SECPulse
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env — set SEC_USER_AGENT="Your Name you@example.com"
```

The app **refuses to start** if `SEC_USER_AGENT` is missing or not in `Name email@example.com` form.

## Run (Stage 1)

```bash
source .venv/bin/activate
python -m backend.main
# or: uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

- Health: `GET http://localhost:8000/api/health`
- Alerts stub: `GET http://localhost:8000/api/alerts`
- Polls `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom` every 30s
- Stores watched forms (`8-K`, `8-K/A`, `4`, `SC 13D`, `SC 13D/A`) in `data/secpulse.db`
- Dedupes by accession number; skips filings with no CIK→ticker mapping
- Rate-limits SEC requests to 8/sec with backoff on 403/429

## Tests

```bash
source .venv/bin/activate
pytest -q
```

Fixtures live under `tests/fixtures/` (saved Atom XML + company tickers JSON).

## Layout

```
SECPulse/
  backend/           # FastAPI app, models, SEC poller
  tests/             # pytest + fixtures
  data/              # SQLite + ticker cache (gitignored runtime files)
  .env.example
  requirements.txt
  pyproject.toml
```

Later stages add Form 4 parsing, 8-K/13D processing, Ollama scoring, prices, full API, and a Vite frontend — keep this single-root layout so `make dev` / one script can start API + UI together.

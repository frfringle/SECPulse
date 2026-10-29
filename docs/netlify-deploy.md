# Deploy SECPulse UI to Netlify

## Important limitation

**Netlify cannot run the Python FastAPI backend** (Atom poller, Form 4 / 8-K parsers, Ollama scoring, SSE, SQLite). A Netlify site can only host the static Vite/React SPA.

To use the UI on Netlify you need a **publicly reachable API** (VPS, Fly, Railway, Render, etc.) and build the frontend with `VITE_API_URL` pointing at that API.

Local / same-box deploy remains: `make run` (FastAPI serves `frontend/dist` on `:8000`).

## Prerequisites

1. Backend running somewhere with HTTPS (recommended) and CORS enabled for your Netlify domain:
   ```bash
   export CORS_ORIGINS=https://YOUR-SITE.netlify.app
   # plus SEC_USER_AGENT and the rest of .env
   python -m backend.main
   ```
2. Node 22+ and npm in the build environment.
3. To publish from this Cloud Agent environment: `NETLIFY_AUTH_TOKEN` (and optionally `NETLIFY_SITE_ID`) **or** `netlify login`. Those were **not** present when these instructions were written — prepare the build locally, then authenticate to publish.

## Build the static SPA

From the repo:

```bash
cd frontend
cp .env.example .env   # optional
# No trailing slash:
export VITE_API_URL=https://YOUR-API.example.com
npm ci
npm run build
# Output: frontend/dist/
```

Leave `VITE_API_URL` empty only when the SPA is served from the same origin as the API (normal `make run` / `make dev` path).

Config files already in `frontend/`:

| File | Purpose |
|------|---------|
| `netlify.toml` | Build command, `dist` publish, SPA redirect |
| `public/_redirects` | `/* → /index.html` for client-side routes |
| `.env.example` | Documents `VITE_API_URL` |

## Deploy with Netlify CLI

```bash
cd frontend
# First time / CI:
export NETLIFY_AUTH_TOKEN=...   # from https://app.netlify.com/user/applications#personal-access-tokens
# Optional existing site:
export NETLIFY_SITE_ID=...

npx netlify deploy --dir=dist --prod
# or create a new site:
# npx netlify sites:create --name secpulse-ui
# npx netlify deploy --dir=dist --prod --site=$NETLIFY_SITE_ID
```

Or connect the GitHub repo in the Netlify UI with:

- **Base directory:** `frontend`
- **Build command:** `npm run build`
- **Publish directory:** `dist`
- **Env:** `VITE_API_URL=https://YOUR-API.example.com`

## CORS + SSE notes

- Set `CORS_ORIGINS` on the API to your Netlify URL (comma-separated list supported).
- Browser `EventSource` to a cross-origin `/api/stream` requires CORS headers on the stream response (Starlette `CORSMiddleware` covers this when origins are configured).
- Cookies are unused; `allow_credentials=True` is fine but not required for the current API.

## This environment status

| Item | Status |
|------|--------|
| `npm run build` | Run to produce `frontend/dist` |
| `NETLIFY_AUTH_TOKEN` | Not set — cannot publish from agent |
| `NETLIFY_SITE_ID` | Not set |
| Netlify CLI (`npx netlify`) | Available, not logged in |

Provide a Netlify personal access token (or run `netlify login`) to publish and return a live URL.


## Live deploy (this environment)

- Site: https://secpulse-ui.netlify.app
- Admin: https://app.netlify.com/projects/secpulse-ui
- Site ID: `3b6bc8bd-d615-4036-8f28-624c9031f7aa`
- API (Cloudflare quick tunnel → this VM `:8000`): `https://visiting-partner-already-morrison.trycloudflare.com`
- Frontend rebuilt with `VITE_API_URL` pointing at that tunnel; API `CORS_ORIGINS` includes `https://secpulse-ui.netlify.app`
- **Caveat:** trycloudflare URL is ephemeral — dies when the Cloud Agent / `cloudflared` / API process stops. For a durable setup, host FastAPI on Fly/Railway/Render and rebuild with a stable `VITE_API_URL`.

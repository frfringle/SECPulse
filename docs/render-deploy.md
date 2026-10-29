# Deploy SECPulse API on Render

Use the repo `Dockerfile` + `render.yaml` Blueprint so the FastAPI backend (EDGAR poller, SSE, optional USPTO, SQLite) runs with a **persistent disk** at `/data`.

## Dashboard steps (recommended)

1. Open [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
2. Connect GitHub and select **`frfringle/SECPulse`** (branch with `render.yaml`, e.g. `main` after merge or `cursor/stage1-ingestion-34ed`).
3. Render reads `render.yaml` and proposes service **`secpulse-api`**:
   - Runtime: **Docker**
   - Disk: **`secpulse-data`** mounted at **`/data`** (1 GB)
   - Health check: `/api/health`
4. When prompted for sync’d env vars, set at least:
   - **`SEC_USER_AGENT`** = `Your Name you@example.com` (required)
   - **`CORS_ORIGINS`** = `https://secpulse-ui.netlify.app` (if using Netlify UI)
   - Optional: **`USPTO_API_KEY`** (leave blank / skip if unused)
5. Apply / create → wait for the first deploy.
6. Copy the service URL (`https://secpulse-api-xxxx.onrender.com`).

### Manual “Web Service” (no Blueprint)

1. **New** → **Web Service** → same repo.  
2. Runtime: **Docker** (Dockerfile path `.`).  
3. **Advanced** → add disk, mount path **`/data`**, size ≥ 1 GB.  
4. Set env vars as in the table below.  
5. Health check path: `/api/health`.

## Environment

| Variable | Required | Notes |
|----------|----------|-------|
| `SEC_USER_AGENT` | **yes** | `"Name email@example.com"` |
| `PORT` | no | Render sets `PORT`; Blueprint defaults `8000`. App reads `PORT`. |
| `CORS_ORIGINS` | for Netlify | e.g. `https://secpulse-ui.netlify.app` |
| `DATABASE_URL` | recommended | `sqlite:////data/secpulse.db` (matches disk) |
| `USPTO_API_KEY` | no | Enables patent poller |

Do **not** commit secrets. Blueprint uses `sync: false` so the dashboard prompts for `SEC_USER_AGENT` / `CORS_ORIGINS` / `USPTO_API_KEY`.

## Persistent disk (SQLite)

Mount path **`/data`**. Only files under `/data` survive redeploys.

- Without a disk, the SQLite DB is wiped on every deploy.  
- Disks force single-instance and short downtime on redeploy (Render limitation).  
- You can grow disk size later; you cannot shrink it.

## Point Netlify at Render

```bash
cd frontend
export VITE_API_URL=https://YOUR-SERVICE.onrender.com   # no trailing slash
npm run build
npx netlify deploy --dir=dist --prod
```

On Render: `CORS_ORIGINS=https://secpulse-ui.netlify.app`.

## Free / starter notes

- Free web services on Render **spin down** when idle; first request after idle can be slow. Prefer a paid starter instance for a live Netlify UI.  
- Cold starts + disk are fine for personal use; expect a few seconds of downtime on redeploy.

## CLI / tokens

This agent does **not** invent Render API tokens. Deploy via the dashboard Blueprint flow, or run `render` CLI login on your own machine if you use the CLI.

## Smoke check

```bash
curl -s https://YOUR-SERVICE.onrender.com/api/health
# expect: "status":"ok"
```

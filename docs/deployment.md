# Deployment

## Verified in this environment (no Docker) — the running provisional app
```bash
bash scripts/run_local.sh
# App:  http://127.0.0.1:8080/frontend/index.html
# API:  http://127.0.0.1:8010/api/health   ·   Docs: http://127.0.0.1:8010/docs
```
Backend: FastAPI/uvicorn on :8010. Frontend: static MapLibre SPA served on :8080
(so `../data/boundaries` and `config.js` resolve). This is what was tested here.

## Containerised (files provided; NOT built in this sandbox — no Docker daemon)
```bash
docker compose up --build
# open http://localhost:8080/frontend/index.html
```
`backend/Dockerfile` (python:3.12-slim, slim `requirements-api.txt`, `/api/health`
healthcheck) + `docker-compose.yml` (api + static web). Build/run on any host with
Docker; not exercised in the current environment.

## Public URL — honest status
No public deployment URL yet. Blockers: (1) no Docker daemon in this sandbox;
(2) no configured/authorised external host. A public deploy needs a host with
Python 3.12 + the compact processed files (`data/processed/*.nc`,
`data/boundaries/*.geojson`, `data/demo/*`), which the image already bundles.
The frontend alone can go on any static host once `config.js.API_BASE` points at
a reachable backend. No URL is fabricated.

## Vercel — LIVE
**Production URL: https://waves-nine-gold.vercel.app** (public alias).
Deployed via `vercel deploy --prod`. Serves the provisional (2020) baseline.
All endpoints verified 200 live (health, thresholds, location-risk, risk-map,
forecast-grid, cities, profile-risk); root `/` → 307 → `/index.html` (app).
Note: the per-deployment `*.vercel.app` URLs are behind Vercel deployment
protection (302 to SSO) — use the public alias above. Redeploy: `vercel --prod`.

## Vercel setup (how it's wired)
The repo is Vercel-ready:
- `api/index.py` exposes the FastAPI ASGI `app`; `vercel.json` rewrites `/api/*`
  to it and serves `/` → `frontend/index.html`.
- Root `requirements.txt` is **slim** (fastapi, pydantic, pyyaml, httpx, numpy) —
  the threshold store reads a numpy **`.npz`** (no netCDF4/xarray/pandas), so the
  function is small. Regenerate the npz with `python scripts/export_thresholds_npz.py`.
- `WAVES_CACHE_DIR=/tmp/waves-cache` (set in `api/index.py`) handles the read-only FS.
- risk-map fetches cities concurrently (~2 s) to stay inside function limits.
- `.vercelignore` keeps `.env`, `.venv`, `data/raw/`, `*.nc`, `tmp/` out of the upload.
- Frontend auto-targets the **same-origin** `/api` when not on localhost.

Deploy (you run these — they publish to YOUR Vercel account):
```bash
vercel login            # or:  !vercel login  in this session
vercel --prod           # from the repo root; first run links/creates the project
```
Post-deploy checks: `https://<domain>/api/health`, then open `https://<domain>/`.

Caveats: serves the **provisional (2020) baseline** frozen at deploy time —
redeploy after the full 1991–2020 npz is built. CDS downloading never runs on
Vercel. The MapTiler key in `frontend/config.js` is a client key — restrict it by
domain in the MapTiler dashboard. If the build rejects `maxDuration: 30`, remove
that line from `vercel.json` (endpoints are fast enough for the default).

## Config
`.env` (git-ignored) / `.env.example`: CDS creds (or `~/.cdsapirc`),
`NEXT_PUBLIC_MAPTILER_API_KEY`, `FORECAST_PROVIDER`. Frontend key lives in
git-ignored `frontend/config.js` (see `config.example.js`).

# Motor Self-Inspection AI (PS-03)

Team 3 entry, Masters' Union Applied AI Challenge. A customer films their car (React + Vite app, Android via Capacitor); the system returns one of
APPROVE / APPROVE_WITH_EXCLUSIONS / RESHOOT / REJECT with reasons and a damage register. All data is synthetic.

## How it works
1. `engine/frame_reader.py` reads what is in the video (today: written frame descriptions; later: a vision model) and lists damage.
2. `engine/decision_engine.py` applies the PolicyNest SOP v2.4 as plain rules: fraud, then quality, then severe damage, then minor damage, then clean.

## Run the test on the 420 gold cases
```
pip install pandas openpyxl
cd engine && python score_end_to_end.py
```
Current result: 418/420 decisions correct (99.5%); human reviewers 71.7%. Damage type and severity exact match 98.5%.
Caveat: tested on written descriptions, not real video.

## Run it locally (two terminals)
```
# 1) the API (from the repo root)
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.app:app --reload            # http://localhost:8000/api/health

# 2) the website: React + Vite (later wrapped into an Android app with Capacitor)
cd web && npm install && npm run dev                   # open the address Vite prints (usually http://localhost:5173)
```
While developing, Vite forwards `/api` calls to port 8000. For a deployed or Android build, set `VITE_API_URL`
to the API's full address (see `web/.env.example`).

## Deployment (Render free tier)
**Live:** https://motor-self-inspection-web.onrender.com (API: https://motor-self-inspection-api.onrender.com/api/health)
- After pushing changes, open each service in Render and click **Manual Deploy -> Deploy latest commit** (auto-deploy is off).
- Settings live in `render.yaml`: two free services.
  - `motor-self-inspection-api` (Python 3.12.7): build `pip install -r backend/requirements.txt`, start `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`.
  - `motor-self-inspection-web` (static site from `web/`): build `npm ci && npm run build`, publish `dist`, setting `VITE_API_URL` = the API's address.
- The two challenge workbooks (synthetic data) are committed in `data/`, so the deployed API reads them directly; no secrets
  or tokens are needed. If a file is missing or unreadable, the site still opens and shows a "Data not loaded" message.
- **Note for the team:** the repo and the live site are both public, so anyone can download the data and see each case's
  content. The challenge pack states all data is synthetic; we decided on 10 Nov to keep everything in one public repo.
- The free tier sleeps after ~15 minutes idle; the first visit then takes 30-60 s. Open the site a minute before any demo.

See STATUS.md for what is done and what is left.

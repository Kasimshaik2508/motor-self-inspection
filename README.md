# Motor Self-Inspection AI (PS-03)

Team 3 entry, Masters' Union Applied AI Challenge. A customer films their car; the system returns one of
APPROVE / APPROVE_WITH_EXCLUSIONS / RESHOOT / REJECT with reasons and a damage register. All data is synthetic.

## How it works
1. `engine/frame_reader.py` reads what is in the video (today: written frame descriptions; later: a vision model) and lists damage.
2. `engine/decision_engine.py` applies the PolicyNest SOP v2.4 as plain rules: fraud, then quality, then severe damage, then minor damage, then clean.

## Run the test on the 420 gold cases
```
pip install pandas openpyxl
# put the two workbooks in data/ (see data/README.md)
cd engine && python score_end_to_end.py
```
Current result: 418/420 decisions correct (99.5%); human reviewers 71.7%. Damage type and severity exact match 98.5%.
Caveat: tested on written descriptions, not real video.

## Run the website
```
pip install -r backend/requirements.txt
uvicorn backend.app:app --reload     # from the repo root, with data/ filled in
# open http://localhost:8000
```
The page is plain HTML + JavaScript (no build step) and is served by the same FastAPI app.

## Deployment (Render free tier)
- Settings live in `render.yaml` (build: `pip install -r backend/requirements.txt`; start: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`; Python 3.12.7).
- The challenge data is NOT in this repo. On startup `backend/fetch_data.py` downloads the two workbooks from the private repo
  `motor-self-inspection-data` using `DATA_REPO_TOKEN` (a read-only token set only in Render's dashboard). If that fails,
  the site still opens and shows a "Data not loaded" message with the reason.
- **Note for the team:** the live site is public, so anyone can see each case's content (frame descriptions, expected decision)
  through `/api/cases`. Keeping the files out of GitHub does not hide that. We accepted this for the demo.
- The free tier sleeps after ~15 minutes idle; the first visit then takes 30-60 s. Open the site a minute before any demo.

See STATUS.md for what is done and what is left.

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

See STATUS.md for what is done and what is left.

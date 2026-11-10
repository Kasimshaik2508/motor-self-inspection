# Motor Self-Inspection AI (PS-03)

Team 3 entry, Masters' Union Applied AI Challenge. A customer films their car (React + Vite app, Android via Capacitor); the system returns one of
APPROVE / APPROVE_WITH_EXCLUSIONS / RESHOOT / REJECT with reasons and a damage register. All data is synthetic.

## What the app does (three tabs)
1. **Inspect my car** (customer): live phone camera, guided through the 12 SOP shots. FREE and ON THE PHONE:
   a car detector (COCO-SSD, TensorFlow.js) says "car detected" and auto-captures when the car fills the frame;
   OCR (Tesseract.js) reads the number plate (front/rear) and chassis number and compares them with what was entered;
   dark / blurry photos get "retake" at once. The backend's SOP engine then decides: missing / dark / blurry photos,
   unreadable plate or chassis -> one plain re-shoot message; plate or chassis mismatch -> surveyor (fraud desk);
   everything fine -> a reviewer checks damage (no damage AI yet, so we never auto-approve).
2. **Reviewer**: every inspection with photos and the AI's findings; confirm or override (overrides need a reason).
   A person is required for fraud suspicions, severe damage, plate/chassis disagreement, low-confidence damage,
   a second failed retake (surveyor), and when no vision model is available (never auto-approve blind).
3. **Evaluation (420 cases)**: the challenge's gold cases, read from written frame descriptions, scored 418/420.

## How it works
- `engine/vision.py` - the eyes: sends all photos in ONE request to a vision model (swappable: `VISION_PROVIDER` =
  `gemini` | `openrouter` | `none`), then cleans the answer (SOP panel/type lists, severity ranges).
- `engine/live_inspection.py` - turns the model's answers into the engine's `Findings`, decides, applies SOP routing
  (second failed retake -> surveyor, identity conflict / low confidence -> reviewer), keeps the record (memory only).
- `engine/decision_engine.py` - the SOP v2.4 rules: fraud, then quality, then severe damage, then minor damage, then clean.
- `engine/frame_reader.py` - reads the challenge's written frame descriptions for the 420-case evaluation.
- `web/src/Camera.jsx` + `web/src/detect.js` - live camera, on-phone car detection, auto-capture, plate / chassis OCR.
  No API key, no paid calls; model files download once from public CDNs. Accuracy on real cars NOT yet measured.
- `web/src/photo.js` - on-phone photo checks (resize, brightness, sharpness). Thresholds are first guesses, uncalibrated.
- `tests/test_live_routes.py` - scripted model answers through every SOP route (routing only, not model accuracy).

## Vision model settings (Render -> motor-self-inspection-api -> Environment)
- `VISION_PROVIDER` = `gemini` and `GEMINI_API_KEY` = your key (aistudio.google.com). Optional `GEMINI_MODEL`.
  Gemini's free tier may use uploaded content to improve Google's products: test photos only, never real customers.
- or `VISION_PROVIDER` = `openrouter`, `OPENROUTER_API_KEY`, optional `OPENROUTER_MODEL`.
- Without these (the current setup), the app uses the phone's own checks above and a reviewer checks damage.
- **Untested:** the accuracy of any model on real car photos. Measure it on the team's own test photos.

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
- Render redeploys both services automatically a minute or two after a push to `main` (checked 10 Nov).
- Settings live in `render.yaml`: two free services.
  - `motor-self-inspection-api` (Python 3.12.7): build `pip install -r backend/requirements.txt`, start `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`.
  - `motor-self-inspection-web` (static site from `web/`): build `npm ci && npm run build`, publish `dist`, setting `VITE_API_URL` = the API's address.
- The two challenge workbooks (synthetic data) are committed in `data/`, so the deployed API reads them directly; no secrets
  or tokens are needed. If a file is missing or unreadable, the site still opens and shows a "Data not loaded" message.
- **Note for the team:** the repo and the live site are both public, so anyone can download the data and see each case's
  content. The challenge pack states all data is synthetic; we decided on 10 Nov to keep everything in one public repo.
- The free tier sleeps after ~15 minutes idle; the first visit then takes 30-60 s. Open the site a minute before any demo.

See STATUS.md for what is done and what is left.

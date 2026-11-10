"""
backend/app.py - the web API (FastAPI). Thin on purpose: all logic lives in engine/pipeline.py.

Run:  pip install -r backend/requirements.txt
      uvicorn backend.app:app --reload        (from the repo root, with data/ filled in)
Endpoints:
  GET /api/health            -> {"ok": true, "data_loaded": bool, "data_message": "..."}
  GET /api/cases             -> list of the 420 cases
  GET /api/cases/{id}        -> full analysis of one case (decision, reasons, damage register, message, evidence)
  GET /api/evaluate          -> accuracy over all 420
"""
import os, sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
from fetch_data import ensure_data

# FAIL SAFE: get the data (download it if needed), then load the engine. If either step fails the server
# still starts; the API answers 503 with a plain reason and the page shows a "data not loaded" banner.
DATA_OK, DATA_MESSAGE = ensure_data()
pipeline = None
if DATA_OK:
    try:
        import pipeline                      # reads the spreadsheets as soon as it is imported
    except Exception as e:                   # e.g. a corrupt file or a renamed sheet
        DATA_OK, DATA_MESSAGE = False, f"Data not loaded: the data files could not be read ({type(e).__name__})."
print(f"[startup] {DATA_MESSAGE}", flush=True)   # safe: the message never contains the token

app = FastAPI(title="Motor Self-Inspection AI")
# CORS lets the React site (its own address on Render, or https://localhost inside the Capacitor app) call this API.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True, "data_loaded": DATA_OK, "data_message": DATA_MESSAGE}


def need_data():
    if not DATA_OK:
        raise HTTPException(503, DATA_MESSAGE)


@app.get("/api/cases")
def cases():
    need_data()
    return pipeline.list_cases()


@app.get("/api/cases/{case_id}")
def case(case_id: str):
    need_data()
    try:
        return pipeline.analyze(case_id)
    except KeyError:
        raise HTTPException(404, "unknown case")


@app.get("/api/evaluate")
def evaluate():
    need_data()
    return pipeline.evaluate()


@app.get("/")
def root():
    # The website is a separate React app (web/), deployed as its own static site; this server is only the API.
    return {"service": "Motor Self-Inspection AI API", "health": "/api/health", "website": "see web/ (React + Vite)"}

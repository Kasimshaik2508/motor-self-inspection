"""
backend/app.py - the web API (FastAPI). Thin on purpose: all logic lives in engine/pipeline.py.

Run:  pip install -r backend/requirements.txt
      uvicorn backend.app:app --reload        (from the repo root, with data/ filled in)
Endpoints:
  GET /api/health            -> {"ok": true}
  GET /api/cases             -> list of the 420 cases
  GET /api/cases/{id}        -> full analysis of one case (decision, reasons, damage register, message, evidence)
  GET /api/evaluate          -> accuracy over all 420
"""
import os, sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import pipeline

app = FastAPI(title="Motor Self-Inspection AI")
# CORS lets the React site (a different address while developing) call this API from the browser.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/cases")
def cases():
    return pipeline.list_cases()


@app.get("/api/cases/{case_id}")
def case(case_id: str):
    try:
        return pipeline.analyze(case_id)
    except KeyError:
        raise HTTPException(404, "unknown case")


@app.get("/api/evaluate")
def evaluate():
    return pipeline.evaluate()

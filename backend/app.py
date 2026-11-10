"""
backend/app.py - the web API (FastAPI). Thin on purpose: all logic lives in engine/pipeline.py.

Run:  pip install -r backend/requirements.txt
      uvicorn backend.app:app --reload        (from the repo root, with data/ filled in)
Endpoints:
  GET /api/health            -> {"ok": true, "data_loaded": bool, "data_message": "..."}
  GET /api/cases             -> list of the 420 cases
  GET /api/cases/{id}        -> full analysis of one case (decision, reasons, damage register, message, evidence)
  GET /api/evaluate          -> accuracy over all 420
  Live photo inspections (the customer app and the reviewer console):
  POST /api/inspections                 -> customer sends photos; returns what the CUSTOMER may see
  GET  /api/inspections/{id}            -> customer checks the result again (e.g. after a reviewer decided)
  GET  /api/review/inspections          -> reviewer: list of inspections
  GET  /api/review/inspections/{id}     -> reviewer: everything (photos, AI findings, decision)
  POST /api/review/inspections/{id}     -> reviewer: confirm or override, with a reason
NOTE: the reviewer endpoints have NO login in this MVP. Anyone with the link can use them. Fine for a demo
with synthetic or test photos; a real product needs reviewer accounts.
"""
import os, sys
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))

# FAIL SAFE: load the engine, which reads the two workbooks in data/. If that fails (file missing, corrupt,
# sheet renamed) the server still starts; the API answers 503 with a plain reason and the page shows a
# "data not loaded" banner instead of crashing.
DATA_OK, DATA_MESSAGE = True, "Data files loaded."
pipeline = None
try:
    import pipeline                          # reads the spreadsheets as soon as it is imported
except FileNotFoundError as e:
    DATA_OK, DATA_MESSAGE = False, f"Data not loaded: missing file {os.path.basename(str(e.filename))} in data/."
except Exception as e:
    DATA_OK, DATA_MESSAGE = False, f"Data not loaded: the data files could not be read ({type(e).__name__})."
print(f"[startup] {DATA_MESSAGE}", flush=True)
import live_inspection, vision                  # the photo app: does not need the workbooks

app = FastAPI(title="Motor Self-Inspection AI")
# CORS lets the React site (its own address on Render, or https://localhost inside the Capacitor app) call this API.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True, "data_loaded": DATA_OK, "data_message": DATA_MESSAGE,
            "vision_provider": os.environ.get("VISION_PROVIDER", "none")}


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


# ---------------- live photo inspections ----------------
class Shot(BaseModel):
    shot: str
    image_b64: str
    brightness: Optional[float] = None     # measured on the phone, 0 (black) to 1 (white)
    sharpness: Optional[float] = None      # measured on the phone; higher = sharper
    captured_at_ms: Optional[float] = None
    car_detected: Optional[bool] = None    # on-phone car detector (outside shots only)
    plate_read: str = ""                   # on-phone OCR (FRONT / REAR)
    chassis_read: str = ""                 # on-phone OCR (CHASSIS_NUMBER), last 6 characters


class InspectionIn(BaseModel):
    declared_plate: str
    declared_chassis_last6: str
    shots: List[Shot]
    retake_of: Optional[str] = None


class ReviewIn(BaseModel):
    action: str                 # CONFIRM or OVERRIDE
    final_outcome: Optional[str] = None
    reason: str = ""
    reviewer: str = ""


@app.get("/api/shots")
def shots():
    return [{"code": c, "what": w} for c, w in vision.SHOTS]


@app.post("/api/inspections")
def create_inspection(body: InspectionIn):
    if not body.shots:
        raise HTTPException(400, "no photos were sent")
    seen = set()
    for s in body.shots:
        if s.shot not in vision.SHOT_CODES or s.shot in seen:
            raise HTTPException(400, f"unknown or repeated shot: {s.shot}")
        seen.add(s.shot)
        try:
            vision.check_base64_image(s.image_b64)
        except Exception as e:
            raise HTTPException(400, f"photo {s.shot}: {e}")
    if body.retake_of:
        try:
            live_inspection.get(body.retake_of)
        except KeyError:
            raise HTTPException(404, "the inspection you are retaking was not found (the server may have restarted)")
    rec = live_inspection.run(body.declared_plate.strip(), body.declared_chassis_last6.strip(),
                              [s.model_dump() for s in body.shots], body.retake_of)
    return live_inspection.customer_view(rec)


@app.get("/api/inspections/{inspection_id}")
def get_inspection(inspection_id: str):
    try:
        return live_inspection.customer_view(live_inspection.get(inspection_id))
    except KeyError:
        raise HTTPException(404, "inspection not found (the free server forgets inspections when it restarts)")


@app.get("/api/review/inspections")
def review_list():
    return [live_inspection.reviewer_summary(r) for r in live_inspection.all_records()]


@app.get("/api/review/inspections/{inspection_id}")
def review_detail(inspection_id: str):
    try:
        return live_inspection.reviewer_detail(live_inspection.get(inspection_id))
    except KeyError:
        raise HTTPException(404, "inspection not found")


@app.post("/api/review/inspections/{inspection_id}")
def review_action(inspection_id: str, body: ReviewIn):
    try:
        rec = live_inspection.review(inspection_id, body.action, body.final_outcome, body.reason, body.reviewer)
    except KeyError:
        raise HTTPException(404, "inspection not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return live_inspection.reviewer_summary(rec)


@app.get("/")
def root():
    # The website is a separate React app (web/), deployed as its own static site; this server is only the API.
    return {"service": "Motor Self-Inspection AI API", "health": "/api/health", "website": "see web/ (React + Vite)"}

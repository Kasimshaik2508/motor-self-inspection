"""
pipeline.py - the one function the app calls: analyze(case_id) -> a plain dict.

WHY: the website must not know how decisions are made. It asks "analyze this case" and gets back a dict
     (JSON-friendly). Later, when real video + a vision model arrive, only build_findings() changes;
     the decision engine and the API stay as they are.
HOW: build_findings()  = gather evidence (metadata, shot log, damage read from the frame descriptions)
     decide()          = apply the SOP rules (decision_engine.py)
     analyze()         = package both for the screen, including the gold answer so the UI can show right/wrong.
"""
import os, sys
from dataclasses import asdict
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decision_engine import Findings, decide
from frame_reader import read_damage
from score_on_gold import cases, shots_by, panels_by, gold, num, read, EVAL

_frames = read(EVAL, "frame_descriptions")
_frames_by = {k: list(zip(v.shot_code, v.frame_description)) for k, v in _frames.groupby("case_id")}
_gold_by = gold.set_index("case_id")


def build_findings(case_id: str) -> Findings:
    c, sh = cases.loc[case_id], shots_by[case_id]
    missing = sh.loc[sh.captured != "True", "shot_code"].tolist()
    bad = [(r.shot_code, r.shot_quality) for r in sh.itertuples() if r.shot_quality not in ("OK", "NOT_CAPTURED")]
    start = {r.shot_code: float(r.start_sec) for r in sh.itertuples() if r.start_sec != ""}
    damage = read_damage(_frames_by.get(case_id, []), start)
    return Findings(c.declared_reg_no, c.plate_ocr_text, c.chassis_last6_declared, c.chassis_last6_ocr,
                    num(c.lighting_score), num(c.blur_score), num(c.screen_moire_score),
                    num(c.capture_to_upload_hours), missing, bad, damage)


def list_cases():
    """The 420 gold cases, for the case picker."""
    return [{"case_id": r.case_id, "gold_decision": r.gold_decision} for r in gold.itertuples()]


def analyze(case_id: str) -> dict:
    if case_id not in _gold_by.index:
        raise KeyError(case_id)
    f = build_findings(case_id)
    d = decide(f)
    g = _gold_by.loc[case_id]
    c = cases.loc[case_id]
    return {
        "case_id": case_id,
        "decision": d.outcome,
        "gold_decision": g.gold_decision,
        "correct": d.outcome == g.gold_decision,
        "reasons": d.reasons,
        "route": d.route,
        "fraud_pattern": d.fraud_pattern,
        "damage_register": [asdict(x) for x in d.damage_register],
        "customer_message": d.customer_message,
        "evidence": {
            "plate_declared": f.plate_declared, "plate_read": f.plate_read,
            "chassis_declared": f.chassis_declared,
            "chassis_read": f.chassis_read, "lighting": f.lighting, "blur": f.blur, "moire": f.moire,
            "hours_since_capture": f.hours_since_capture, "missing_shots": f.missing_shots,
        },
        "frames": [{"shot": s, "description": t} for s, t in _frames_by.get(case_id, [])],
    }


def evaluate() -> dict:
    """Run all 420 and return the headline numbers for the evaluation page."""
    rows = [analyze(x["case_id"]) for x in list_cases()]
    ok = sum(r["correct"] for r in rows)
    by = {}
    for r in rows:
        by.setdefault(r["gold_decision"], [0, 0])
        by[r["gold_decision"]][0] += r["correct"]
        by[r["gold_decision"]][1] += 1
    return {"total": len(rows), "correct": ok, "accuracy": round(ok / len(rows), 4),
            "reviewer_accuracy": round(float((gold.original_reviewer_decision == gold.gold_decision).mean()), 4),
            "per_decision": {k: {"correct": v[0], "total": v[1]} for k, v in by.items()},
            "misses": [r["case_id"] for r in rows if not r["correct"]]}

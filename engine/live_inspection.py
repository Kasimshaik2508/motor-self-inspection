"""
live_inspection.py - a REAL customer inspection: photos in, decision with evidence out.

FLOW
  1. The phone already checked each photo (brightness, sharpness) and sends 12 JPEGs + those scores.
  2. vision.analyze() looks at the photos (shot, quality, plate, chassis, screen-photo, damage).
  3. build_findings() turns that into the SAME Findings object the 420-case evaluation uses...
  4. ...so decision_engine.decide() applies the unchanged SOP v2.4 rules.
  5. SOP routing on top of the engine:
       - second failed re-shoot  -> surveyor visit (SOP 4, 8)
       - plate and chassis disagree -> a person decides (SOP 13)
       - any damage the model is unsure about -> a reviewer confirms (low-confidence gate)
       - no cloud vision model -> use the PHONE's own results (car detected, plate / chassis OCR, dark / blur).
         Quality and identity problems are decided at once; damage is "not assessed by AI", so anything that
         would be approved goes to a reviewer to check damage. We NEVER auto-approve without a damage check.
  6. The record is kept for the reviewer console.

STORAGE: in memory only (the newest 50 inspections). A restart - or the free host going to sleep - empties it.
That is fine for a demo; a real product would use a database and object storage.
"""
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict

from decision_engine import Damage, Findings, decide, plate_relation, chassis_relation
import vision

LOW_CONFIDENCE = 0.6     # OUR choice: damage below this confidence is checked by a person. Not from the SOP.
STORE_LIMIT = 50
SESSION_MINUTES = 30     # OUR choice: all first-attempt photos should be taken in one go (one visit to the car).
                         # Photos spread over more time could come from different places or cars -> a person checks.
                         # The times come from the phone, so a determined cheater could fake them (see README).
_store = OrderedDict()   # id -> record (newest last)

PLAIN_SHOT = {c: c.replace("_45", " corner").replace("_", " ").lower() for c in vision.SHOT_CODES}


def _plain_reshoot(reasons):
    """SOP 8 + 11: ONE message that lists EVERY problem, in plain words, with how to fix it."""
    asks = []
    missing = [PLAIN_SHOT.get(r.split(":", 1)[1], r) for r in reasons if r.startswith("MISSING_SHOT:")]
    if missing:
        asks.append("take the missing or wrong photos: " + ", ".join(missing))
    if "TOO_DARK" in reasons:
        asks.append("the photos are too dark: please retake them in daylight or under a bright light")
    if "TOO_BLURRY" in reasons:
        asks.append("most photos are blurry: hold the phone with both hands and keep still")
    if "PLATE_UNREADABLE" in reasons:
        asks.append("we could not read the number plate: retake the front and rear photos a little closer")
    if "CHASSIS_UNREADABLE" in reasons:
        asks.append("we could not read the chassis number: retake that photo close up, with the last six characters clear")
    return "We could not complete the check yet. Please fix all of these and send again: " + \
        "; ".join(f"({i + 1}) {a}" for i, a in enumerate(asks)) + "."


DARK_BELOW, BLURRY_BELOW = 0.25, 40     # same first-guess thresholds as web/src/photo.js (uncalibrated)


def phone_results(phone_shots):
    """Per-shot results from the phone's free on-device checks, in the same shape vision.py returns."""
    out = []
    for s in phone_shots:
        quality = "DARK" if (s.get("brightness") or 1) < DARK_BELOW else \
            "BLURRY" if (s.get("sharpness") is not None and s["sharpness"] < BLURRY_BELOW) else "OK"
        car = s.get("car_detected")
        out.append({"shot": s["shot"], "answered": True,
                    "shows_expected_shot": car is not False,      # outside shot with no car in it = wrong photo
                    "quality": quality, "screen_photo": False,
                    "plate_text": s.get("plate_read") or "", "chassis_last6": (s.get("chassis_read") or "")[-6:],
                    "damage": []})
    return out


def build_findings(declared_plate, declared_chassis, phone_shots, vision_results):
    """phone_shots: [{shot, brightness, sharpness, captured_at_ms}]; vision_results: per-shot dicts from vision.py"""
    seen = {r["shot"]: r for r in vision_results}
    captured = [s["shot"] for s in phone_shots]
    missing = [c for c in vision.SHOT_CODES if c not in captured]
    missing += [r["shot"] for r in vision_results if not r["shows_expected_shot"]]   # wrong angle counts as missing
    bad = [(r["shot"], r["quality"]) for r in vision_results if r["quality"] != "OK"]

    # Front and rear are both read; use the reading closest to the plate on file. OCR misreads one photo far more
    # often than a car carries two different plates. Both readings stay visible to the reviewer (per-shot results).
    # Two readers look at each photo: the phone's OCR and (when on) the cloud model. Both readings count, and
    # every reading stays visible to the reviewer. Tested 11 Nov: the cloud model misread our chassis label the
    # same way three times while the phone read it right, so neither reader alone may send a customer to fraud.
    phone = {s["shot"]: s for s in phone_shots}
    reads = [t for c in ("FRONT", "REAR") for t in (seen.get(c, {}).get("plate_text"), phone.get(c, {}).get("plate_read")) if t]
    rank = {"MATCH": 0, "ONE_CHAR_SLIP": 1, "DIFFERENT": 2, "UNREADABLE": 3}
    plate_read = min(reads, key=lambda t: rank[plate_relation(declared_plate, t)], default="")
    chassis_reads = [t for t in (seen.get("CHASSIS_NUMBER", {}).get("chassis_last6"),
                                 (phone.get("CHASSIS_NUMBER", {}).get("chassis_read") or "")[-6:]) if t]
    chassis_read = min(chassis_reads, key=lambda t: rank.get(chassis_relation(declared_chassis, t), 3), default="")

    # Our own scores, NOT the capture SDK's: lighting = average photo brightness measured on the phone (0-1);
    # blur = share of photos the model called BLURRY. Both need calibrating on real test photos.
    lighting = sum(s.get("brightness", 0.5) for s in phone_shots) / max(1, len(phone_shots))
    blur = sum(1 for r in vision_results if r["quality"] == "BLURRY") / max(1, len(vision_results))
    # OUR mapping to the SOP's moire score: the model must flag 2+ photos as "photo of a screen" to count as a
    # screen-recording fraud signal. One flagged photo goes to a reviewer instead (see run()): tested 11 Nov,
    # Gemini flagged our drawn demo chassis label alone, which would have sent an honest customer to the fraud desk.
    moire = 0.9 if sum(1 for r in vision_results if r["screen_photo"]) >= 2 else 0.0
    oldest = min((s.get("captured_at_ms") or time.time() * 1000) for s in phone_shots) if phone_shots else time.time() * 1000
    hours = max(0.0, (time.time() * 1000 - oldest) / 3_600_000)

    best = {}
    for r in vision_results:
        for d in r["damage"]:
            dmg = Damage(d["panel"], d["kind"], d["severity"], r["shot"], None)
            if d["panel"] not in best or dmg.severity > best[d["panel"]].severity:
                best[d["panel"]] = dmg
    return Findings(declared_plate, plate_read, declared_chassis, chassis_read, round(lighting, 2), round(blur, 2),
                    moire, round(hours, 2), sorted(set(missing), key=vision.SHOT_CODES.index), bad, list(best.values()))


def run(declared_plate, declared_chassis, phone_shots, retake_of=None, rc=None):
    """phone_shots: [{shot, image_b64, brightness, sharpness, captured_at_ms}] -> stored record"""
    previous = _store.get(retake_of) if retake_of else None
    attempt = (previous["attempt"] + 1) if previous else 1
    rec = {"id": uuid.uuid4().hex[:8], "created_at": time.time(), "attempt": attempt, "retake_of": retake_of,
           "declared": {"plate": declared_plate, "chassis_last6": declared_chassis},
           "rc": rc,                            # the RC record the plate/chassis came from (None if typed)
           "photos": {s["shot"]: s["image_b64"] for s in phone_shots},
           "phone_checks": [{k: s.get(k) for k in ("shot", "brightness", "sharpness", "via")} for s in phone_shots],
           "review": None}
    extra = [s for s in phone_shots if s["shot"] not in vision.SHOT_CODES]      # RC card, damage close-ups
    phone_shots = [s for s in phone_shots if s["shot"] in vision.SHOT_CODES]   # only the SOP's 12 shots decide
    damage_checked = True
    try:
        results, vehicle, model = vision.analyze([(s["shot"], s["image_b64"]) for s in phone_shots])
        rec.update(vision_ok=True, model=model, vehicle=vehicle, per_shot=results)
    except vision.VisionUnavailable as e:
        results, damage_checked = phone_results(phone_shots), False
        rec.update(vision_ok=False, model="on-phone checks (car detector + OCR); damage not assessed by AI",
                   vehicle={}, per_shot=results, vision_error=str(e))

    f = build_findings(declared_plate, declared_chassis, phone_shots, results)
    d = decide(f)
    decision = asdict(d)
    hold = []
    message = d.customer_message
    if d.outcome == "RESHOOT":
        message = _plain_reshoot(d.reasons)
        if attempt >= 2:                                            # SOP: do not ask a third time
            decision["route"] = "SURVEYOR_VISIT"
            hold.append("SECOND_FAILED_ATTEMPT")
            message = "Thank you. We could not complete the check from the photos, so a surveyor will contact you to inspect the car in person."
    plate_rel = plate_relation(declared_plate, f.plate_read)
    chassis_rel = chassis_relation(declared_chassis, f.chassis_read)
    if {plate_rel, chassis_rel} == {"MATCH", "DIFFERENT"}:         # SOP 13: identity checks disagree -> a person
        hold.append("IDENTITY_CONFLICT")
    if not damage_checked and d.outcome in ("APPROVE", "APPROVE_WITH_EXCLUSIONS"):
        hold.append("DAMAGE_NOT_ASSESSED_BY_AI")                   # photos passed every check; a person checks damage
    unsure = [x for r in results for x in r["damage"] if x["confidence"] < LOW_CONFIDENCE]
    if unsure and d.outcome in ("APPROVE", "APPROVE_WITH_EXCLUSIONS"):
        hold.append("LOW_CONFIDENCE_DAMAGE")
    if d.route in ("FRAUD_DESK", "REVIEWER_CONFIRM"):
        hold.append(d.route)
    # Team rule (11 Nov): the AI may approve a car on its own only when it sees NO damage. Anything it reports
    # is confirmed by a person before it goes on the customer's record or changes their outcome.
    if damage_checked and any(r["damage"] for r in results) and d.route != "FRAUD_DESK":
        hold.append("AI_FOUND_DAMAGE")
    if sum(1 for r in results if r.get("screen_photo")) == 1 and d.route != "FRAUD_DESK":
        hold.append("ONE_PHOTO_LOOKS_LIKE_A_SCREEN")                  # a person decides; not enough for fraud
    # Anti-cheat checks (OUR rules, not the SOP's): only matter when the photos would otherwise pass.
    if d.outcome in ("APPROVE", "APPROVE_WITH_EXCLUSIONS"):
        times = [s["captured_at_ms"] for s in phone_shots + extra if s.get("captured_at_ms")]
        if not retake_of and times and (max(times) - min(times)) > SESSION_MINUTES * 60_000:
            hold.append("PHOTOS_NOT_IN_ONE_SESSION")
        if any(s.get("via") == "file" for s in phone_shots + extra):
            hold.append("PHOTO_FROM_FILE")                           # not the live camera: a person checks
        if any(s["shot"].startswith("DAMAGE_CLOSEUP") for s in extra):
            hold.append("CUSTOMER_REPORTED_DAMAGE")                  # customer showed damage: a person looks
    if any(h in hold for h in ("IDENTITY_CONFLICT", "LOW_CONFIDENCE_DAMAGE", "REVIEWER_CONFIRM", "AI_FOUND_DAMAGE", "ONE_PHOTO_LOOKS_LIKE_A_SCREEN", "PHOTOS_NOT_IN_ONE_SESSION",
                               "PHOTO_FROM_FILE", "CUSTOMER_REPORTED_DAMAGE")) and d.route != "FRAUD_DESK":
        message = "Thank you, we have your photos. A reviewer is confirming the result and will get back to you shortly."
    elif "DAMAGE_NOT_ASSESSED_BY_AI" in hold:
        message = ("All 12 photos passed our checks and your number plate and chassis number match. "
                   "A reviewer is now checking the photos for existing damage and will confirm shortly.")
    rec.update(findings=asdict(f), decision=decision, hold_reasons=hold,
               identity={"plate": plate_rel, "chassis": chassis_rel},
               status="NEEDS_REVIEW" if hold and "SECOND_FAILED_ATTEMPT" not in hold else "AI_DECIDED",
               customer_message=message)
    return _save(rec)


def _save(rec):
    _store[rec["id"]] = rec
    while len(_store) > STORE_LIMIT:
        _store.popitem(last=False)
    return rec


def customer_view(rec):
    """What the customer may see. Never fraud reasons, never internal routing (SOP 7 and 13)."""
    d = rec.get("decision") or {}
    final = (rec["review"] or {}).get("final_outcome") if rec["status"] == "REVIEWED" else \
        (d.get("outcome") if rec["status"] == "AI_DECIDED" else None)
    show_register = final == "APPROVE_WITH_EXCLUSIONS"
    retake = []
    if final == "RESHOOT" and rec["attempt"] < 2:
        retake = [r.split(":", 1)[1] for r in d.get("reasons", []) if r.startswith("MISSING_SHOT:")]
    if final == "REJECT" and d.get("route") == "FRAUD_DESK":
        final = None                                   # the customer is only told a surveyor will contact them
    if "SECOND_FAILED_ATTEMPT" in rec.get("hold_reasons", []) and rec["status"] != "REVIEWED":
        final = None                                   # not "reshoot" again: a surveyor visit is booked instead
    return {"id": rec["id"], "status": rec["status"], "attempt": rec["attempt"],
            "outcome": final,
            "message": rec["customer_message"],
            "damage_register": d.get("damage_register", []) if show_register else [],
            "retake_shots": retake, "can_retake": final == "RESHOOT" and rec["attempt"] < 2}


def reviewer_summary(rec):
    d = rec.get("decision") or {}
    return {"id": rec["id"], "created_at": rec["created_at"], "status": rec["status"], "attempt": rec["attempt"],
            "ai_outcome": d.get("outcome"), "route": d.get("route"), "hold_reasons": rec.get("hold_reasons", []),
            "plate": rec["declared"]["plate"], "car_no": (rec.get("rc") or {}).get("car_no"),
            "final_outcome": (rec["review"] or {}).get("final_outcome")}


def reviewer_detail(rec):
    return {k: v for k, v in rec.items()}


def review(inspection_id, action, final_outcome, reason, reviewer):
    """SOP 13: a reviewer can confirm or override any AI decision; overrides are logged with a reason."""
    rec = _store[inspection_id]
    if action not in ("CONFIRM", "OVERRIDE"):
        raise ValueError("action must be CONFIRM or OVERRIDE")
    ai = (rec.get("decision") or {}).get("outcome")
    if action == "CONFIRM":
        if not ai:
            raise ValueError("there is no AI decision to confirm; choose OVERRIDE and pick the outcome")
        final_outcome = ai
    elif final_outcome not in ("APPROVE", "APPROVE_WITH_EXCLUSIONS", "RESHOOT", "REJECT"):
        raise ValueError("pick the final outcome")
    if action == "OVERRIDE" and not reason.strip():
        raise ValueError("an override needs a reason (SOP 13)")
    rec["review"] = {"action": action, "final_outcome": final_outcome, "reason": reason.strip()[:500],
                     "reviewer": (reviewer or "reviewer").strip()[:60], "at": time.time()}
    rec["status"] = "REVIEWED"
    d = rec.get("decision") or {}
    if final_outcome == "APPROVE":
        msg = "Your car is approved and cover starts now."
    elif final_outcome == "APPROVE_WITH_EXCLUSIONS":
        items = ", ".join(f"{x['panel'].replace('_', ' ').lower()} ({x['kind'].lower()})" for x in d.get("damage_register", []))
        msg = ("Your car is approved and cover starts now. "
               + (f"We have recorded existing damage on: {items}. " if items else "We have recorded existing damage. ")
               + "Damage already present is not covered until it is repaired and re-inspected.")
    elif final_outcome == "RESHOOT":
        msg = _plain_reshoot(d.get("reasons", [])) if d.get("outcome") == "RESHOOT" else \
            "Please take the photos again, following the on-screen guide."
    else:  # REJECT
        severe = any(r.startswith("SEVERE") for r in d.get("reasons", []))
        if severe and d.get("route") != "FRAUD_DESK":
            msg = "Some damage must be repaired before cover can start. Please repair it and take a new inspection."
        else:
            msg = "Thank you. A surveyor will contact you to complete the inspection in person."  # never mention fraud
    rec["customer_message"] = msg
    return rec


def all_records():
    return list(reversed(_store.values()))


def get(inspection_id):
    return _store[inspection_id]

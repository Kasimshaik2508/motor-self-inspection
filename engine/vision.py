"""
vision.py - the "eyes": sends the customer's photos to a vision-language model and gets back what it sees.

WHY a separate, swappable file: the decision engine must not care WHICH model looked at the photos.
     Swap models with one setting, compare them on the same photos, and keep the SOP rules untouched.
HOW: one request PER PHOTO, sent in parallel (a single 12-photo request made the model copy answers between
     photos; see analyze()).
     The model answers in strict JSON per photo: is it the right shot, is it usable, plate / chassis text,
     screen-photo suspicion, and every visible damage with panel, type, severity and confidence.
     We then CLEAN the answer: unknown panels -> OTHER, unknown damage types dropped, severities forced into
     the SOP's ranges (scratch 1-2, crack 2-3, broken/missing 3, paint mismatch 1).

Settings (environment variables; keys live only in the host's settings, never in code):
  VISION_PROVIDER   gemini | openrouter | none      (default: none -> photos go straight to a reviewer)
  GEMINI_API_KEY    + optional GEMINI_MODEL          (default gemini-3.1-flash-lite: cheapest; tested 11 Nov)
  OPENROUTER_API_KEY + optional OPENROUTER_MODEL     (default qwen/qwen-2.5-vl-7b-instruct:free)
  Gemini's FREE tier may use what you send to improve Google's products: use it only for test photos of
  cars you have permission to photograph, never for real customers.
TESTED 11 Nov (one photo per request, see README): Gemini 3.1 Flash-Lite caught 98/100 damaged cars and 7/7
damaged Indian cars, and wrongly flagged 3 of 92 clean cars. NOT yet tested: small scratches on a real car, and
how well it does with all 12 photos in one request (what the app sends).
"""
import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request

# The 12 required shots (SOP section 3): code -> what the customer should capture
SHOTS = [
    ("FRONT", "Whole front of the car, number plate readable, both headlamps"),
    ("FRONT_LEFT_45", "Front-left corner: front bumper corner, left front door, headlamp"),
    ("LEFT_SIDE", "Whole left side: both left doors and the body line"),
    ("REAR_LEFT_45", "Rear-left corner: left rear door, rear bumper corner, tail lamp"),
    ("REAR", "Whole rear of the car, number plate readable, boot lid"),
    ("REAR_RIGHT_45", "Rear-right corner: right rear door, rear bumper corner, tail lamp"),
    ("RIGHT_SIDE", "Whole right side: both right doors"),
    ("FRONT_RIGHT_45", "Front-right corner: front bumper corner, right front door, headlamp"),
    ("ROOF_AND_GLASS", "Roof and windscreen, from a raised angle"),
    ("ODOMETER", "Instrument cluster with the odometer readable, ignition on"),
    ("CHASSIS_NUMBER", "Engraved chassis number (VIN plate), last six characters readable"),
    ("ENGINE_BAY", "Engine bay with the bonnet open"),
]
SHOT_CODES = [c for c, _ in SHOTS]

# The order and tips the CUSTOMER app uses (11 Nov, after studying a real insurer's self-inspection demo):
# documents and the inside first (sitting in the driver's seat), then chassis and engine with the bonnet open, then
# close the bonnet and walk around the car. Two kinds of extra photos are NOT part of the SOP's 12 shots and never
# change the AI decision; they are for the reviewer: the RC card (required by the app) and up to 3 optional damage
# close-ups. Tips are what the customer reads; "what" (above) is what the photo must show.
_TIP_WALK = "Walk around the car. Don't zoom: step closer or farther instead."
CAPTURE = [
    {"code": "RC_CARD", "what": "Your RC (registration certificate) card, front side, all text readable",
     "tip": "Hold it flat in daylight so it fills most of the frame.", "required": True, "sop": False},
    {"code": "ODOMETER", "tip": "Sit in the driver's seat with the engine on. Show the TOTAL kilometres "
     "(odometer), not the trip meter: a trip reading means a retake."},
    {"code": "CHASSIS_NUMBER", "tip": "It is ENGRAVED in the metal: usually under the bonnet near the windscreen, "
     "or on a metal plate at the driver or passenger door pillar. Not the sticker on the windscreen. "
     "Don't zoom: move closer."},
    {"code": "ENGINE_BAY", "tip": "Then close the bonnet for the outside photos."},
    {"code": "FRONT", "tip": "Stand about 3 metres in front so the whole car and the number plate are in the frame."},
    {"code": "FRONT_LEFT_45", "tip": _TIP_WALK},
    {"code": "LEFT_SIDE", "tip": _TIP_WALK},
    {"code": "REAR_LEFT_45", "tip": _TIP_WALK},
    {"code": "REAR", "tip": "Make sure the rear number plate is sharp and readable."},
    {"code": "REAR_RIGHT_45", "tip": _TIP_WALK},
    {"code": "RIGHT_SIDE", "tip": _TIP_WALK},
    {"code": "FRONT_RIGHT_45", "tip": _TIP_WALK},
    {"code": "ROOF_AND_GLASS", "tip": "Hold the phone up high to show the roof and the windscreen."},
] + [{"code": f"DAMAGE_CLOSEUP_{i}", "what": "Close-up of a scratch, dent or crack (optional)",
      "tip": "Only if your car has damage: move close, don't zoom. Skip if there is none.",
      "required": False, "sop": False} for i in (1, 2, 3)]
for _c in CAPTURE:
    _c.setdefault("what", dict(SHOTS).get(_c["code"], ""))
    _c.setdefault("required", True)
    _c.setdefault("sop", True)
CAPTURE_CODES = [c["code"] for c in CAPTURE]
assert sorted(c["code"] for c in CAPTURE if c["sop"]) == sorted(SHOT_CODES)   # all 12 SOP shots, each once
PANELS = ["FRONT_BUMPER", "REAR_BUMPER", "BONNET", "ROOF", "WINDSHIELD", "BOOT_TAILGATE", "HEADLAMPS", "TAIL_LAMPS",
          "LEFT_FRONT_DOOR", "LEFT_REAR_DOOR", "RIGHT_FRONT_DOOR", "RIGHT_REAR_DOOR", "OTHER"]
KINDS = ["SCRATCH", "DENT", "CRACK", "BROKEN", "MISSING", "PAINT_MISMATCH"]
QUALITIES = ["OK", "DARK", "BLURRY", "TOO_FAR", "OBSTRUCTED"]


class VisionUnavailable(Exception):
    """No model configured, or the model call failed. The app then sends the photos to a human reviewer."""


def _prompt(shots):
    lines = [f"Image {i + 1}: should show {code} - {dict(SHOTS)[code]}" for i, (code, _) in enumerate(shots)]
    return f"""You are a motor-insurance inspector in India checking a customer's photos of their own car before cover starts.
There are {len(shots)} images, in this order:
{chr(10).join(lines)}

For EACH image return one object. Report ONLY real, visible body damage on the customer's car: dents, scratches,
cracks, broken glass or lamps, missing or crushed parts. Do NOT report reflections, shadows, dirt, dust, water
spots, stickers, badges, tinted glass, design lines or panel gaps (these caused most false alarms in our tests).
If you are unsure whether something is damage, report it with a LOW confidence: a person will check it.
Severity guide: 1 = minor/cosmetic (scratch under 10 cm, coin-sized dent); 2 = moderate (needs panel work or a part);
3 = severe (broken or missing part, crease across a panel, windscreen crack in the driver's view).

Return ONLY JSON in exactly this shape:
{{"shots": [{{"index": 1,
  "shows_expected_shot": true,
  "quality": "OK" | "DARK" | "BLURRY" | "TOO_FAR" | "OBSTRUCTED",
  "looks_like_photo_of_a_screen": false,
  "plate_text": "number plate characters if readable, else empty",
  "chassis_last6": "last six characters of the chassis/VIN if this image shows it and they are readable, else empty",
  "damage": [{{"panel": one of {PANELS},
              "kind": one of {KINDS},
              "severity": 1 | 2 | 3,
              "description": "short plain description, with size if visible",
              "confidence": number from 0 to 1}}]
}}],
 "vehicle": {{"make": "", "model": "", "colour": ""}}}}"""


def _post(url, headers, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise VisionUnavailable(f"model call failed (HTTP {e.code}): {detail}")   # never includes the key
    except Exception as e:
        raise VisionUnavailable(f"model call failed ({type(e).__name__})")


def _gemini(shots):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise VisionUnavailable("GEMINI_API_KEY is not set on the server")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    parts = [{"text": _prompt(shots)}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b64}} for _, b64 in shots]
    out = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                {"x-goog-api-key": key},
                {"contents": [{"parts": parts}],
                 "generationConfig": {"temperature": 0, "response_mime_type": "application/json"}})
    try:
        return out["candidates"][0]["content"]["parts"][0]["text"], f"gemini:{model}"
    except (KeyError, IndexError):
        raise VisionUnavailable("the model returned no answer (it may have blocked the request)")


def _openrouter(shots):
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise VisionUnavailable("OPENROUTER_API_KEY is not set on the server")
    model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen-2.5-vl-7b-instruct:free")
    content = [{"type": "text", "text": _prompt(shots)}] + [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}} for _, b64 in shots]
    out = _post("https://openrouter.ai/api/v1/chat/completions", {"Authorization": f"Bearer {key}"},
                {"model": model, "temperature": 0, "messages": [{"role": "user", "content": content}]})
    try:
        return out["choices"][0]["message"]["content"], f"openrouter:{model}"
    except (KeyError, IndexError):
        raise VisionUnavailable("the model returned no answer")


def _clean_severity(kind, sev):
    sev = max(1, min(3, int(sev or 1)))
    if kind in ("BROKEN", "MISSING"):
        return 3
    if kind == "PAINT_MISMATCH":
        return 1
    if kind == "SCRATCH":
        return min(sev, 2)
    if kind == "CRACK":
        return max(sev, 2)
    return sev


def clean_damage(items):
    """Any damage list (from a cloud model or the phone's models) -> only SOP panels/kinds, SOP severity ranges."""
    damage = []
    for d in (items or [])[:20]:
        if not isinstance(d, dict):
            continue
        kind = str(d.get("kind", "")).upper()
        if kind not in KINDS:
            continue
        panel = str(d.get("panel", "OTHER")).upper()
        try:
            conf = float(d.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        try:
            sev = _clean_severity(kind, d.get("severity"))
        except (TypeError, ValueError):
            sev = _clean_severity(kind, 1)
        damage.append({"panel": panel if panel in PANELS else "OTHER", "kind": kind, "severity": sev,
                       "description": str(d.get("description", ""))[:200],
                       "confidence": round(max(0.0, min(1.0, conf)), 2)})
    return damage


def _parse(text, shots):
    """Turn the model's text into clean per-shot dicts, whatever small mistakes it made."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise VisionUnavailable("the model's answer was not valid JSON")
        data = json.loads(m.group(0))
    by_index = {int(s.get("index", i + 1)): s for i, s in enumerate(data.get("shots", []))}
    results = []
    for i, (code, _) in enumerate(shots):
        s = by_index.get(i + 1, {})
        damage = clean_damage(s.get("damage"))
        quality = str(s.get("quality", "OK")).upper()
        results.append({
            "shot": code,
            "answered": bool(s),
            "shows_expected_shot": bool(s.get("shows_expected_shot", True)),
            "quality": quality if quality in QUALITIES else "OK",
            "screen_photo": bool(s.get("looks_like_photo_of_a_screen", False)),
            "plate_text": str(s.get("plate_text", "") or "")[:20],
            "chassis_last6": re.sub(r"[^A-Z0-9]", "", str(s.get("chassis_last6", "") or "").upper())[-6:],
            "damage": damage,
        })
    return results, data.get("vehicle", {})


def analyze(shots):
    """
    shots: list of (shot_code, base64_jpeg) for the photos the customer took.
    returns: (per_shot_results, vehicle, model_name)   or raises VisionUnavailable.
    """
    provider = os.environ.get("VISION_PROVIDER", "none").strip().lower()
    if provider not in ("gemini", "openrouter"):
        raise VisionUnavailable("no vision model is configured (VISION_PROVIDER is 'none')")
    call = _gemini if provider == "gemini" else _openrouter

    # ONE PHOTO PER REQUEST (tested 11 Nov): with all 12 photos in one request the model assumed they showed one
    # car, missed two swapped-in damaged cars and copied the plate onto a different car's photo. One photo at a
    # time it caught 98/100 damaged cars. Requests run in parallel so the customer waits about as long as for one.
    def one(shot):
        for attempt, wait in enumerate((5, 15, 25, None)):
            try:
                text, name = call([shot])
                (r,), vehicle = _parse(text, [shot])
                return r, vehicle, name
            except VisionUnavailable as e:
                # "too many requests" (free tier: about 15 a minute; one inspection is 12) or a busy server:
                # wait and retry. After the last try the whole check fails safely: a reviewer checks damage.
                if wait is None or not any(code in str(e) for code in ("429", "500", "503")):
                    raise
                time.sleep(wait)
    with ThreadPoolExecutor(max_workers=6) as pool:
        answers = list(pool.map(one, shots))
    results = [r for r, _, _ in answers]
    front = [v for (r, v, _), (code, _) in zip(answers, shots) if code == "FRONT" and v.get("make")]
    vehicle = front[0] if front else next((v for _, v, _ in answers if v.get("make")), {})
    return results, vehicle, answers[0][2] + " (one photo per request)"


def check_base64_image(b64):
    """Small sanity check so a broken upload fails clearly: must be a JPEG under ~3 MB."""
    raw = base64.b64decode(b64, validate=True)
    if len(raw) > 3_000_000:
        raise ValueError("photo larger than 3 MB")
    if raw[:3] != b"\xff\xd8\xff":
        raise ValueError("photo is not a JPEG")
    return len(raw)

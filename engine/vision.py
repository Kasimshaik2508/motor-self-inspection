"""
vision.py - the "eyes": sends the customer's photos to a vision-language model and gets back what it sees.

WHY a separate, swappable file: the decision engine must not care WHICH model looked at the photos.
     Swap models with one setting, compare them on the same photos, and keep the SOP rules untouched.
HOW: ONE request with all the photos (faster, and kinder to free-tier rate limits than 12 requests).
     The model answers in strict JSON per photo: is it the right shot, is it usable, plate / chassis text,
     screen-photo suspicion, and every visible damage with panel, type, severity and confidence.
     We then CLEAN the answer: unknown panels -> OTHER, unknown damage types dropped, severities forced into
     the SOP's ranges (scratch 1-2, crack 2-3, broken/missing 3, paint mismatch 1).

Settings (environment variables; keys live only in the host's settings, never in code):
  VISION_PROVIDER   gemini | openrouter | none      (default: none -> photos go straight to a reviewer)
  GEMINI_API_KEY    + optional GEMINI_MODEL          (default gemini-2.5-flash)
  OPENROUTER_API_KEY + optional OPENROUTER_MODEL     (default qwen/qwen-2.5-vl-7b-instruct:free)
  Gemini's FREE tier may use what you send to improve Google's products: use it only for test photos of
  cars you have permission to photograph, never for real customers.
UNTESTED: how accurate any of these models is on real car photos. Measure it on your own test photos.
"""
import base64
import json
import os
import re
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
PANELS = ["FRONT_BUMPER", "REAR_BUMPER", "BONNET", "ROOF", "WINDSHIELD", "BOOT_TAILGATE", "HEADLAMPS", "TAIL_LAMPS",
          "LEFT_FRONT_DOOR", "LEFT_REAR_DOOR", "RIGHT_FRONT_DOOR", "RIGHT_REAR_DOOR", "OTHER"]
KINDS = ["SCRATCH", "DENT", "CRACK", "BROKEN", "MISSING", "PAINT_MISMATCH"]
QUALITIES = ["OK", "DARK", "BLURRY", "TOO_FAR", "OBSTRUCTED"]


class VisionUnavailable(Exception):
    """No model configured, or the model call failed. The app then sends the photos to a human reviewer."""


def _prompt(shots):
    lines = [f"Image {i + 1}: should show {code} - {dict(SHOTS)[code]}" for i, (code, _) in enumerate(shots)]
    return f"""You are a motor-insurance inspector checking a customer's photos of their own car before cover starts.
There are {len(shots)} images, in this order:
{chr(10).join(lines)}

For EACH image return one object. Report only what is visible. If you are unsure whether damage is present,
include it with a LOW confidence rather than leaving it out (a missed damage becomes a paid claim).
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
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
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
        damage = []
        for d in s.get("damage", []) or []:
            kind = str(d.get("kind", "")).upper()
            if kind not in KINDS:
                continue
            panel = str(d.get("panel", "OTHER")).upper()
            try:
                conf = float(d.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            damage.append({"panel": panel if panel in PANELS else "OTHER", "kind": kind,
                           "severity": _clean_severity(kind, d.get("severity")),
                           "description": str(d.get("description", ""))[:200],
                           "confidence": round(max(0.0, min(1.0, conf)), 2)})
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
    if provider == "gemini":
        text, name = _gemini(shots)
    elif provider == "openrouter":
        text, name = _openrouter(shots)
    else:
        raise VisionUnavailable("no vision model is configured (VISION_PROVIDER is 'none')")
    results, vehicle = _parse(text, shots)
    return results, vehicle, name


def check_base64_image(b64):
    """Small sanity check so a broken upload fails clearly: must be a JPEG under ~3 MB."""
    raw = base64.b64decode(b64, validate=True)
    if len(raw) > 3_000_000:
        raise ValueError("photo larger than 3 MB")
    if raw[:3] != b"\xff\xd8\xff":
        raise ValueError("photo is not a JPEG")
    return len(raw)

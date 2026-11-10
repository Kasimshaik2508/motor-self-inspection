"""Run from the repo root:  python tests/test_live_routes.py
Feeds SCRIPTED model answers (no real model, no photos) through the live photo flow and prints the outcome of
each SOP route. It checks the ROUTING logic only; it says nothing about how accurate a real vision model is."""
# Scripted model answers -> check every SOP route of the live photo flow. Not a test of model accuracy.
import sys, time, json
sys.path.insert(0, "engine")
import vision, live_inspection as L

def shot(code, quality="OK", ok=True, screen=False, plate="", chassis="", damage=()):
    return {"index": 0, "shows_expected_shot": ok, "quality": quality, "looks_like_photo_of_a_screen": screen,
            "plate_text": plate, "chassis_last6": chassis, "damage": list(damage)}

def model_says(per_code, skip=()):
    codes = [c for c in vision.SHOT_CODES if c not in skip]
    def fake(shots):
        data = {"shots": [dict(per_code.get(c, shot(c)), index=i + 1) for i, (c, _) in enumerate(shots)], "vehicle": {}}
        return vision._parse(json.dumps(data), shots)[0], {}, "scripted"
    vision.analyze = fake
    return [{"shot": c, "image_b64": "x", "brightness": 0.5, "sharpness": 200, "captured_at_ms": time.time() * 1000} for c in codes]

base = {"FRONT": shot("FRONT", plate="KA01AB1234"), "CHASSIS_NUMBER": shot("CHASSIS_NUMBER", chassis="123456")}
def run(name, extra=None, skip=(), plate="KA 01 AB 1234", retake_of=None, bright=None):
    phone = model_says({**base, **(extra or {})}, skip)
    if bright is not None:
        for p in phone: p["brightness"] = bright
    r = L.run(plate, "123456", phone, retake_of)
    c = L.customer_view(r)
    print(f"{name:34s} AI={str((r['decision'] or {}).get('outcome')):24s} status={r['status']:13s} hold={r['hold_reasons']}\n{'':34s} customer sees outcome={c['outcome']} | {c['message'][:110]}")
    return r

dent = {"panel": "REAR_BUMPER", "kind": "DENT", "severity": 1, "description": "5 cm dent", "confidence": 0.9}
run("1 clean car")
run("2 minor dent, confident", {"REAR": shot("REAR", plate="KA01AB1234", damage=[dent])})
run("3 minor dent, UNSURE", {"REAR": shot("REAR", damage=[dict(dent, confidence=0.4)])})
run("4 broken headlamp (severe)", {"FRONT_LEFT_45": shot("FRONT_LEFT_45", damage=[{"panel": "HEADLAMPS", "kind": "BROKEN", "severity": 1, "confidence": 0.9}])})
r1 = run("5 two photos skipped", skip=("LEFT_SIDE", "ENGINE_BAY"))
run("6 retake fails again -> surveyor", skip=("LEFT_SIDE",), retake_of=r1["id"])
run("7 too dark", bright=0.1)
run("8 plate ok, chassis DIFFERENT", {"CHASSIS_NUMBER": shot("CHASSIS_NUMBER", chassis="999999")})
run("9 one-char plate slip, chassis ok", {"FRONT": shot("FRONT", plate="KA01AB1Z34")})
run("10 photo of a screen", {"REAR": shot("REAR", screen=True)})
run("11 wrong angle for left side", {"LEFT_SIDE": shot("LEFT_SIDE", ok=False)})
print("scratch severity clamp (model said 3):", vision._clean_severity("SCRATCH", 3), "| crack said 1:", vision._clean_severity("CRACK", 1))

"""
frame_reader.py  -  turns a written frame description into damage findings

WHY: the pack has no video, only a sentence per shot ("The front bumper shows a 5 cm scratch.").
     This file reads those sentences the way the vision model will later read real frames, and
     hands the decision engine a list of Damage(panel, kind, severity, shot, second).
     Same output shape as the future vision layer, so the engine does not care which one made it.

HOW: three small steps per sentence
     1. find the panel   ("front bumper" -> FRONT_BUMPER)
     2. find the type    (scratch / dent / crack / broken / missing / paint mismatch)
     3. grade severity   from SOP section 5 anchors + a size ladder (see below)

THE SEVERITY LADDER IS OUR JUDGEMENT, NOT THE SOP'S. The SOP gives anchors only:
     scratch < 10 cm = 1 ... broken or missing part = 3 ... crack = 2 or 3 ... paint mismatch = 1.
     We read size words onto three steps (fixed BEFORE looking at any gold answer):
       step 1: shallow, minor, small, 5 cm
       step 2: palm-sized, medium, noticeable, 15 cm
       step 3: large, severe, deep, 30 cm
     scratch is capped at 2, crack has a floor of 2, broken / missing is always 3.
     The problem owner should confirm this ladder.
"""
import re
from decision_engine import Damage

# longest names first so "right front door" is found before "door"
PANELS = [
    ("right front door", "RIGHT_FRONT_DOOR"), ("right rear door", "RIGHT_REAR_DOOR"),
    ("left front door", "LEFT_FRONT_DOOR"), ("left rear door", "LEFT_REAR_DOOR"),
    ("front bumper", "FRONT_BUMPER"), ("rear bumper", "REAR_BUMPER"),
    ("tail lamps", "TAIL_LAMPS"), ("tail lamp", "TAIL_LAMPS"),
    ("headlamps", "HEADLAMPS"), ("headlamp", "HEADLAMPS"),
    ("windshield", "WINDSHIELD"), ("windscreen", "WINDSHIELD"),
    ("boot lid", "BOOT_TAILGATE"), ("tailgate", "BOOT_TAILGATE"),
    ("bonnet", "BONNET"), ("roof", "ROOF"),
]

# order matters: the first rule that matches decides the type
KINDS = [
    ("MISSING", ["missing"]),
    ("BROKEN", ["broken", "shattered", "hanging loose"]),
    ("PAINT_MISMATCH", ["repaint", "different shade"]),
    ("CRACK", ["crack"]),
    ("DENT", ["dent"]),
    ("SCRATCH", ["scratch", "scuff"]),
]

STEP3 = ["large", "severe", "deep", "30 cm"]
STEP2 = ["palm-sized", "medium", "noticeable", "15 cm"]


def _step(text: str) -> int:
    t = text.lower()
    if any(w in t for w in STEP3):
        return 3
    if any(w in t for w in STEP2):
        return 2
    return 1  # shallow / minor / small / 5 cm, or no size word at all


def _severity(kind: str, text: str) -> int:
    if kind in ("BROKEN", "MISSING"):
        return 3                       # SOP: broken or missing part = severity 3
    if kind == "PAINT_MISMATCH":
        return 1                       # SOP: record it, severity 1
    step = _step(text)
    if kind == "SCRATCH":
        return min(step, 2)            # SOP: scratches are 1 or 2
    if kind == "CRACK":
        return max(step, 2)            # SOP: cracks are 2 or 3
    return step                        # DENT: 1 (coin-sized) to 3 (crease)


def _sentences(description: str):
    return [s.strip() for s in re.split(r"(?<=\.)\s+", description) if s.strip()]


def read_damage(frames, shot_start=None):
    """
    frames: list of (shot_code, description) for ONE case
    shot_start: optional {shot_code: second the shot starts}, used as the evidence second
    returns: list[Damage], one per panel (the worst reading if several shots mention it)
    """
    shot_start = shot_start or {}
    best = {}
    for shot, desc in frames:
        for s in _sentences(desc):
            low = s.lower().replace("paint cracking", "")  # 'dent with paint cracking at the edge' is a dent, not a crack
            panel = next((code for name, code in PANELS if name in low), None)
            kind = next((k for k, words in KINDS if any(w in low for w in words)), None)
            if not panel or not kind:
                continue
            # only sentences that describe damage ("... shows ...") - skips "Nothing notable." etc.
            if " shows " not in low and " has " not in low:
                continue
            d = Damage(panel, kind, _severity(kind, low), shot, shot_start.get(shot))
            if panel not in best or d.severity > best[panel].severity:
                best[panel] = d
    return list(best.values())

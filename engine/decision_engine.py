"""
PS-03 decision engine  (the "rules" half of the product)

WHY THIS FILE EXISTS
  The vision model (Gemini, added later) only REPORTS what it sees in the video.
  This file DECIDES. It takes those findings and applies the PolicyNest SOP v2.4 as
  plain if/else rules, so every decision can be explained and tested.

HOW IT WORKS (one pass, first rule that fires wins)
  1. FRAUD    -> REJECT, send to fraud desk (customer is never told it is fraud)
  2. QUALITY  -> RESHOOT (missing / dark / blurry / unreadable plate or chassis)
  3. SEVERE   -> REJECT (severity 3 anywhere; a reviewer confirms before customer is told)
  4. MINOR    -> APPROVE_WITH_EXCLUSIONS (severity 1-2, written into the damage register)
  5. CLEAN    -> APPROVE
  Fraud still records the damage it saw; it only decides the outcome.
"""
from dataclasses import dataclass, field
from typing import Optional

# ---- thresholds: every number has a source -------------------------------------------
LIGHTING_MIN = 0.35        # SOP section 8: lighting score below 0.35 -> re-shoot
BLUR_MAX = 0.60            # SOP section 8: blur score above 0.6 -> re-shoot
OLD_VIDEO_HOURS = 72       # SOP section 7: recorded more than 72 hours before upload
MOIRE_MIN = 0.40           # OUR choice: in the 3,180 non-gold cases the bulk sits below 0.3
                           #   and the tail starts around 0.4. SOP gives no number.


@dataclass
class Damage:
    panel: str
    kind: str                # SCRATCH / DENT / CRACK / BROKEN / MISSING / PAINT_MISMATCH
    severity: int            # 1 minor, 2 moderate, 3 severe
    shot: Optional[str] = None      # evidence: which shot ...
    second: Optional[float] = None  # ... and which second (filled by the vision layer)


@dataclass
class Findings:
    """Everything the engine needs to know about one video."""
    plate_declared: str
    plate_read: str
    chassis_declared: str
    chassis_read: str
    lighting: float
    blur: float
    moire: float
    hours_since_capture: float
    missing_shots: list = field(default_factory=list)
    bad_shots: list = field(default_factory=list)      # [(shot_code, quality)]
    damage: list = field(default_factory=list)         # [Damage]


@dataclass
class Decision:
    outcome: str
    reasons: list
    fraud_pattern: str = "NONE"
    route: str = "NONE"                 # NONE / FRAUD_DESK / REVIEWER_CONFIRM
    damage_register: list = field(default_factory=list)
    customer_message: str = ""


# ---- identity checks (SOP section 6) ---------------------------------------------------
def _norm(s) -> str:
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def plate_relation(declared, read) -> str:
    """MATCH, ONE_CHAR_SLIP (probably an OCR error), DIFFERENT, or UNREADABLE."""
    a, b = _norm(declared), _norm(read)
    if not b:
        return "UNREADABLE"
    if a == b:
        return "MATCH"
    if len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1:
        return "ONE_CHAR_SLIP"
    return "DIFFERENT"


def chassis_relation(declared, read) -> str:
    a, b = _norm(declared), _norm(read)
    if not b:
        return "UNREADABLE"
    return "MATCH" if a == b else "DIFFERENT"


# ---- the three families of checks ------------------------------------------------------
def fraud_signals(f: Findings) -> list:
    """Returns fraud patterns that fired, in priority order."""
    out = []
    plate = plate_relation(f.plate_declared, f.plate_read)
    chassis = chassis_relation(f.chassis_declared, f.chassis_read)
    # chassis is the strongest check; any plate difference beyond a one-char slip is a mismatch
    if chassis == "DIFFERENT" or plate == "DIFFERENT":
        out.append("VEHICLE_MISMATCH")
    if f.hours_since_capture > OLD_VIDEO_HOURS:
        out.append("OLD_VIDEO")
    if f.moire >= MOIRE_MIN:
        out.append("SCREEN_RECORDING")
    return out


def quality_problems(f: Findings) -> list:
    # SOP section 8 lists the ONLY re-shoot triggers. A single soft / far / partly-blocked shot is NOT one
    # (section 12 calls those "re-shoots that are not needed"), so per-shot tags are not used on their own.
    out = [f"MISSING_SHOT:{s}" for s in f.missing_shots]
    dark_shots = sum(1 for _, q in f.bad_shots if q == "DARK")
    if f.lighting < LIGHTING_MIN or dark_shots > 6:       # "lighting below 0.35 or MOST shots tagged DARK"
        out.append("TOO_DARK")
    if f.blur > BLUR_MAX:
        out.append("TOO_BLURRY")
    if plate_relation(f.plate_declared, f.plate_read) == "UNREADABLE":
        out.append("PLATE_UNREADABLE")
    if chassis_relation(f.chassis_declared, f.chassis_read) == "UNREADABLE":
        out.append("CHASSIS_UNREADABLE")
    return out


# ---- customer messages (SOP section 11) --------------------------------------------------
def _message(outcome, reasons, register) -> str:
    if outcome == "APPROVE":
        return "Your car is approved and cover starts now."
    if outcome == "APPROVE_WITH_EXCLUSIONS":
        items = ", ".join(f"{d.panel.replace('_', ' ').lower()} ({d.kind.lower()})" for d in register)
        return (f"Your car is approved and cover starts now. We have recorded existing damage on: {items}. "
                "Damage already present is not covered until it is repaired and re-inspected.")
    if outcome == "RESHOOT":
        return ("We could not complete the check. Please record a new video fixing all of these: "
                + "; ".join(reasons))
    if any(r.startswith("SEVERE") for r in reasons):
        return "Some damage must be repaired before cover can start. Please repair it and record a new inspection video."
    return "Thank you. A surveyor will contact you to complete the inspection in person."  # never mention fraud


# ---- the decision itself -----------------------------------------------------------------
def decide(f: Findings) -> Decision:
    register = [d for d in f.damage if d.severity > 0]          # always recorded, whatever the outcome
    fraud = fraud_signals(f)
    if fraud:
        reasons = [f"FRAUD_SUSPECTED_{p}" for p in fraud]
        return Decision("REJECT", reasons, fraud[0], "FRAUD_DESK", register,
                        _message("REJECT", reasons, register))
    quality = quality_problems(f)
    if quality:
        return Decision("RESHOOT", quality, "NONE", "NONE", register, _message("RESHOOT", quality, register))
    severe = [d for d in register if d.severity >= 3]
    if severe:
        reasons = [f"SEVERE_DAMAGE:{d.panel}:{d.kind}" for d in severe]
        return Decision("REJECT", reasons, "NONE", "REVIEWER_CONFIRM", register, _message("REJECT", reasons, register))
    if register:
        reasons = [f"PRE_EXISTING_DAMAGE:{d.panel}" for d in register]
        return Decision("APPROVE_WITH_EXCLUSIONS", reasons, "NONE", "NONE", register,
                        _message("APPROVE_WITH_EXCLUSIONS", reasons, register))
    return Decision("APPROVE", ["CLEAN"], "NONE", "NONE", [], _message("APPROVE", [], []))

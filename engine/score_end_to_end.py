"""
End-to-end test on the 420 gold cases with NO gold damage as input.
  inputs  : case metadata + shot_log + frame descriptions (read by frame_reader)
  engine  : decision_engine.decide
  truth   : gold_decision (evaluation set) and gold damage per panel (panel_damage sheet)

Damage recall is measured the way the Brief measures reviewer misses: only on damaged panels that were
VISIBLE in the video (panel_damage.visible_in_video).
"""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decision_engine import Findings, decide
from frame_reader import read_damage
from score_on_gold import cases, shots_by, panels_by, gold, num, read, EVAL

frames = read(EVAL, "frame_descriptions")
frames_by = {k: list(zip(v.shot_code, v.frame_description)) for k, v in frames.groupby("case_id")}


def build(case_id):
    c, sh = cases.loc[case_id], shots_by[case_id]
    missing = sh.loc[sh.captured != "True", "shot_code"].tolist()
    bad = [(r.shot_code, r.shot_quality) for r in sh.itertuples() if r.shot_quality not in ("OK", "NOT_CAPTURED")]
    start = {r.shot_code: float(r.start_sec) for r in sh.itertuples() if r.start_sec != ""}
    dmg = read_damage(frames_by.get(case_id, []), start)
    return Findings(c.declared_reg_no, c.plate_ocr_text, c.chassis_last6_declared, c.chassis_last6_ocr,
                    num(c.lighting_score), num(c.blur_score), num(c.screen_moire_score),
                    num(c.capture_to_upload_hours), missing, bad, dmg)


rows, dm_rows = [], []
for g in gold.itertuples():
    f = build(g.case_id)
    d = decide(f)
    hour = int(cases.loc[g.case_id].capture_local_time.split(":")[0])
    rows.append(dict(case_id=g.case_id, gold=g.gold_decision, pred=d.outcome, night=(hour < 6 or hour >= 19),
                     reviewer=g.original_reviewer_decision, reasons="; ".join(d.reasons)))
    found = {x.panel: x for x in f.damage}
    for p in panels_by[g.case_id].itertuples():
        gold_sev = int(p.gold_severity)
        rev_sev = int(p.reviewer_recorded_severity or 0)
        hit = found.get(p.panel)
        dm_rows.append(dict(case_id=g.case_id, panel=p.panel, visible=p.visible_in_video == "True",
                            gold_type=p.gold_damage_type, gold_sev=gold_sev,
                            found=hit is not None, f_type=hit.kind if hit else "", f_sev=hit.severity if hit else 0,
                            rev_found=rev_sev > 0, night=rows[-1]["night"]))
R, D = pd.DataFrame(rows), pd.DataFrame(dm_rows)

print(f"DECISION accuracy (no gold damage used): {(R.pred == R.gold).mean():.1%} ({(R.pred == R.gold).sum()}/{len(R)})"
      f"   reviewers: {(R.reviewer == R.gold).mean():.1%}")
print(pd.crosstab(R.gold, R.pred))

truth = D[(D.gold_sev > 0) & D.visible]
print(f"\nDAMAGE on visible damaged panels (n={len(truth)})")
for name, sub in [("all", truth), ("severity 1 (minor)", truth[truth.gold_sev == 1]),
                  ("severity 2", truth[truth.gold_sev == 2]), ("severity 3", truth[truth.gold_sev == 3])]:
    strict = ((sub.found) & (sub.f_type == sub.gold_type) & (sub.f_sev == sub.gold_sev)).mean()
    print(f"  {name:20s} n={len(sub):4d}  found {sub.found.mean():5.1%}  exact(type+severity) {strict:5.1%}"
          f"   reviewers found {sub.rev_found.mean():5.1%}")
for name, sub in truth.groupby("night"):
    print(f"  {'night' if name else 'day  '} found {sub.found.mean():.1%} (n={len(sub)}), reviewers {sub.rev_found.mean():.1%}")
fa = D[(D.gold_sev == 0) & D.found]
print(f"  false damage entries on panels with no gold damage: {len(fa)} of {int(D.found.sum())} entries")
print("\nmost common type/severity confusions among found panels:")
conf = truth[truth.found & ((truth.f_type != truth.gold_type) | (truth.f_sev != truth.gold_sev))]
print(conf.groupby(["gold_type", "gold_sev", "f_type", "f_sev"]).size().sort_values(ascending=False).head(12).to_string())
R.to_csv(os.path.dirname(os.path.abspath(__file__)) + "/run_text.csv", index=False)

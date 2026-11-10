"""
Scores the decision engine on the 420 gold cases.

Two runs, because the engine needs a damage list and we do not have the vision layer yet:
  A) "oracle damage"   - feed the TRUE damage (gold). Tests the RULES alone.
  B) "reviewer damage" - feed the damage the human reviewer recorded (often incomplete).
     Shows what happens when damage detection is imperfect, and what the vision layer must beat.
"""
import sys, os
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decision_engine import Findings, Damage, decide

# Data files are NOT in this repo. Put the two challenge workbooks in ../data/ (or set PS03_DATA).
DATA = os.environ.get("PS03_DATA", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")) + "/"
CASES = DATA + "PS-03_inspection_cases.xlsx"
EVAL = DATA + "PS-03_evaluation_set.xlsx"
read = lambda f, s: pd.read_excel(f, sheet_name=s, dtype=str, keep_default_na=False)  # keep "NONE" as text

cases, shots, panels = read(CASES, "cases"), read(CASES, "shot_log"), read(CASES, "panel_damage")
gold = read(EVAL, "gold_labels")
cases = cases.set_index("case_id")
shots_by = {k: v for k, v in shots.groupby("case_id")}
panels_by = {k: v for k, v in panels.groupby("case_id")}
num = lambda x: float(x) if str(x).strip() != "" else 0.0


def findings_for(case_id: str, source: str) -> Findings:
    c = cases.loc[case_id]
    sh = shots_by[case_id]
    missing = sh.loc[sh.captured != "True", "shot_code"].tolist()
    bad = [(r.shot_code, r.shot_quality) for r in sh.itertuples() if r.shot_quality not in ("OK", "NOT_CAPTURED")]
    pd_ = panels_by[case_id]
    damage = []
    for r in pd_.itertuples():
        if source == "gold":
            kind, sev = r.gold_damage_type, int(r.gold_severity)
        else:
            kind, sev = r.reviewer_recorded_damage, int(r.reviewer_recorded_severity or 0)
        if kind != "NONE" and sev > 0:
            damage.append(Damage(r.panel, kind, sev))
    return Findings(c.declared_reg_no, c.plate_ocr_text, c.chassis_last6_declared, c.chassis_last6_ocr,
                    num(c.lighting_score), num(c.blur_score), num(c.screen_moire_score),
                    num(c.capture_to_upload_hours), missing, bad, damage)


def run(source: str) -> pd.DataFrame:
    rows = []
    for g in gold.itertuples():
        d = decide(findings_for(g.case_id, source))
        hour = int(cases.loc[g.case_id].capture_local_time.split(":")[0])
        rows.append(dict(case_id=g.case_id, gold=g.gold_decision, pred=d.outcome, route=d.route,
                         fraud_gold=g.fraud_pattern, fraud_pred=d.fraud_pattern,
                         reviewer=g.original_reviewer_decision, night=(hour < 6 or hour >= 19),
                         reasons="; ".join(d.reasons)))
    return pd.DataFrame(rows)


def report(df: pd.DataFrame, title: str):
    print(f"\n===== {title} =====")
    print(f"decision accuracy: {(df.pred == df.gold).mean():.1%}  ({(df.pred == df.gold).sum()}/{len(df)})")
    print(f"human reviewers on the same 420: {(df.reviewer == df.gold).mean():.1%}")
    print("\nconfusion (rows = gold, cols = engine)")
    print(pd.crosstab(df.gold, df.pred))
    fr = df[df.fraud_gold.isin(["VEHICLE_MISMATCH", "OLD_VIDEO", "SCREEN_RECORDING", "DAMAGE_CONCEALED"])]
    print("\nfraud, per pattern (caught = engine flagged the same pattern, or RESHOOT for concealed)")
    for p, g in fr.groupby("fraud_gold"):
        ok = (g.pred == "RESHOOT") if p == "DAMAGE_CONCEALED" else (g.fraud_pred == p)
        print(f"  {p:18s} {ok.sum():3d}/{len(g):3d} = {ok.mean():.0%}   (reviewers: {(g.reviewer == g.gold).mean():.0%})")
    clean = df[df.fraud_gold == "NONE"]
    print(f"  false fraud flags on non-fraud cases: {(clean.route == 'FRAUD_DESK').sum()}/{len(clean)}")
    for name, g in df.groupby("night"):
        print(f"  {'night' if name else 'day  '} accuracy: {(g.pred == g.gold).mean():.1%} (n={len(g)})")


if __name__ == "__main__":
    a = run("gold"); report(a, "A) rules alone, true damage fed in")
    b = run("reviewer"); report(b, "B) reviewer-recorded damage fed in")
    a.to_csv(os.path.dirname(os.path.abspath(__file__)) + "/run_a.csv", index=False)
    b.to_csv(os.path.dirname(os.path.abspath(__file__)) + "/run_b.csv", index=False)
    print("\nmisses in A:")
    print(a[a.pred != a.gold][["case_id", "gold", "pred", "fraud_gold", "reasons"]].to_string(index=False))

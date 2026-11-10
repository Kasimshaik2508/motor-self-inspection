/*
  Reviewer.jsx - the REVIEWER console (SOP section 13).

  The AI decides most cases alone. A person handles what the SOP reserves for people: fraud suspicions,
  severe damage before the customer is told, plate/chassis disagreements, damage the AI was unsure about,
  and anything where the vision model was unavailable. The reviewer sees every photo with the AI's findings,
  then CONFIRMS the AI's decision or OVERRIDES it with a reason (overrides are logged, SOP 13).
  MVP limits: no login (anyone with the link can review) and the list is kept in server memory only.
*/
import { useEffect, useState } from "react";
import { get, post } from "./api";

const pretty = (s) => String(s ?? "-").replace(/_45/, " corner").replace(/_/g, " ").toLowerCase();
const time = (t) => new Date(t * 1000).toLocaleString();
const OUTCOMES = ["APPROVE", "APPROVE_WITH_EXCLUSIONS", "RESHOOT", "REJECT"];

export default function Reviewer() {
  const [list, setList] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try { setList(await get("/api/review/inspections")); } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, []);

  if (openId) return <Detail id={openId} onBack={() => { setOpenId(null); load(); }} />;

  return (
    <section className="card">
      <div className="row spaced"><h2>Reviewer console</h2><button className="ghost" onClick={load}>Refresh</button></div>
      <p className="muted small">Inspections are kept in server memory: the free server forgets them when it restarts or sleeps.</p>
      {error && <p className="bad-text">{error}</p>}
      {list && !list.length && <p className="muted">No inspections yet. Do one in "Inspect my car" first.</p>}
      {list && list.length > 0 && (
        <table>
          <thead><tr><th>ID</th><th>When</th><th>Plate</th><th>Status</th><th>AI decision</th><th>Why a person</th><th>Final</th></tr></thead>
          <tbody>{list.map((r) => (
            <tr key={r.id} className="clickable" onClick={() => setOpenId(r.id)}>
              <td><code>{r.id}</code></td><td>{time(r.created_at)}</td><td>{r.plate}</td>
              <td><span className={"pill " + r.status}>{pretty(r.status)}</span></td>
              <td>{r.ai_outcome ? <span className={"badge sm " + r.ai_outcome}>{pretty(r.ai_outcome)}</span> : "-"}</td>
              <td>{r.hold_reasons.map(pretty).join(", ") || "-"}</td>
              <td>{r.final_outcome ? pretty(r.final_outcome) : "-"}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </section>
  );
}

function Detail({ id, onBack }) {
  const [r, setR] = useState(null);
  const [error, setError] = useState("");
  const [action, setAction] = useState("CONFIRM");
  const [outcome, setOutcome] = useState("APPROVE");
  const [reason, setReason] = useState("");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    try { const x = await get("/api/review/inspections/" + id); setR(x); if (!x.decision) setAction("OVERRIDE"); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [id]);

  async function submit() {
    setSaving(true); setError("");
    try {
      await post("/api/review/inspections/" + id, { action, final_outcome: action === "OVERRIDE" ? outcome : null, reason, reviewer: name });
      await load();
    } catch (e) { setError(e.message); } finally { setSaving(false); }
  }

  if (!r) return <section className="card">{error ? <p className="bad-text">{error}</p> : "Loading…"}</section>;
  const d = r.decision;
  const byShot = Object.fromEntries((r.per_shot || []).map((s) => [s.shot, s]));
  const phone = Object.fromEntries((r.phone_checks || []).map((s) => [s.shot, s]));

  return (
    <>
      <section className="card">
        <div className="row spaced"><button className="link" onClick={onBack}>← All inspections</button><code>{r.id}</code></div>
        <h2>AI decision</h2>
        {d ? (
          <>
            <div className="row"><span className={"badge " + d.outcome}>{pretty(d.outcome)}</span>
              {d.route !== "NONE" && <span className="muted">route: {pretty(d.route)}</span>}</div>
            <div><b>Reasons:</b> {d.reasons.map((x) => <span className="tag" key={x}>{x}</span>)}</div>
          </>
        ) : <p className="warn-text">No AI decision: {r.vision_error}</p>}
        {r.hold_reasons?.length > 0 && <p><b>Why a person is needed:</b> {r.hold_reasons.map(pretty).join(", ")}</p>}
        <p className="muted small">Model: {r.model || "none"} · attempt {r.attempt} · declared plate {r.declared.plate}, chassis {r.declared.chassis_last6}
          {r.identity && <> · plate {pretty(r.identity.plate)}, chassis {pretty(r.identity.chassis)}</>}
          {r.vehicle?.make && <> · seen: {r.vehicle.colour} {r.vehicle.make} {r.vehicle.model}</>}</p>
        <h2 className="sub">Message the customer sees</h2>
        <div className="msg">{r.customer_message}</div>
      </section>

      <section className="card">
        <h2>Photos and what the AI saw</h2>
        <div className="shotgrid">
          {Object.entries(r.photos).map(([code, b64]) => {
            const s = byShot[code];
            return (
              <figure key={code} className="shot">
                <img src={"data:image/jpeg;base64," + b64} alt={pretty(code)} />
                <figcaption>
                  <b>{pretty(code)}</b>
                  {s && <div className="small">quality {pretty(s.quality)}{!s.shows_expected_shot && " · WRONG ANGLE"}{s.screen_photo && " · LOOKS LIKE A SCREEN"}
                    {s.plate_text && <> · plate “{s.plate_text}”</>}{s.chassis_last6 && <> · chassis “{s.chassis_last6}”</>}</div>}
                  {phone[code] && <div className="small muted">phone: brightness {phone[code].brightness}, sharpness {phone[code].sharpness}</div>}
                  {s?.damage.map((x, i) => (
                    <div key={i} className={"small " + (x.confidence < 0.6 ? "warn-text" : "")}>
                      {pretty(x.panel)}: {pretty(x.kind)}, severity {x.severity}, confidence {x.confidence} — {x.description}
                    </div>
                  ))}
                </figcaption>
              </figure>
            );
          })}
        </div>
      </section>

      <section className="card">
        <h2>Your decision</h2>
        {r.review && (
          <p className="ok-text">{r.review.action === "CONFIRM" ? "Confirmed" : "Overridden"} by {r.review.reviewer}: {pretty(r.review.final_outcome)}
            {r.review.reason && <> — “{r.review.reason}”</>}</p>
        )}
        <div className="form">
          <label>Your name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="reviewer" /></label>
          <div className="row">
            <label className="check"><input type="radio" checked={action === "CONFIRM"} disabled={!d} onChange={() => setAction("CONFIRM")} /> Confirm the AI ({d ? pretty(d.outcome) : "none"})</label>
            <label className="check"><input type="radio" checked={action === "OVERRIDE"} onChange={() => setAction("OVERRIDE")} /> Override</label>
          </div>
          {action === "OVERRIDE" && (
            <label>Final outcome<select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
              {OUTCOMES.map((o) => <option key={o} value={o}>{pretty(o)}</option>)}</select></label>
          )}
          <label>Reason {action === "OVERRIDE" ? "(required)" : "(optional)"}<textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        </div>
        {error && <p className="bad-text">{error}</p>}
        <button onClick={submit} disabled={saving || (action === "OVERRIDE" && !reason.trim())}>{saving ? "Saving…" : "Save decision"}</button>
      </section>
    </>
  );
}

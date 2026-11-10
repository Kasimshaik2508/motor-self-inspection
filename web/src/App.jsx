/*
  App.jsx - the screens. No decision logic lives here: the browser only shows what the engine returned,
  so the app can never disagree with the engine.

  Flow:
  1. On start, ask /api/health. Free hosting sleeps when idle, so if it takes more than 3 s we say
     "waking up the server" instead of looking broken. If the data is missing we show why, and stop.
  2. Load the case list into the pickers.
  3. "Inspect" -> /api/cases/<id>, shown in <CaseResult>.
  4. "Run evaluation" -> /api/evaluate, shown in <Evaluation>.
  Note: React escapes any text it puts on screen, so case text cannot inject HTML (the old page had to do this by hand).
*/
import { useEffect, useState } from "react";
import { get } from "./api";

const pretty = (s) => String(s).replace(/_/g, " ").toLowerCase();

export default function App() {
  const [status, setStatus] = useState("connecting"); // connecting | waking | ready | nodata | offline
  const [message, setMessage] = useState("");
  const [cases, setCases] = useState([]);

  useEffect(() => {
    const slow = setTimeout(() => setStatus((s) => (s === "connecting" ? "waking" : s)), 3000);
    (async () => {
      try {
        const h = await get("/api/health");
        if (!h.data_loaded) { setMessage(h.data_message); setStatus("nodata"); return; }
        setCases(await get("/api/cases"));
        setStatus("ready");
      } catch (e) {
        setMessage(e.message); setStatus("offline");
      } finally {
        clearTimeout(slow);
      }
    })();
    return () => clearTimeout(slow);
  }, []);

  return (
    <>
      <header>
        <h1>Motor Self-Inspection AI</h1>
        <p>PolicyNest · PS-03 · synthetic data. Pick a case: the system reads the evidence, applies the SOP rules and explains its decision.</p>
      </header>
      <main>
        <StatusBanner status={status} message={message} />
        {status === "ready" && <Inspector cases={cases} />}
        {status === "ready" && <Evaluation />}
      </main>
    </>
  );
}

function StatusBanner({ status, message }) {
  if (status === "connecting") return <section className="card muted">Connecting to the server…</section>;
  if (status === "waking")
    return <section className="card warn">Waking up the server. The free host sleeps when nobody has used it for a while; this takes up to a minute.</section>;
  if (status === "nodata")
    return (
      <section className="card bad">
        <h2>Data not loaded</h2>
        <p>{message}</p>
        <p className="muted">The site is running, but it has no cases to show yet.</p>
      </section>
    );
  if (status === "offline")
    return (
      <section className="card bad">
        <h2>Could not reach the server</h2>
        <p>{message}</p>
        {/* The page checks the server only once when it opens, so give people an obvious way to check again. */}
        <button onClick={() => window.location.reload()}>Try again</button>
      </section>
    );
  return null;
}

function Inspector({ cases }) {
  const [filter, setFilter] = useState("");
  const list = cases.filter((c) => !filter || c.gold_decision === filter);
  const [picked, setPicked] = useState(cases[0]?.case_id || "");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const kinds = [...new Set(cases.map((c) => c.gold_decision))].sort();

  function changeFilter(f) {
    setFilter(f);
    const first = cases.find((c) => !f || c.gold_decision === f);
    setPicked(first?.case_id || "");
  }

  async function inspect() {
    if (!picked) return;
    setBusy(true); setError("");
    try { setResult(await get("/api/cases/" + picked)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  return (
    <>
      <section className="card">
        <h2>1 · Choose a case</h2>
        <div className="row">
          <select aria-label="Filter by expected decision" value={filter} onChange={(e) => changeFilter(e.target.value)}>
            <option value="">All {cases.length} cases</option>
            {kinds.map((k) => <option key={k} value={k}>Expected: {pretty(k)}</option>)}
          </select>
          <select aria-label="Case" value={picked} onChange={(e) => setPicked(e.target.value)}>
            {list.map((c) => <option key={c.case_id} value={c.case_id}>{c.case_id}</option>)}
          </select>
          <button onClick={inspect} disabled={busy || !picked}>{busy ? "Inspecting…" : "Inspect"}</button>
        </div>
        {error && <p className="bad-text">{error}</p>}
      </section>
      {result && <CaseResult r={result} />}
    </>
  );
}

function CaseResult({ r }) {
  const e = r.evidence;
  const route =
    r.route === "FRAUD_DESK" ? "Routed to the fraud desk. The customer is only told a surveyor will contact them."
    : r.route === "REVIEWER_CONFIRM" ? "A human reviewer confirms this before the customer is told." : "";
  const kv = [
    ["Plate declared", e.plate_declared], ["Plate read", e.plate_read || "(unreadable)"],
    ["Chassis declared", e.chassis_declared], ["Chassis read", e.chassis_read || "(unreadable)"],
    ["Lighting", e.lighting], ["Blur", e.blur], ["Screen-recording score", e.moire],
    ["Hours since filmed", e.hours_since_capture], ["Missing shots", e.missing_shots.length ? e.missing_shots.join(", ") : "none"],
  ];
  return (
    <section className="card">
      <h2>2 · Decision for {r.case_id}</h2>
      <div className="row">
        <span className={"badge " + r.decision}>{pretty(r.decision)}</span>
        <span className="muted">
          {r.correct ? "matches the expert answer" : `differs from the expert answer (${pretty(r.gold_decision)})`}
        </span>
      </div>
      {route && <p className="muted">{route}</p>}
      <div><b>Why:</b> {r.reasons.map((x) => <span className="tag" key={x}>{x}</span>)}</div>

      <h2 className="sub">Message to the customer</h2>
      <div className="msg">{r.customer_message}</div>

      <h2 className="sub">Damage register</h2>
      {r.damage_register.length ? (
        <table>
          <thead><tr><th>Panel</th><th>Type</th><th>Severity</th><th>Seen in shot</th><th>At second</th></tr></thead>
          <tbody>
            {r.damage_register.map((d, i) => (
              <tr key={i}>
                <td>{pretty(d.panel)}</td><td>{pretty(d.kind)}</td><td>{d.severity}</td>
                <td>{d.shot ? pretty(d.shot) : "-"}</td><td>{d.second ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <span className="muted">No damage found.</span>}

      <h2 className="sub">Evidence used</h2>
      <div className="grid">{kv.map(([k, v]) => <div className="kv" key={k}><b>{k}</b>{String(v)}</div>)}</div>

      <h2 className="sub">What the camera saw (per shot)</h2>
      {r.frames.map((f, i) => <div className="frame" key={i}><code>{f.shot}</code> {f.description}</div>)}
    </section>
  );
}

function Evaluation() {
  const [e, setE] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setBusy(true); setError("");
    try { setE(await get("/api/evaluate")); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <section className="card">
      <h2>3 · Accuracy on all 420 gold cases</h2>
      <div className="row">
        <button className="ghost" onClick={run} disabled={busy}>{busy ? "Running 420 cases…" : "Run evaluation"}</button>
        {e && (
          <span className="muted">
            {e.correct} of {e.total} correct ({(e.accuracy * 100).toFixed(1)}%). Human reviewers on the same cases: {(e.reviewer_accuracy * 100).toFixed(1)}%.
          </span>
        )}
      </div>
      {error && <p className="bad-text">{error}</p>}
      {e && (
        <>
          <table>
            <thead><tr><th>Expert decision</th><th>Correct</th><th>Total</th></tr></thead>
            <tbody>
              {Object.entries(e.per_decision).map(([k, v]) => (
                <tr key={k}><td>{pretty(k)}</td><td>{v.correct}</td><td>{v.total}</td></tr>
              ))}
            </tbody>
          </table>
          {e.misses.length > 0 && <p className="muted">Cases it got wrong: {e.misses.join(", ")}</p>}
          <p className="muted">Tested on written frame descriptions, not real video.</p>
        </>
      )}
    </section>
  );
}

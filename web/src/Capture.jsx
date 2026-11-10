/*
  Capture.jsx - the CUSTOMER app: photograph the car, check each photo on the phone, send, get a decision.

  Steps:  details -> 12 guided shots -> review -> sending -> result (-> retake once, if asked)
  The camera: <input type="file" accept="image/*" capture="environment"> opens the phone's rear camera
  (on a laptop it opens a file picker, which is handy for testing with saved photos). The same code runs
  inside the Android app later (Capacitor), so no separate camera code is needed for the MVP.
*/
import { useEffect, useState } from "react";
import { get, post } from "./api";
import { processPhoto } from "./photo";

const pretty = (s) => String(s).replace(/_45/, " corner").replace(/_/g, " ").toLowerCase();

export default function Capture() {
  const [shots, setShots] = useState([]);
  const [step, setStep] = useState("details");
  const [plate, setPlate] = useState("");
  const [chassis, setChassis] = useState("");
  const [consent, setConsent] = useState(false);
  const [photos, setPhotos] = useState({});        // shot code -> processed photo
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [retakeOf, setRetakeOf] = useState(null);
  const [highlight, setHighlight] = useState([]);  // shots the server asked to retake

  useEffect(() => { get("/api/shots").then(setShots).catch((e) => setError(e.message)); }, []);

  const shot = shots[idx];
  const photo = shot && photos[shot.code];

  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";                              // lets the customer pick the same file again after a retake
    if (!file) return;
    setBusy(true); setError("");
    try {
      const ph = await processPhoto(file);
      setPhotos((p) => ({ ...p, [shot.code]: ph }));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  function next() { if (idx < shots.length - 1) setIdx(idx + 1); else setStep("review"); }

  async function send() {
    setStep("sending"); setError("");
    try {
      const body = {
        declared_plate: plate, declared_chassis_last6: chassis, retake_of: retakeOf,
        shots: shots.filter((s) => photos[s.code]).map((s) => ({
          shot: s.code, image_b64: photos[s.code].b64, brightness: photos[s.code].brightness,
          sharpness: photos[s.code].sharpness, captured_at_ms: photos[s.code].capturedAt,
        })),
      };
      setResult(await post("/api/inspections", body));
      setStep("result");
    } catch (e) { setError(e.message); setStep("review"); }
  }

  async function refresh() {
    setBusy(true);
    try { setResult(await get("/api/inspections/" + result.id)); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  function startRetake() {
    setRetakeOf(result.id);
    setHighlight(result.retake_shots);
    setPhotos((p) => { const q = { ...p }; result.retake_shots.forEach((c) => delete q[c]); return q; });
    const first = shots.findIndex((s) => result.retake_shots.includes(s.code));
    setIdx(first >= 0 ? first : 0);
    setResult(null); setStep("shots");
  }

  function restart() {
    setStep("details"); setPhotos({}); setIdx(0); setResult(null); setRetakeOf(null); setHighlight([]); setError("");
  }

  if (step === "details") return (
    <section className="card">
      <h2>Inspect my car</h2>
      <p>You will take {shots.length || 12} photos around your car. Each photo is checked on your phone first, then our AI looks for
        damage and decides. Stand about 1.5 to 2 metres away, in daylight.</p>
      <div className="form">
        <label>Registration number<input value={plate} onChange={(e) => setPlate(e.target.value.toUpperCase())} placeholder="e.g. KA 01 AB 1234" /></label>
        <label>Last 6 characters of the chassis number<input value={chassis} maxLength={6} onChange={(e) => setChassis(e.target.value.toUpperCase())} placeholder="from your RC" /></label>
        <label className="check"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          This is my car, or I have the owner's permission to photograph it.</label>
      </div>
      <p className="muted small">Demo: photos are sent to an AI model for analysis. Use only test photos, not real customers.</p>
      {error && <p className="bad-text">{error}</p>}
      <button disabled={!plate.trim() || chassis.trim().length < 6 || !consent || !shots.length} onClick={() => setStep("shots")}>Start</button>
    </section>
  );

  if (step === "shots" && shot) return (
    <section className="card">
      <h2>Photo {idx + 1} of {shots.length}{retakeOf ? " · retake" : ""}</h2>
      <Strip shots={shots} photos={photos} idx={idx} highlight={highlight} onPick={setIdx} />
      <h3>{pretty(shot.code)}</h3>
      <p>{shot.what}.</p>
      {highlight.includes(shot.code) && <p className="warn-text">We need this photo again.</p>}
      {photo ? (
        <>
          <img className="preview" src={photo.dataUrl} alt={pretty(shot.code)} />
          {photo.warnings.map((w) => <p className="warn-text" key={w}>{w}</p>)}
          <div className="row">
            <label className="button ghost">Retake<input type="file" accept="image/*" capture="environment" hidden onChange={onFile} /></label>
            <button onClick={next}>{photo.warnings.length ? "Use anyway" : "Use this photo"}</button>
          </div>
        </>
      ) : (
        <div className="row">
          <label className={"button" + (busy ? " disabled" : "")}>{busy ? "Checking photo…" : "Take photo"}
            <input type="file" accept="image/*" capture="environment" hidden onChange={onFile} disabled={busy} /></label>
          <button className="ghost" onClick={next}>Skip this shot</button>
        </div>
      )}
      {error && <p className="bad-text">{error}</p>}
      <div className="row spaced">
        <button className="link" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>← Back</button>
        <button className="link" onClick={() => setStep("review")}>Review all →</button>
      </div>
    </section>
  );

  if (step === "review") {
    const missing = shots.filter((s) => !photos[s.code]);
    return (
      <section className="card">
        <h2>Check your photos</h2>
        <div className="thumbs">
          {shots.map((s, i) => (
            <button key={s.code} className="thumb" onClick={() => { setIdx(i); setStep("shots"); }}>
              {photos[s.code] ? <img src={photos[s.code].dataUrl} alt="" /> : <span className="empty">missing</span>}
              <span>{pretty(s.code)}{photos[s.code]?.warnings.length ? " ⚠" : ""}</span>
            </button>
          ))}
        </div>
        {missing.length > 0 && <p className="warn-text">{missing.length} photo(s) missing. Missing photos will mean a retake request.</p>}
        {error && <p className="bad-text">{error}</p>}
        <button onClick={send} disabled={missing.length === shots.length}>Send for inspection</button>
      </section>
    );
  }

  if (step === "sending") return (
    <section className="card"><h2>Checking your car…</h2><p>Our AI is looking at your photos. This can take up to a minute.</p></section>
  );

  if (step === "result" && result) return (
    <section className="card">
      <h2>Result</h2>
      {result.outcome && <span className={"badge " + result.outcome}>{pretty(result.outcome)}</span>}
      {!result.outcome && <span className="badge PENDING">being reviewed</span>}
      <div className="msg">{result.message}</div>
      {result.damage_register.length > 0 && (
        <>
          <h2 className="sub">Existing damage we recorded</h2>
          <table><thead><tr><th>Panel</th><th>Type</th><th>Severity</th><th>Photo</th></tr></thead>
            <tbody>{result.damage_register.map((d, i) => (
              <tr key={i}><td>{pretty(d.panel)}</td><td>{pretty(d.kind)}</td><td>{d.severity}</td><td>{d.shot ? pretty(d.shot) : "-"}</td></tr>
            ))}</tbody></table>
        </>
      )}
      <p className="muted small">Inspection ID: {result.id} · attempt {result.attempt}</p>
      {error && <p className="bad-text">{error}</p>}
      <div className="row">
        {result.can_retake && <button onClick={startRetake}>Retake the photos we asked for</button>}
        {result.status === "NEEDS_REVIEW" && <button className="ghost" onClick={refresh} disabled={busy}>Check for an update</button>}
        <button className="ghost" onClick={restart}>New inspection</button>
      </div>
    </section>
  );

  return <section className="card muted">Loading…</section>;
}

function Strip({ shots, photos, idx, highlight, onPick }) {
  return (
    <div className="strip" aria-label="Progress">
      {shots.map((s, i) => (
        <button key={s.code} title={pretty(s.code)} onClick={() => onPick(i)}
          className={"dot" + (photos[s.code] ? " done" : "") + (i === idx ? " current" : "") + (highlight.includes(s.code) ? " redo" : "")} />
      ))}
    </div>
  );
}

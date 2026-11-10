/*
  Capture.jsx - the CUSTOMER app: photograph the car, check each photo on the phone, send, get a decision.

  Steps:  details -> 12 guided shots -> review -> sending -> result (-> retake once, if asked)
  Each shot: live camera (Camera.jsx) with on-phone car detection and auto-capture; then, still on the phone:
  brightness/blur check, "is there a car in this photo?", and OCR of the plate (front/rear) or chassis number.
  If the live camera is unavailable (laptop, permission refused) the customer can pick or take a photo file instead.
  Everything here is free and runs on the phone: no API key, no paid AI calls.
*/
import { useCallback, useEffect, useState } from "react";
import { get, post } from "./api";
import { processPhoto } from "./photo";
import Camera from "./Camera";
import { compareIds, detectCar, readChassis, readPlate } from "./detect";

// shots of the outside of the car (a car should be visible); the rest are close-ups
const CAR_SHOTS = ["FRONT", "FRONT_LEFT_45", "LEFT_SIDE", "REAR_LEFT_45", "REAR", "REAR_RIGHT_45", "RIGHT_SIDE", "FRONT_RIGHT_45", "ROOF_AND_GLASS"];
const ID_LABEL = { MATCH: "matches what you entered ✓", ONE_CHAR_SLIP: "one character differs (probably a reading slip)", DIFFERENT: "does NOT match what you entered", UNREADABLE: "could not be read" };

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
  const [camFailed, setCamFailed] = useState(false);
  const [analysing, setAnalysing] = useState("");
  const onNoCamera = useCallback(() => setCamFailed(true), []);

  useEffect(() => { get("/api/shots").then(setShots).catch((e) => setError(e.message)); }, []);

  const shot = shots[idx];
  const photo = shot && photos[shot.code];

  /** On-phone analysis after a photo is taken: car present? plate / chassis text? */
  async function analyse(code, ph) {
    const out = { ...ph };
    const warnings = [...ph.warnings];
    try {
      if (CAR_SHOTS.includes(code)) {
        setAnalysing("Checking for the car…");
        if (!out.car || !out.car.found) out.car = await detectCar(out.canvas);
        if (!out.car.found) warnings.push("We could not see a car in this photo. Point the camera at the whole car.");
      }
      if (code === "FRONT" || code === "REAR") {
        setAnalysing("Reading the number plate…");
        out.plate = await readPlate(out.canvas, out.car?.box);
        out.plateCheck = compareIds(plate, out.plate.text);
        if (out.plateCheck === "UNREADABLE") warnings.push("We could not read the number plate. Retake a little closer.");
      }
      if (code === "CHASSIS_NUMBER") {
        setAnalysing("Reading the chassis number…");
        out.chassisRead = await readChassis(out.canvas);
        out.chassisCheck = compareIds(chassis, out.chassisRead.last6);
        if (out.chassisCheck === "UNREADABLE") warnings.push("We could not read the chassis number. Get closer, keep it sharp.");
      }
    } catch {
      warnings.push("The on-phone checker could not run on this photo (it may still be downloading). You can use the photo anyway.");
    }
    out.warnings = warnings;
    setAnalysing("");
    return out;
  }

  async function accept(code, ph) {
    setBusy(true); setError("");
    try { const done = await analyse(code, ph); setPhotos((p) => ({ ...p, [code]: done })); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";                              // lets the customer pick the same file again after a retake
    if (!file) return;
    try { await accept(shot.code, { ...(await processPhoto(file)), via: "file" }); } catch (err) { setError(err.message); }
  }

  function retakeCurrent() { setPhotos((p) => { const q = { ...p }; delete q[shot.code]; return q; }); }

  function next() { if (idx < shots.length - 1) setIdx(idx + 1); else setStep("review"); }

  async function send() {
    setStep("sending"); setError("");
    try {
      const body = {
        declared_plate: plate, declared_chassis_last6: chassis, retake_of: retakeOf,
        shots: shots.filter((s) => photos[s.code]).map((s) => ({
          shot: s.code, image_b64: photos[s.code].b64, brightness: photos[s.code].brightness,
          sharpness: photos[s.code].sharpness, captured_at_ms: photos[s.code].capturedAt,
          car_detected: CAR_SHOTS.includes(s.code) ? !!photos[s.code].car?.found : null,
          plate_read: photos[s.code].plate?.text || "", chassis_read: photos[s.code].chassisRead?.last6 || "",
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
      <p>You will take {shots.length || 12} photos around your car with your phone camera. The app finds the car and captures
        each photo for you, checks it is clear, and reads the number plate and chassis number. Stand about 1.5 to 2 metres away, in daylight.</p>
      <div className="form">
        <label>Registration number<input value={plate} onChange={(e) => setPlate(e.target.value.toUpperCase())} placeholder="e.g. KA 01 AB 1234" /></label>
        <label>Last 6 characters of the chassis number<input value={chassis} maxLength={6} onChange={(e) => setChassis(e.target.value.toUpperCase())} placeholder="from your RC" /></label>
        <label className="check"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          This is my car, or I have the owner's permission to photograph it.</label>
      </div>
      <p className="muted small">Car detection and text reading run on your phone. Photos are sent to our server for the decision. Demo: use test photos of cars you may photograph.</p>
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
          <ul className="checks">
            {CAR_SHOTS.includes(shot.code) && <li className={photo.car?.found ? "ok-text" : "warn-text"}>
              {photo.car?.found ? `Car detected ✓ (${Math.round(photo.car.score * 100)}% sure)` : "No car detected"}</li>}
            {photo.plate && <li className={photo.plateCheck === "MATCH" ? "ok-text" : "warn-text"}>
              Plate read: <b>{photo.plate.text || "-"}</b>, {ID_LABEL[photo.plateCheck]}</li>}
            {photo.chassisRead && <li className={photo.chassisCheck === "MATCH" ? "ok-text" : "warn-text"}>
              Chassis last 6 read: <b>{photo.chassisRead.last6 || "-"}</b>, {ID_LABEL[photo.chassisCheck]}</li>}
          </ul>
          {photo.warnings.map((w) => <p className="warn-text" key={w}>{w}</p>)}
          <div className="row">
            <button className="ghost" onClick={retakeCurrent}>Retake</button>
            <button onClick={next}>{photo.warnings.length ? "Use anyway" : "Use this photo"}</button>
          </div>
        </>
      ) : busy ? (
        <p className="muted">{analysing || "Checking photo…"}</p>
      ) : (
        <>
          {!camFailed && <Camera key={shot.code} shot={shot.code} needsCar={CAR_SHOTS.includes(shot.code)}
            onCapture={(ph) => accept(shot.code, ph)} onNoCamera={onNoCamera} />}
          {camFailed && <p className="muted small">The live camera is not available here, so take or choose a photo instead.</p>}
          <div className="row">
            <label className={"button" + (camFailed ? "" : " ghost")}>{camFailed ? "Take or choose photo" : "Upload a photo instead"}
              <input type="file" accept="image/*" capture="environment" hidden onChange={onFile} /></label>
            <button className="ghost" onClick={next}>Skip this shot</button>
          </div>
        </>
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

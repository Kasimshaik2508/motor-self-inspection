/*
  Capture.jsx - the CUSTOMER app: photograph the car, check each photo on the phone, send, get a decision.

  Steps:  car number -> checklist -> guided shots -> review -> sending -> result (-> retake once, if asked)
  The customer enters only the CAR NUMBER. The chassis number comes from the car's RC record (in real life the
  government VAHAN lookup; here engine/vehicles.py, synthetic demo data), so a cheater cannot type numbers that
  match their photos.
  Shot order (from /api/shots): RC card and odometer from the driver's seat, chassis and engine with the bonnet open,
  then the walk-around, then up to 3 optional damage close-ups. Only the SOP's 12 shots decide; RC + close-ups are
  for the reviewer. Anti-cheat: a photo FILE older than the start of this inspection is refused on the phone, and the
  server sends file photos and photos spread over more than 30 minutes to a reviewer.
  Demo helper: "Fill with demo photos" loads the 13 sample photos (12 SOP shots + an RC card; web/public/demo-photos) and runs the same checks.
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
const ID_LABEL = { MATCH: "matches the RC record ✓", ONE_CHAR_SLIP: "one character differs (probably a reading slip)", DIFFERENT: "does NOT match the RC record", UNREADABLE: "could not be read", SENT: "we will check it against the RC record" };

const CHECKLIST = [
  ["rc", "I have the car's RC card with me."],
  ["chassis", "I know where the chassis number is on the car."],
  ["place", "The car is in daylight in an open place: not under a tree, not inside a garage, workshop, basement or parking lot, and not at a petrol pump."],
  ["clean", "The windscreen and windows are clean."],
  ["ready", "The bonnet is open, all windows are rolled up, and I am in the driver's seat."],
];

const pretty = (s) => String(s).replace(/_45/, " corner").replace(/_/g, " ").toLowerCase().replace(/^rc /, "RC ");

export default function Capture() {
  const [shots, setShots] = useState([]);
  const [step, setStep] = useState("details");
  const [carNo, setCarNo] = useState("");
  const [car, setCar] = useState(null);             // the car on the RC record: model, colour, plate (never the chassis)
  const [demoCars, setDemoCars] = useState([]);
  const [wrongChassis, setWrongChassis] = useState(false);
  const [consent, setConsent] = useState(false);
  const [ticks, setTicks] = useState({});           // the pre-inspection checklist
  const [sessionStart, setSessionStart] = useState(0);
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

  useEffect(() => {
    get("/api/shots").then(setShots).catch((e) => setError(e.message));
    get("/api/vehicles").then(setDemoCars).catch(() => {});
  }, []);
  const plate = car?.plate || "";

  async function findCar(no) {
    setBusy(true); setError(""); setCar(null);
    try { const c = await get("/api/vehicles/" + encodeURIComponent(no.trim())); setCar(c); setCarNo(c.plate); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  /** Demo helper: loads the 13 sample photos and runs exactly the same on-phone checks as a real photo. */
  async function fillDemo() {
    setBusy(true); setError("");
    try {
      const done = {};
      const needed = shots.filter((s) => s.required);
      for (const [i, s] of needed.entries()) {
        setAnalysing(`Demo photo ${i + 1} of ${needed.length}: ${pretty(s.code)}…`);
        const name = s.code === "CHASSIS_NUMBER" && wrongChassis ? "CHASSIS_NUMBER_wrong_car" : s.code;
        const res = await fetch(`${import.meta.env.BASE_URL}demo-photos/${name}.jpg`);
        if (!res.ok) throw new Error(`Demo photo ${name} could not be loaded.`);
        done[s.code] = await analyse(s.code, { ...(await processPhoto(await res.blob())), via: "demo" });
        setPhotos((p) => ({ ...p, [s.code]: done[s.code] }));
      }
      setStep("review");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); setAnalysing(""); }
  }

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
        // the phone does not know the chassis number on file (kept on the server); the server compares it
        out.chassisCheck = out.chassisRead.last6 ? "SENT" : "UNREADABLE";
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
    // A photo file made before this inspection started is an OLD photo (e.g. from the gallery): refuse it.
    // (A photo taken just now with the phone camera has a fresh time. File times can be edited, so this stops
    // casual reuse, not a determined cheater: the server also sends every file photo to a reviewer.)
    if (file.lastModified && sessionStart && file.lastModified < sessionStart - 2 * 60_000) {
      setError("This photo was taken before you started the inspection. Please take a new photo now.");
      return;
    }
    try { await accept(shot.code, { ...(await processPhoto(file)), via: "file" }); } catch (err) { setError(err.message); }
  }

  function retakeCurrent() { setPhotos((p) => { const q = { ...p }; delete q[shot.code]; return q; }); }

  function next() { if (idx < shots.length - 1) setIdx(idx + 1); else setStep("review"); }

  async function send() {
    setStep("sending"); setError("");
    try {
      const body = {
        car_no: carNo, retake_of: retakeOf,
        shots: shots.filter((s) => photos[s.code]).map((s) => ({
          shot: s.code, image_b64: photos[s.code].b64, brightness: photos[s.code].brightness,
          sharpness: photos[s.code].sharpness, captured_at_ms: photos[s.code].capturedAt, via: photos[s.code].via || null,
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
    setStep("details"); setTicks({}); setPhotos({}); setIdx(0); setCar(null); setCarNo(""); setResult(null); setRetakeOf(null); setHighlight([]); setError("");
  }

  if (step === "details") return (
    <section className="card">
      <h2>Inspect my car</h2>
      <p>Enter your car number. We will show the car from its registration (RC) record, then guide you through the photos:
        your RC card and odometer from the driver's seat, the chassis number and engine, then a walk around the car.
        The app finds the car, checks each photo is clear, and reads the number plate and chassis number.</p>
      <form className="form" onSubmit={(e) => { e.preventDefault(); findCar(carNo); }}>
        <label>Car number<input value={carNo} onChange={(e) => { setCarNo(e.target.value.toUpperCase()); setCar(null); }} placeholder="e.g. KA 01 AB 1234" /></label>
        <button type="submit" className="ghost" disabled={!carNo.trim() || busy}>Find my car</button>
      </form>
      {demoCars.length > 0 && !car && (
        <div className="muted small chips">Demo cars (synthetic): {demoCars.map((d) => (
          <button key={d.car_no} className="link" title={d.note} onClick={() => findCar(d.car_no)}>{d.plate}</button>
        ))}</div>
      )}
      {car && (
        <div className="policy">
          <b>{car.make_model}</b> · {car.colour}<br />
          Registration <b>{car.plate}</b> · owner {car.owner}<br />
          <span className="muted small">Please photograph this car. We check the plate and chassis number in your photos against the RC record.</span>
        </div>
      )}
      {car && (
        <label className="check"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          This is my car, or I have the owner's permission to photograph it.</label>
      )}
      {error && <p className="bad-text">{error}</p>}
      <div className="row">
        <button disabled={!car || !consent || !shots.length || busy} onClick={() => setStep("prep")}>Next: get ready</button>
      </div>
      {car && (
        <div className="demo-box">
          <b>No car with you? Try the demo photos.</b>
          <p className="muted small">13 sample photos (a synthetic RC card + 12 photos of a blue Tata Nexon) with the synthetic plate KA 01 AB 1234 (matches demo car KA 01 AB 1234).
            They go through exactly the same checks. <a href={`${import.meta.env.BASE_URL}demo-photos/CREDITS.md`} target="_blank" rel="noreferrer">Photo credits</a></p>
          <label className="check small"><input type="checkbox" checked={wrongChassis} onChange={(e) => setWrongChassis(e.target.checked)} />
            Use a chassis label from a different car (fraud demo)</label>
          <button className="ghost" disabled={!consent || !shots.length || busy} onClick={fillDemo}>{busy && analysing ? analysing : "Fill with demo photos"}</button>
        </div>
      )}
    </section>
  );

  if (step === "prep") {
    const allTicked = CHECKLIST.every(([k]) => ticks[k]);
    return (
      <section className="card">
        <h2>Before you start</h2>
        <p>Tick each one when it is done. This avoids most retakes.</p>
        {CHECKLIST.map(([k, text]) => (
          <label className="check" key={k}><input type="checkbox" checked={!!ticks[k]}
            onChange={(e) => setTicks((t) => ({ ...t, [k]: e.target.checked }))} /> {text}</label>
        ))}
        <details className="small">
          <summary>Where is the chassis number?</summary>
          <p className="muted">It is a 17-character number <b>engraved in the metal</b> of the car. Most cars: under the bonnet,
            on the body near the windscreen. Some cars: on a metal plate at the driver or passenger door pillar. It is also
            printed on your RC. Do not photograph the sticker on the windscreen.</p>
        </details>
        <p className="muted small">Take all the photos in one go, with the live camera. Old photos from your gallery are
          not accepted. Don't zoom: step closer instead.</p>
        <div className="row">
          <button className="ghost" onClick={() => setStep("details")}>Back</button>
          <button disabled={!allTicked} onClick={() => { setSessionStart(Date.now()); setIdx(0); setStep("shots"); }}>Start the photos</button>
        </div>
      </section>
    );
  }

  if (step === "shots" && shot) return (
    <section className="card">
      <h2>{shot.required ? `Photo ${idx + 1} of ${shots.filter((s) => s.required).length}` : "Extra: damage close-up"}{retakeOf ? " · retake" : ""}</h2>
      <Strip shots={shots} photos={photos} idx={idx} highlight={highlight} onPick={setIdx} />
      <h3>{pretty(shot.code)}{!shot.required && " (optional)"}</h3>
      <p>{shot.what}.</p>
      {shot.tip && <p className="muted small">{shot.tip}</p>}
      {highlight.includes(shot.code) && <p className="warn-text">We need this photo again.</p>}
      {photo ? (
        <>
          <img className="preview" src={photo.dataUrl} alt={pretty(shot.code)} />
          <ul className="checks">
            {CAR_SHOTS.includes(shot.code) && <li className={photo.car?.found ? "ok-text" : "warn-text"}>
              {photo.car?.found ? `Car detected ✓ (${Math.round(photo.car.score * 100)}% sure)` : "No car detected"}</li>}
            {photo.plate && <li className={photo.plateCheck === "MATCH" ? "ok-text" : "warn-text"}>
              Plate read: <b>{photo.plate.text || "-"}</b>, {ID_LABEL[photo.plateCheck]}</li>}
            {photo.chassisRead && <li className={photo.chassisCheck === "SENT" ? "ok-text" : "warn-text"}>
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
            <button className="ghost" onClick={next}>{shot.required ? "Skip this shot" : "Skip (no damage)"}</button>
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
    const missing = shots.filter((s) => s.required && !photos[s.code]);
    const noRc = !photos.RC_CARD;
    return (
      <section className="card">
        <h2>Check your photos</h2>
        <div className="thumbs">
          {shots.map((s, i) => (
            <button key={s.code} className="thumb" onClick={() => { setIdx(i); setStep("shots"); }}>
              {photos[s.code] ? <img src={photos[s.code].dataUrl} alt="" /> : <span className="empty">{s.required ? "missing" : "optional"}</span>}
              <span>{pretty(s.code)}{photos[s.code]?.warnings.length ? " ⚠" : ""}</span>
            </button>
          ))}
        </div>
        {missing.length > 0 && <p className="warn-text">{missing.length} photo(s) missing. Missing photos will mean a retake request.</p>}
        {noRc && <p className="bad-text">Add the photo of your RC card before sending.</p>}
        {error && <p className="bad-text">{error}</p>}
        <button onClick={send} disabled={noRc || missing.length === shots.filter((s) => s.required).length}>Send for inspection</button>
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

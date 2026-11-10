/*
  Camera.jsx - the live camera for ONE shot.

  - Opens the phone's REAR camera inside the page (getUserMedia). Needs HTTPS (Render is HTTPS) or localhost.
  - For shots of the outside of the car, it runs the free on-phone car detector about 3 times a second and shows
    "Car detected" / "Move closer". When a car fills at least MIN_AREA of the frame for HOLD_MS, it captures
    by itself (auto-capture). The customer can always press the button instead.
  - For close-ups (odometer, chassis number, engine bay) there is no car to detect: the customer presses capture.
  - If the camera cannot open (laptop without camera, permission refused), it tells the parent to fall back to
    picking a photo file.
  MIN_AREA and HOLD_MS are OUR first guesses; tune them with real use.
*/
import { useEffect, useRef, useState } from "react";
import { detectCar, loadDetector } from "./detect";
import { processCanvas, toCanvas } from "./photo";

const MIN_AREA = 0.2;     // the car must cover at least 20% of the picture
const MIN_SCORE = 0.5;    // detector confidence
const HOLD_MS = 1200;     // ...steadily for 1.2 seconds before auto-capture

export default function Camera({ shot, needsCar, onCapture, onNoCamera }) {
  const video = useRef(null);
  const [state, setState] = useState("starting");   // starting | live | error
  const [det, setDet] = useState(null);
  const [detector, setDetector] = useState(needsCar ? "loading" : "off");
  const [auto, setAuto] = useState(true);
  const [countdown, setCountdown] = useState(0);
  const busy = useRef(false);
  const readySince = useRef(0);

  // 1. open the camera, close it when this screen goes away
  useEffect(() => {
    let stream;
    let cancelled = false;
    (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("no camera API");
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false,
        });
        if (cancelled) return stream.getTracks().forEach((t) => t.stop());
        video.current.srcObject = stream;
        await video.current.play();
        setState("live");
      } catch {
        if (!cancelled) { setState("error"); onNoCamera(); }
      }
    })();
    return () => { cancelled = true; stream?.getTracks().forEach((t) => t.stop()); };
  }, [onNoCamera]);

  // 2. load the detector once (only for outside shots)
  useEffect(() => {
    if (!needsCar) return;
    loadDetector().then(() => setDetector("ready")).catch(() => setDetector("failed"));
  }, [needsCar]);

  async function capture(carInfo) {
    if (busy.current || !video.current?.videoWidth) return;
    busy.current = true;
    const photo = processCanvas(toCanvas(video.current));
    onCapture({ ...photo, car: carInfo ?? null, via: "camera" });
  }

  // 3. detection loop: ~3 times a second; auto-capture when the car is big enough for long enough
  useEffect(() => {
    if (state !== "live" || detector !== "ready") return;
    let stop = false;
    const tick = async () => {
      if (stop || busy.current) return;
      try {
        const d = await detectCar(video.current);
        if (stop) return;
        setDet(d);
        const ok = d.found && d.score >= MIN_SCORE && d.areaFrac >= MIN_AREA;
        if (ok) {
          if (!readySince.current) readySince.current = Date.now();
          const held = Date.now() - readySince.current;
          setCountdown(Math.max(0, Math.ceil((HOLD_MS - held) / 400)));
          if (auto && held >= HOLD_MS) return capture(d);
        } else {
          readySince.current = 0; setCountdown(0);
        }
      } catch { /* one bad frame is not a problem */ }
      setTimeout(tick, 300);
    };
    tick();
    return () => { stop = true; };
    // capture is stable enough for this loop; re-running on every render would restart detection
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, detector, auto]);

  const ok = det && det.found && det.score >= MIN_SCORE && det.areaFrac >= MIN_AREA;
  let hint = "";
  if (needsCar) {
    if (detector === "loading") hint = "Loading the car detector (first time only)…";
    else if (detector === "failed") hint = "Car detector could not load. Take the photo with the button.";
    else if (!det || !det.found) hint = "Looking for a car… point the camera at the car.";
    else if (det.areaFrac < MIN_AREA) hint = "Car detected. Move a little closer so it fills the frame.";
    else hint = auto ? `Car detected ✓ Hold still… ${countdown || ""}` : "Car detected ✓ Press capture.";
  } else {
    hint = "Get close so the text is sharp and readable, then press capture.";
  }

  return (
    <div className="camera">
      <div className={"viewfinder" + (ok ? " ok" : "")}>
        <video ref={video} playsInline muted />
        {det?.found && video.current?.videoWidth > 0 && (
          <div className="box" style={{
            left: `${(det.box[0] / video.current.videoWidth) * 100}%`, top: `${(det.box[1] / video.current.videoHeight) * 100}%`,
            width: `${(det.box[2] / video.current.videoWidth) * 100}%`, height: `${(det.box[3] / video.current.videoHeight) * 100}%`,
          }} />
        )}
        <div className="hint">{state === "starting" ? "Opening camera…" : hint}</div>
      </div>
      <div className="row">
        <button onClick={() => capture(det)} disabled={state !== "live"}>Capture {shot ? "" : ""}</button>
        {needsCar && <label className="check small"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Auto-capture</label>}
      </div>
    </div>
  );
}

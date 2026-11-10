/*
  detect.js - FREE, ON-PHONE "eyes": no API key, no paid calls, nothing sent to an AI company.

  1. Car detection: COCO-SSD (open-source object detector, runs in the browser with TensorFlow.js).
     It recognises 80 everyday objects, including "car", "truck" and "bus". We use it to say
     "car detected" and to auto-capture when the car fills enough of the frame.
     The model files (~5 MB) are downloaded once from Google's public model storage; the photos never leave the phone.
  2. Text reading (OCR): Tesseract.js (open-source), also in the browser. Reads the number plate on the
     FRONT/REAR photos and the chassis number on its close-up.

  Both are loaded only when the camera opens ("lazy"), so the first page loads fast.
  ACCURACY IS UNTESTED on real Indian plates and VIN plates. The customer always sees what was read and can retake.
*/
let detectorPromise = null;
let ocrPromise = null;

export function loadDetector() {
  if (!detectorPromise) {
    detectorPromise = (async () => {
      const tf = await import("@tensorflow/tfjs");
      await tf.ready();
      const cocoSsd = await import("@tensorflow-models/coco-ssd");
      return cocoSsd.load({ base: "lite_mobilenet_v2" });   // the small, fast version for phones
    })();
    detectorPromise.catch(() => { detectorPromise = null; });  // allow a retry after a network error
  }
  return detectorPromise;
}

const VEHICLES = ["car", "truck", "bus"];

/** Finds the biggest vehicle in an image/video/canvas. areaFrac = share of the frame it covers (0-1). */
export async function detectCar(source) {
  const model = await loadDetector();
  const w = source.videoWidth || source.naturalWidth || source.width;
  const h = source.videoHeight || source.naturalHeight || source.height;
  const preds = await model.detect(source, 10, 0.4);
  const cars = preds.filter((p) => VEHICLES.includes(p.class));
  if (!cars.length) return { found: false, score: 0, areaFrac: 0, box: null };
  const best = cars.reduce((a, b) => (a.bbox[2] * a.bbox[3] > b.bbox[2] * b.bbox[3] ? a : b));
  const [, , bw, bh] = best.bbox;
  return { found: true, score: +best.score.toFixed(2), areaFrac: +((bw * bh) / (w * h)).toFixed(2), box: best.bbox };
}

async function getOcr() {
  if (!ocrPromise) {
    ocrPromise = (async () => {
      const { createWorker } = await import("tesseract.js");
      const worker = await createWorker("eng");
      await worker.setParameters({ tessedit_char_whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 " });
      return worker;
    })();
    ocrPromise.catch(() => { ocrPromise = null; });
  }
  return ocrPromise;
}

/** Cut a region out of a canvas, make it grey and 2x bigger: OCR reads small text much better that way. */
function prep(canvas, [x, y, w, h]) {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w * 2)); c.height = Math.max(1, Math.round(h * 2));
  const g = c.getContext("2d");
  g.filter = "grayscale(1) contrast(1.4)";
  g.drawImage(canvas, x, y, w, h, 0, 0, c.width, c.height);
  return c;
}

async function ocr(canvas, region) {
  const worker = await getOcr();
  const { data } = await worker.recognize(region ? prep(canvas, region) : prep(canvas, [0, 0, canvas.width, canvas.height]));
  return (data.text || "").toUpperCase();
}

// Indian plates: "KA 01 AB 1234", "DL 3C AB 1234", Bharat series "22 BH 1234 AA"
const PLATE = /([A-Z]{2})\s*(\d{1,2}[A-Z]?)\s*([A-Z]{0,3})\s*(\d{4})|(\d{2})\s*BH\s*(\d{4})\s*([A-Z]{1,2})/;

/**
 * Reads the number plate. Plates sit in the lower half of the car, so we try that part of the car first,
 * then the whole photo. Returns { text, raw } - text is "" if nothing plate-like was found.
 */
export async function readPlate(canvas, carBox) {
  const tries = [];
  if (carBox) {
    const [x, y, w, h] = carBox;
    tries.push([x, y + h * 0.45, w, h * 0.55]);
  }
  tries.push(null);
  let raw = "";
  for (const region of tries) {
    raw = await ocr(canvas, region);
    const m = raw.replace(/[^A-Z0-9\n ]/g, " ").replace(/\s+/g, " ").match(PLATE);
    if (m) return { text: m[0].replace(/\s+/g, " ").trim(), raw };
  }
  return { text: "", raw };
}

/** Reads the chassis number (VIN) close-up: the longest run of letters and digits; we keep the last 6. */
export async function readChassis(canvas) {
  const raw = await ocr(canvas, null);
  const tokens = raw.replace(/[^A-Z0-9]/g, " ").split(/\s+/).filter((t) => t.length >= 6);
  const best = tokens.sort((a, b) => b.length - a.length)[0] || "";
  return { text: best, last6: best.slice(-6), raw };
}

/** Compares plates ignoring spaces; one wrong character counts as "close" (the SOP's OCR-slip rule). */
export function compareIds(declared, read) {
  const a = String(declared).toUpperCase().replace(/[^A-Z0-9]/g, "");
  const b = String(read).toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (!b) return "UNREADABLE";
  if (a === b) return "MATCH";
  if (a.length === b.length && [...a].filter((ch, i) => ch !== b[i]).length === 1) return "ONE_CHAR_SLIP";
  return "DIFFERENT";
}

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

/** singleLine: tell Tesseract the crop holds ONE line of text (page-segmentation mode 7), as a plate does. */
async function ocr(canvas, region, singleLine = false) {
  return ocrImage(region ? prep(canvas, region) : prep(canvas, [0, 0, canvas.width, canvas.height]), singleLine);
}

async function ocrImage(image, singleLine) {
  const worker = await getOcr();
  await worker.setParameters({ tessedit_pageseg_mode: singleLine ? "7" : "3" });
  const { data } = await worker.recognize(image);
  return (data.text || "").toUpperCase();
}

/**
 * The letters-only part of a plate, scaled so the text is about `height` px tall, grey, with a white margin.
 * We cut off the plate's border and (cutLeft) the blue "IND" strip: Tesseract reads far better without them.
 */
function plateText(canvas, [x, y, w, h], cutLeft, height) {
  const box = clip(canvas, [x + w * cutLeft, y + h * 0.08, w * (0.98 - cutLeft), h * 0.84]);
  const k = height / box[3], pad = 16;
  const c = document.createElement("canvas");
  c.width = Math.round(box[2] * k) + 2 * pad; c.height = Math.round(box[3] * k) + 2 * pad;
  const g = c.getContext("2d");
  g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
  g.filter = "grayscale(1) contrast(1.6)";
  g.drawImage(canvas, box[0], box[1], box[2], box[3], pad, pad, c.width - 2 * pad, c.height - 2 * pad);
  return c;
}

/**
 * Finds plate-shaped bright rectangles: Indian plates are white (private) or yellow (commercial) boards with dark
 * letters, about 2 to 7 times wider than tall. Classic image processing, no model: mark the bright pixels, group
 * touching ones, keep groups with a plate's shape. Returns up to 4 boxes [x, y, w, h] in canvas pixels, best first.
 * Green (EV) and black plates are not covered yet.
 */
export function findPlateBoxes(canvas, area) {
  const [ax, ay, aw, ah] = area || [0, 0, canvas.width, canvas.height];
  const k = Math.min(1, 400 / aw);
  const w = Math.max(8, Math.round(aw * k)), h = Math.max(8, Math.round(ah * k));
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(canvas, ax, ay, aw, ah, 0, 0, w, h);
  const px = g.getImageData(0, 0, w, h).data;
  const lum = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) lum[i] = 0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2];
  const sorted = Float32Array.from(lum).sort();
  const T = Math.max(120, sorted[Math.floor(sorted.length * 0.8)]);      // "bright" = top 20% of this area
  const on = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const r = px[i * 4], gg = px[i * 4 + 1], b = px[i * 4 + 2];
    const white = lum[i] >= T && Math.max(r, gg, b) - Math.min(r, gg, b) < 70;
    const yellow = r > 150 && gg > 120 && b < 110;
    on[i] = white || yellow ? 1 : 0;
  }
  // group touching bright pixels (flood fill); the white border and the gaps between letters hold a plate together
  const seen = new Uint8Array(w * h), boxes = [];
  for (let start = 0; start < w * h; start++) {
    if (!on[start] || seen[start]) continue;
    let x0 = w, y0 = h, x1 = 0, y1 = 0, n = 0;
    const rows = new Map();                 // row -> how many of this group's pixels lie on it
    const stack = [start]; seen[start] = 1;
    while (stack.length) {
      const i = stack.pop(), x = i % w, y = (i / w) | 0;
      n++; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      rows.set(y, (rows.get(y) || 0) + 1);
      for (const j of [i - 1, i + 1, i - w, i + w]) {
        if (j >= 0 && j < w * h && on[j] && !seen[j] && Math.abs((j % w) - x) <= 1) { seen[j] = 1; stack.push(j); }
      }
    }
    // a plate is a SOLID bright band: keep the longest run of rows that are at least 45% bright. This cuts off
    // things that merely touch the plate (white grille trim, a bumper highlight)
    let bw = x1 - x0 + 1, best = [y0, y0 - 1], runStart = -1;
    for (let y = y0; y <= y1 + 1; y++) {
      const solid = y <= y1 && (rows.get(y) || 0) >= 0.45 * bw;
      if (solid && runStart < 0) runStart = y;
      if (!solid && runStart >= 0) { if (y - runStart > best[1] - best[0] + 1) best = [runStart, y - 1]; runStart = -1; }
    }
    if (best[1] < best[0]) continue;
    [y0, y1] = best;
    let m = 0;
    for (let y = y0; y <= y1; y++) m += rows.get(y) || 0;
    n = m;
    const bh = y1 - y0 + 1, aspect = bw / bh, fill = n / (bw * bh);
    // prefer the usual plate shape (about 4.2 : 1); a tilted plate looks squarer, so it is not ruled out
    const shape = Math.exp(-Math.abs(Math.log(aspect / 4.2)));
    if (aspect >= 1.5 && aspect <= 7 && bw >= w * 0.06 && bh >= 6 && fill >= 0.35) boxes.push({ x0, y0, bw, bh, score: bw * bh * fill * shape });
  }
  return boxes.sort((a, b) => b.score - a.score).slice(0, 4).map(({ x0, y0, bw, bh }) => [ax + x0 / k, ay + y0 / k, bw / k, bh / k]);
}

// Indian plates: "KA 01 AB 1234", "DL 3C AB 1234", Bharat series "22 BH 1234 AA"
const PLATE = /([A-Z]{2})\s*(\d{1,2}[A-Z]?)\s*([A-Z]{0,3})\s*(\d{4})|(\d{2})\s*BH\s*(\d{4})\s*([A-Z]{1,2})/;

// State and union-territory codes that start a normal Indian plate. A "plate" starting with anything else is
// almost certainly an OCR mistake, so we do not accept it.
const STATES = new Set(("AN AP AR AS BR CG CH DD DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD OR PB PY " +
  "RJ SK TN TR TS UK UA UP WB").split(" "));

// OCR mixes up look-alike characters. Where the plate format says "digit" or "letter", we swap the look-alike.
const TO_DIGIT = { O: "0", D: "0", Q: "0", I: "1", L: "1", T: "1", Z: "2", S: "5", B: "8", G: "6" };
const TO_LETTER = { 0: "O", 1: "I", 2: "Z", 5: "S", 8: "B", 6: "G" };
const dig = (t) => [...t].map((ch) => TO_DIGIT[ch] || ch).join("");
const let_ = (t) => [...t].map((ch) => TO_LETTER[ch] || ch).join("");
// same shape as PLATE, but each position also accepts its look-alikes
const LOOSE = /([A-Z0-9]{2}) ?([0-9OIDQLTZSBG]{1,2})([A-Z]?) ?([A-Z0-9]{0,3}) ?([0-9OIDQLTZSBG]{4})(?![A-Z0-9])/g;

/** Finds an Indian plate in OCR text, fixing look-alike slips by position. Returns "" if none. */
export function findPlate(text) {
  const clean = text.toUpperCase().replace(/[^A-Z0-9\n ]/g, " ").replace(/[ \t]+/g, " ");
  const strict = clean.match(PLATE);
  if (strict && strict[5]) return `${strict[5]} BH ${strict[6]} ${strict[7]}`;
  if (strict && STATES.has(strict[1])) {
    const d2 = /^\d$/.test(strict[2]) ? "0" + strict[2] : strict[2];
    return [strict[1], d2, strict[3], strict[4]].filter(Boolean).join(" ");
  }
  for (const line of clean.split("\n")) {
    for (const m of line.matchAll(LOOSE)) {
      const state = let_(m[1]);
      if (!STATES.has(state)) continue;
      const district = dig(m[2]) + m[3];
      const series = let_(m[4]);
      if (!/^[A-Z]{0,3}$/.test(series)) continue;
      // standard districts have 2 digits ("01"); OCR often drops the 0. Delhi-style "3C" keeps its letter.
      const d2 = /^\d$/.test(district) ? "0" + district : district;
      return [state, d2, series, dig(m[5])].filter(Boolean).join(" ");
    }
  }
  return "";
}

/**
 * Reads the number plate. Plates sit in the lower half of the car, so we try that part of the car first,
 * then the whole photo. Returns { text, raw } - text is "" if nothing plate-like was found.
 */
export async function readPlate(canvas, carBox) {
  const tries = [];      // [region, singleLine]
  let lower = null;
  if (carBox) {
    const [x, y, w, h] = carBox;
    lower = [x, y + h * 0.45, w, h * 0.55];
  }
  // 1) plate-shaped bright boxes (lower part of the car first). Each is read 6 ways (with/without the IND strip,
  //    three text sizes) and the most common answer wins: one shaky reading does not decide.
  const boxes = [...findPlateBoxes(canvas, lower), ...(lower ? findPlateBoxes(canvas, null) : [])];
  let raw = "";
  for (const b of boxes) {
    const votes = new Map();
    for (const cutLeft of [0.12, 0.03]) for (const height of [60, 90, 110]) {
      raw = await ocrImage(plateText(canvas, b, cutLeft, height), true);
      const text = findPlate(raw);
      if (text) votes.set(text, (votes.get(text) || 0) + 1);
    }
    if (votes.size) return { text: [...votes].sort((a, z) => z[1] - a[1])[0][0], raw };
  }
  // 2) the old fallbacks: lower part of the car, then the whole photo
  if (lower) tries.push([lower, false]);
  tries.push([null, false]);
  for (const [region, single] of tries) {
    raw = await ocr(canvas, region && clip(canvas, region), single);
    const text = findPlate(raw);
    if (text) return { text, raw };
  }
  return { text: "", raw };
}

function clip(canvas, [x, y, w, h]) {
  const x0 = Math.max(0, x), y0 = Math.max(0, y);
  return [x0, y0, Math.min(canvas.width, x + w) - x0, Math.min(canvas.height, y + h) - y0];
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

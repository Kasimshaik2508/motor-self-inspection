/*
  photo.js - work done ON THE PHONE for each photo, before anything is uploaded.

  WHY on the phone: the customer is standing next to the car. Telling them "too dark, retake" in one second
  is far better than telling them after an upload and a server round-trip (plan.md: device-first).
  HOW:
    1. shrink the photo so its long edge is at most 1280 px and save it as JPEG (about 150-300 KB),
       so 12 photos upload fast on mobile data;
    2. brightness = average lightness of the pixels, 0 (black) to 1 (white);
    3. sharpness  = how much neighbouring pixels differ ("variance of the Laplacian"): blurry photos are smooth,
       so the number is small.
  The two warning thresholds below are OUR first guesses, NOT calibrated. Tune them on real test photos.
*/
export const DARK_BELOW = 0.25;
export const BLURRY_BELOW = 40;

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve({ img, url });
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("This file could not be opened as a photo.")); };
    img.src = url; // browsers apply the phone's rotation (EXIF) when drawing an <img>
  });
}

function measure(img) {
  const long = 256;
  const k = Math.min(1, long / Math.max(img.naturalWidth, img.naturalHeight));
  const w = Math.max(8, Math.round(img.naturalWidth * k)), h = Math.max(8, Math.round(img.naturalHeight * k));
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, w, h);
  const px = ctx.getImageData(0, 0, w, h).data;
  const gray = new Float32Array(w * h);
  let sum = 0;
  for (let i = 0; i < w * h; i++) {
    const g = 0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2];
    gray[i] = g; sum += g;
  }
  let n = 0, m = 0, m2 = 0;
  for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
    const i = y * w + x;
    const lap = 4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - w] - gray[i + w];
    n++; m += lap; m2 += lap * lap;
  }
  const mean = m / n;
  return { brightness: +(sum / (w * h) / 255).toFixed(3), sharpness: +(m2 / n - mean * mean).toFixed(1) };
}

export async function processPhoto(file) {
  const { img, url } = await loadImage(file);
  try {
    const k = Math.min(1, 1280 / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    const dataUrl = c.toDataURL("image/jpeg", 0.82);
    const { brightness, sharpness } = measure(img);
    const warnings = [];
    if (brightness < DARK_BELOW) warnings.push("This photo looks too dark. Retake it in daylight or under a bright light.");
    if (sharpness < BLURRY_BELOW) warnings.push("This photo looks blurry. Hold the phone with both hands and keep still.");
    return { dataUrl, b64: dataUrl.split(",")[1], brightness, sharpness, capturedAt: Date.now(), warnings };
  } finally {
    URL.revokeObjectURL(url);
  }
}

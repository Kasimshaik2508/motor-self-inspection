/*
  api.js - the ONLY file that talks to the backend.

  WHY one file: the screens never build URLs themselves. When we wrap this in Capacitor (Android), the page runs
  on the phone, not on our server, so every call needs the server's full address. That address is one setting:
    VITE_API_URL   e.g. https://motor-self-inspection-api.onrender.com
  Left empty (local development), calls go to the same address as the page and Vite forwards /api to
  localhost:8000 (see vite.config.js).
*/
export const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export const get = (path) => request(path);
export const post = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

async function request(path, options) {
  let r;
  try {
    r = await fetch(API + path, options);
  } catch {
    // fetch only throws when no answer came back at all (server down, wrong address, no internet).
    throw new Error("The server did not answer. It may be down or the address may be wrong. Try again in a minute.");
  }
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).detail || ""; } catch { /* body was not JSON */ }
    throw new Error(detail || `${path} -> HTTP ${r.status}`);
  }
  return r.json();
}

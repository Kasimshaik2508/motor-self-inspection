# Project status (updated Wed 11 Nov 2026)

Deadlines: **Check-in 2 Thu 12 Nov** (deployed URL + one-page note) · Check-in 3 Mon 16 Nov · Final auction Wed 18 Nov

Overall: about 30% done (core logic built and tested; app, deployment and real-video work remain).

## Done
| Item | Result | Owner |
|---|---|---|
| Decision engine (SOP rules) | 418/420 correct (99.5%) with damage read from frame descriptions. Misses: INSP-70637 (expected REJECT, engine says RESHOOT) and INSP-71027 (expected RESHOOT) | |
| Frame reader (text to damage list) | 98.5% exact type+severity | |
| Scoring scripts on the 420 gold cases | reproducible | |
| Plan review and tech-stack decision | React + Vite (Capacitor for Android later), FastAPI | |
| Pipeline module `engine/pipeline.py` (analyze one case, evaluate all 420) | tested, 418/420 | |
| FastAPI app `backend/app.py` | run locally 10 Nov: all endpoints work, /api/evaluate = 418/420 in ~0.3 s; no code changes needed | |
| Website rebuilt in React + Vite (`web/`): case picker, decision, damage register, evaluation, data-not-loaded / server-down banners | tested 10 Nov against the real API on a separate address: inspect, filter, evaluation (418/420), phone width, no-data and server-down screens. "Waking up the server" message NOT tested (needs a sleeping Render server). Old plain-HTML page removed | |
| Requirements pinned to tested versions; `.venv/` ignored; Python 3.12 | done | |
| **Customer capture app** (10 Nov, after team feedback): guided 12-shot photos, on-phone dark/blur check, upload, vision layer (Gemini / OpenRouter, swappable), SOP decision, plain re-shoot message, one retake then surveyor | tested locally WITHOUT a model (goes to reviewer, as designed) + 11 scripted model answers through every route. Real model accuracy on car photos NOT tested: needs a key and test photos | |
| **Free on-phone camera app** (10 Nov, per Nitin): live camera, car detection + auto-capture (COCO-SSD), plate + chassis OCR (Tesseract.js), decision from phone checks, damage -> reviewer | tested: OCR reads 3 synthetic plate formats + a synthetic VIN correctly; detector loads and runs; camera fallback works; 6 phone-only routes pass. NOT tested: live camera and car detection on a real car (needs a phone test) | |
| **Reviewer console** (confirm / override with reason, photos + AI findings) | tested locally: override needs a reason, customer sees the reviewer's result. No login; memory-only storage | |
| Low-confidence gate (<0.6), identity-conflict route, re-shoot round counting | in the photo app; scripted tests pass | |
| **Demo policy database + demo photos (11 Nov, per Shashwat):** (later re-keyed by car number, see next row) 3 demo cars; 12 free-licence demo photos with credits; "Fill with demo photos" button | tested locally 11 Nov in the browser: right car -> passes to damage review; wrong chassis -> fraud desk (identity conflict); photos of a different car -> fraud desk. Customer never sees the chassis number | |
| **Car number instead of policy number (11 Nov):** self-inspection happens before a policy exists, so the customer types only the car number; the chassis comes from the RC record (synthetic stand-in for VAHAN, `engine/vehicles.py`). Chassis check unchanged and mandatory | tested locally 11 Nov in the browser: typed "ka01ab 1234" finds the car; unknown number -> clear "not found" message; right car -> passes to damage review; wrong chassis label -> fraud desk; photos of a different car (DL 3C AB 5678) -> fraud desk. API never returns the chassis. 17 scripted routes still pass. To confirm with Vansh: how the real flow identifies the car (car number vs SMS link with a proposal ID) | |
| **Real-insurer flow (11 Nov, after studying a public self-inspection demo video of another insurer):** before-you-start checklist (5 ticks + "where is the chassis number?"); shot order RC -> odometer -> chassis -> engine -> walk-around; sharper tips (engraved chassis not sticker, total km not trip, no zoom); RC card photo (required, reviewer only) + up to 3 optional damage close-ups; anti-cheat: old photo files refused on the phone, file photos / photos over 30 min / customer close-ups -> reviewer | tested locally 11 Nov: checklist locks Start until all 5 ticked; a day-old photo file refused, a fresh one accepted; via the API: live camera -> passes, file photo -> reviewer, 45-min spread -> reviewer, close-up -> reviewer; demo right car -> damage review, wrong chassis -> fraud desk; 17 scripted routes unchanged; evaluation still 418/420. NOT tested on a real phone (live camera blocked in our test browser) | |
| **AI damage check = Google Gemini 3.1 Flash-Lite (11 Nov, per Shashwat/Nitin):** one photo per request (in parallel); no damage + plate/chassis match -> approved with no person; any damage -> reviewer confirms; Gemini unavailable -> reviewer. Plate/chassis: phone OCR + Gemini, whichever matches. Hugging Face YOLO11 models tested and dropped | Model comparison (public photos, one per request): Gemini caught Indian 7/7, Korean 98/100 damaged; wrongly flagged Indian 1/33, Korean 2/50, demo 0/9 clean. Hugging Face models: flagged Indian 25/33, Korean 31/50 clean -> dropped. Real API through the app's code: clean demo car -> APPROVED with no person (~6 s); 2 damaged photos swapped in -> both caught -> reviewer. Found and fixed: a 12-photo single request missed damage and copied the plate; Gemini misread our chassis label. NOT tested: small scratches, a real car, live Render (needs VISION_PROVIDER=gemini + GEMINI_API_KEY pasted by Kasim). Free tier ~15 requests/min = 1 inspection a minute | |
| Better plate reading (11 Nov): plate-box finder, majority vote, look-alike fixes, Indian state-code check; server uses the better of front/rear | on the demo photos both plates read KA 01 AB 1234. Earlier version read neither. NOT tested on real Indian plate photos | |
| **Live on Render (10 Nov):** website https://motor-self-inspection-web.onrender.com , API https://motor-self-inspection-api.onrender.com | tested live: opens without login, Inspect works, evaluation 418/420, no console errors. Pushes to main redeploy automatically (seen 10 Nov) | |

## To do before Check-in 2 (Thu 12 Nov)
| Item | Owner | Status |
|---|---|---|
| One-page note | Kasim | Done 11 Nov: https://claude.ai/artifact/5VizMCTPruUZPg4SfDDjGJ (private until shared; export to PDF from the doc if a file is needed) |
| Fix Check-in 1 deck (team name, 3,180 wording) | Kasim | Done 11 Nov: cover says "Team 3"; proof slide now says "tune on the other 3,180, test only on the 420" |

## To do before the auction (16 and 18 Nov)
| Item | Owner | Status |
|---|---|---|
| Verified / not-verified checklist with evidence | | Not started |
| Test the live app on a phone with a real car (camera, auto-capture, plate/chassis OCR) | Kasim / team | Not started |
| Damage detection (later: free/cheap model, decided by the team) | | Later |
| Calibrate on-phone dark/blur thresholds on real photos (the night-dashboard odometer demo photo is flagged "too dark") | | Not started |
| Measure plate reading on a public Indian plate dataset (licence check first) | | Not started |
| Plain re-shoot message for the 420-case evaluation page (photo app already has it) | | Not started |
| Confirm severity ladder with problem owner | | Not started |

## Later
- Damage models: cut false alarms (try a higher threshold per type, test on real Indian car photos incl. OLX damaged-car photos); measure speed on a mid-range phone; calibrate severity; re-run the models on the server so the phone cannot fake "no damage"
- Damage models licence: CarDD-trained model A has no stated licence; for real use get permission or retrain on owned data; Ultralytics YOLO is AGPL
- **One continuous video** (driver's seat -> RC -> odometer -> chassis -> walk-around), as a real insurer does: strongest anti-cheat. Big change: ask Vansh first (our 12-shot SOP rules and 418/420 are built on photos; the challenge data also has videos)
- Read the RC card with OCR and compare its chassis number with the RC record; previous-policy pages for renewals; mobile-number login; spoken instructions in Hindi and other languages
- Server-side photo times (the phone's times can be faked)
- Test with real videos and a swappable vision model (free options)
- Capacitor Android wrap (only after Check-in 2)
- Cloud vision API for damage (team decision pending). Gemini pricing checked 10 Nov 2026 on aistudio.google.com/docs/pricing:
  - Cheapest confirmed: Gemini 3.1 Flash-Lite, $0.25 per 1M input tokens, $1.50 per 1M output (batch half price). 2.5 Flash-Lite ($0.10 / $0.40) not verified word for word.
  - An image costs 258 tokens per 768x768 tile. Our ESTIMATE (not measured): 12 photos ~13k input + ~1.5k output, about $0.006 per inspection.
  - Paid tier: link billing and prepay at least $5. Free tier exists, but Google uses free-tier inputs to improve its products, so it is fine for demo photos only. The docs do not say whether the free tier needs a card.
  - Code default GEMINI_MODEL changed to gemini-3.1-flash-lite on 11 Nov (gemini-2.5-flash retires 1 Dec 2026).
  - Free alternative still open: open-source CarDD damage models (check licences first).

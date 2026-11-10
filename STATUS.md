# Project status (updated Tue 10 Nov 2026)

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
| **Live on Render (10 Nov):** website https://motor-self-inspection-web.onrender.com , API https://motor-self-inspection-api.onrender.com | tested live: opens without login, Inspect works, evaluation 418/420, no console errors. Deployed from the public repo URL, so pushes do NOT auto-deploy: use Manual Deploy in Render | |

## To do before Check-in 2 (Thu 12 Nov)
| Item | Owner | Status |
|---|---|---|
| Reviewer console page (confirm / override a decision) | | Not started |
| One-page note | | Not started |
| Fix Check-in 1 deck (team name, 3,180 wording) | | Not started |

## To do before the auction (16 and 18 Nov)
| Item | Owner | Status |
|---|---|---|
| Re-shoot round counting (surveyor after 2nd failure) | | Not started |
| Low-confidence gate and verified / not-verified checklist | | Not started |
| Re-shoot message in plain words listing every problem (today it shows codes like TOO_DARK) | | Not started |
| Reviewer console | | Not started |
| Confirm severity ladder with problem owner | | Not started |

## Later
- Test with real videos and a swappable vision model (free options)
- Capacitor Android wrap (only after Check-in 2)

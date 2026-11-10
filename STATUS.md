# Project status (updated Tue 10 Nov 2026)

Deadlines: **Check-in 2 Thu 12 Nov** (deployed URL + one-page note) · Check-in 3 Mon 16 Nov · Final auction Wed 18 Nov

Overall: about 30% done (core logic built and tested; app, deployment and real-video work remain).

## Done
| Item | Result | Owner |
|---|---|---|
| Decision engine (SOP rules) | 418/420 correct (99.5%) | |
| Frame reader (text to damage list) | 98.5% exact type+severity | |
| Scoring scripts on the 420 gold cases | reproducible | |
| Plan review and tech-stack decision | React + Vite, FastAPI | |
| Pipeline module `engine/pipeline.py` (analyze one case, evaluate all 420) | tested, 418/420 | |
| FastAPI app `backend/app.py` | run locally 10 Nov: all endpoints work, /api/evaluate = 418/420 in ~0.3 s; no code changes needed | |
| Website `frontend/index.html` (case picker, decision, damage register, evaluation) | tested 10 Nov in a browser against the real FastAPI server: inspect + evaluation work, no console errors | |
| Requirements pinned to tested versions; `.venv/` ignored; Python 3.12 | done | |

## To do before Check-in 2 (Thu 12 Nov)
| Item | Owner | Status |
|---|---|---|
| Reviewer console page (confirm / override a decision) | | Not started |
| Public deployed URL that opens without login | | Config ready (`render.yaml`, `backend/fetch_data.py`); fail-safe tested locally (no token, wrong token). Real download from the private repo NOT yet tested: waiting on Kasim to create the data repo, token and Render account |
| One-page note | | Not started |
| Fix Check-in 1 deck (team name, 3,180 wording) | | Not started |

## To do before the auction (16 and 18 Nov)
| Item | Owner | Status |
|---|---|---|
| Re-shoot round counting (surveyor after 2nd failure) | | Not started |
| Low-confidence gate and verified / not-verified checklist | | Not started |
| Reviewer console | | Not started |
| Confirm severity ladder with problem owner | | Not started |

## Later
- Test with real videos and a swappable vision model (free options)
- Capacitor Android wrap (only after Check-in 2)

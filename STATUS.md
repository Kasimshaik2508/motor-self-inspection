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
| FastAPI app `backend/app.py` | written, NOT yet run (needs `pip install -r backend/requirements.txt`) | |

## To do before Check-in 2 (Thu 12 Nov)
| Item | Owner | Status |
|---|---|---|
| Run and check the FastAPI backend locally | | Written, untested |
| React + Vite frontend (case picker, decision, damage register, customer message) | | Not started |
| Public deployed URL that opens without login | | Not started |
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

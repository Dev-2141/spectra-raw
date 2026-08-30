# SPECTRA-SCAN AI

**Adaptive Smart Scan Scheduler for Simulated Electronic Support Spectrum Surveillance**

A receive-only, **simulation-only**, educational/research prototype. It demonstrates
how an Electronic Support (ES) receiver with limited instantaneous bandwidth can
intelligently decide *which band to scan next* and *how long to dwell*, learning
from hits, misses, false alarms, and reward.

> ⚠️ **Safety / scope.** Everything here is synthetic. No transmission, jamming,
> spoofing, emitter targeting, real/classified emitter libraries, or operational
> EW tactics. The "receiver" only *observes* a simulated spectrum.

---

## Status — Step 1 of 5 complete

| Area | Delivered in Step 1 |
| --- | --- |
| Project scaffold | `backend/` (FastAPI) + `frontend/` (React+Vite+TS) + `docs/` |
| Simulation core | Synthetic RF environment, receiver digital twin, reward engine, step engine |
| Emitter behaviors | `constant`, `burst`, `periodic`, `hopping`, `low_duty`, `priority` |
| Schedulers | `round_robin`, `random` (baselines) |
| Metrics | Pd, false-alarm rate, interception ratio, intercept delay, reward, coverage, revisit, missed opportunities, high-priority rate, correct-prediction % |
| API | `/api/health`, `/api/state`, `/api/simulation/reset|step|run`, `/api/schedulers` |
| Frontend | Dark dashboard shell: header, control panel, spectrum/waterfall/scan-path previews, metrics panel, status bar |
| Tests | 12 `pytest` tests (environment shape, activity, determinism, step/time, round-robin cycle, metrics, all API endpoints) |

Smart schedulers, dataset lab, strategy comparison, and the full dashboard arrive
in Steps 2–5.

---

## Requirements

- Python 3.11+
- Node.js 20+ / npm

## Run the backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS/Linux:         source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Health:   http://127.0.0.1:8000/api/health

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to
`http://127.0.0.1:8000` (override with `VITE_API_TARGET`).

## Run the tests

```bash
cd backend
.venv\Scripts\python -m pytest -q      # Windows
# or: python -m pytest -q
```

---

## How the simulator works (Step 1)

- The spectrum is divided into `num_bands` (default 64) frequency bands.
- Time advances in discrete slots (default 1000).
- `RFEnvironment` paints a deterministic ground-truth `occupancy` matrix
  `(time_slots × bands)` plus SNR, power, and threat matrices from a seeded RNG.
- Emitter activity runs are collapsed into **events** used for interception and
  intercept-delay metrics.
- `Receiver` observes one band (or a small window) per dwell. Detection is a
  logistic function of the synthetic SNR relative to the detection threshold;
  false alarms occur at a fixed rate on inactive scans.
- `Simulation.step()` asks the active scheduler for a `ScanDecision`, tunes the
  receiver, observes, scores the outcome with the reward engine, updates running
  estimates and metrics, and advances time.

### Reward table

```
+10 high-priority detection      -2  empty scan
+5  normal detection             -4  false alarm
+1  correct inactive prediction  -6  missed active signal (per unscanned active band)
-1  retune cost                  -10 missed high-priority signal
```

Open-loop baselines (round-robin, random) accrue large missed-opportunity
penalties — that gap is what the smart schedulers in Step 2 will close.

---

## Project layout

```
backend/
  app/
    main.py            FastAPI app + CORS
    api/               routes + process-wide SimulationManager
    models/            Pydantic models (Band, Emitter, ScanDecision, ...)
    simulation/        environment, receiver, reward, engine
    schedulers/        base + baselines + registry
    metrics/           incremental MetricsTracker
  tests/               pytest suite
  data/                saved datasets (Step 3)
frontend/
  src/App.tsx          dashboard shell
  src/api.ts           typed API client
docs/                  design notes
```

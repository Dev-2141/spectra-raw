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

## Status — Steps 1–4 of 5 complete

| Area | Delivered |
| --- | --- |
| Project scaffold | `backend/` (FastAPI) + `frontend/` (React+Vite+TS) + `docs/` |
| Simulation core | Synthetic RF environment, receiver digital twin, reward engine, step engine |
| Emitter behaviors | `constant`, `burst`, `periodic`, `hopping`, `low_duty`, `priority` |
| Baseline schedulers | `round_robin`, `random` |
| Smart schedulers | `priority` (weighted score), `epsilon_bandit`, `ucb_bandit`, `thompson`, `q_learning` (tabular, multi-episode training) |
| Explainability | every decision returns confidence, top-3 reasons, alternatives, prediction, and a plain-English explanation |
| Metrics | Pd, false-alarm rate, interception ratio, intercept delay, reward, coverage, revisit, missed opportunities, high-priority rate, correct-prediction % |
| Dataset lab | DeepSense-style generator (occupancy / power / SNR / threat / emitter-type-label matrices), NPY+CSV+JSON store, replay as simulation environment |
| Strategy comparison | run all schedulers on one shared scenario (seed or replayed dataset), weighted-score winner, time series, JSON/CSV/HTML export |
| API | `health`, `state`, `schedulers`, `simulation/{reset,step,run,train}`, `dataset/{generate,list,{id},{id}/stats,{id}/preview,{id}/load}`, `comparison/{run,last,export/{fmt}}`, `explainability/log`, `training/{runs,last}`, `report/run[/export/{fmt}]` |
| Frontend | Full tabbed dashboard — persistent control sidebar (transport, speed, scheduler, env/receiver config, presets) + six views: **Live Monitor** (spectrum, waterfall + scan-path overlay, live metric cards, active-decision panel, event log, reward timeline), **Strategy Comparison** (ranked table, bar + line charts, winner badge, exports), **Dataset Lab** (generate form, list, stat cards, preview heatmap, load), **Training Runs** (train form, per-episode chart + table), **Explainability Log** (filterable live decision log), **Reports** (run report + last comparison, CSV/JSON/HTML export). Hand-built responsive SVG/canvas charts, no chart dependency. |
| Tests | 59 `pytest` tests (Steps 1–4) |

Polish, scenario presets, metric hardening, judge-ready docs + demo script (Step 5) are next.

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
penalties — the adaptive schedulers (`priority`, bandits, `q_learning`) close
that gap by revisiting active/high-threat bands sooner.

## Datasets & strategy comparison (Step 3)

```bash
# generate a reusable synthetic dataset from the current config
curl -X POST http://127.0.0.1:8000/api/dataset/generate \
  -H "Content-Type: application/json" \
  -d '{"name":"sparse-demo","config":{"num_bands":64,"num_time_slots":1000,"seed":2025}}'

curl http://127.0.0.1:8000/api/dataset/list
curl -X POST http://127.0.0.1:8000/api/dataset/<id>/load          # replay it as the live env

# run every scheduler against one shared scenario and rank them
curl -X POST http://127.0.0.1:8000/api/comparison/run \
  -H "Content-Type: application/json" \
  -d '{"schedulers":["round_robin","random","priority","epsilon_bandit","ucb_bandit","q_learning"],"steps":1000}'

curl http://127.0.0.1:8000/api/comparison/export/csv    # or /json, /html
```

Datasets are stored under `backend/data/datasets/<id>/` as `meta.json` +
`*.npy` (source of truth) + `*.csv` mirrors. The comparison winner is chosen by
a weighted score over interception ratio, high-priority detection rate, average
reward, and (inverted) missed opportunities and intercept delay — no metric is
hardcoded per strategy.

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

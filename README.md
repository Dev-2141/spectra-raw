# SPECTRA-SCAN AI

**Adaptive Smart Scan Scheduler for Simulated Electronic Support Spectrum Surveillance**

A receive-only, **simulation-only**, educational / research prototype. It shows how
an Electronic Support (ES) receiver with limited instantaneous bandwidth can
*intelligently* decide which band to scan next, how long to dwell, and how to
improve from hits, misses, false alarms, and reward — entirely on synthetic RF.

> ## Safety / scope
> Everything here is synthetic. **No transmission, no jamming, no spoofing, no
> emitter targeting, no real or classified emitter libraries, no operational EW
> tactics.** The "receiver" only *observes* a simulated spectrum. `/api/health`
> reports `transmit_capability: false`. There is no code path that emits RF.

---

## Status — all 5 build steps complete

| Step | Delivered |
| --- | --- |
| 1 | Project scaffold, synthetic RF environment, receiver digital twin, reward engine, step engine, `round_robin` + `random` schedulers, metrics, dashboard shell |
| 2 | `priority`, `epsilon_bandit`, `ucb_bandit`, `thompson`, `q_learning` schedulers; per-decision explainability; multi-episode Q-learning training |
| 3 | DeepSense-style dataset generator + store (NPY/CSV/JSON) + replay; strategy comparison engine; JSON/CSV/HTML export |
| 4 | Full tabbed dashboard: Live Monitor, Strategy Comparison, Dataset Lab, Training Runs, Explainability Log, Reports |
| 5 | Six scenario presets, metric hardening, loading/error/empty states, expanded tests (**75 passing**), this README + demo script |

---

## 1. Project overview

The full product is two services:

- **Backend** — Python + FastAPI. Owns the synthetic RF environment, the receiver
  digital twin, the schedulers, the reward + metrics engines, the dataset store,
  and the strategy-comparison engine. Pure NumPy/Pandas/scikit-learn; no ML
  framework required.
- **Frontend** — React + Vite + TypeScript, a dense dark "RF analytics" dashboard.
  Charts are hand-built responsive SVG/canvas (no chart dependency).

```
backend/app/
  main.py            FastAPI app + CORS
  api/               routes + process-wide SimulationManager
  models/            Pydantic models
  simulation/        environment, receiver, reward, engine, presets
  schedulers/        base + baselines + smart + q-learning + registry
  metrics/           incremental MetricsTracker
  dataset/           generator, store, stats  (DeepSense-style)
  comparison/        strategy comparison engine + export
  reporting.py       run-report CSV/HTML
frontend/src/
  useSim.ts          central state hook + play loop
  ControlSidebar.tsx persistent controls + scenario presets
  charts.tsx         SpectrumChart, Waterfall, LineChart, BarChart, Sparkline
  views/             one file per dashboard tab
```

## 2. Problem statement mapping

| Real ES problem | In this prototype |
| --- | --- |
| Wide RF spectrum, many possible emitters | `num_bands` frequency bands (default 64), 6 synthetic emitter behaviours |
| Receiver sees only a narrow slice at a time | receiver observes **one band** (or a small `scan_window`) per dwell |
| Must choose where to look next | pluggable **scheduler** returns a `ScanDecision` each time slot |
| Retuning costs time | `retune_delay_slots` dead time whenever the band changes |
| Detection is probabilistic (SNR, noise) | logistic P(detect) vs `detection_threshold_db`; fixed false-alarm rate |
| Intercepting high-value emitters matters most | per-emitter `threat`; high-priority detection rate + reward weighting |
| Learn from experience | bandit value updates / Q-learning / priority-score feedback each step |

## 3. Why open-loop scanning is weak

`round_robin` sweeps every band in a fixed order; `random` picks uniformly. Both
ignore everything they observe. On a wide spectrum with sparse or moving emitters:

- while the receiver marches through empty bands, **active bands elsewhere go
  unscanned** — every such band-slot is a *missed opportunity* (−6, or −10 if
  high-priority);
- a periodic ("radar-like") emitter is only caught if the sweep happens to line
  up with its pulse;
- a frequency-hopping emitter is almost never where the linear sweep is.

The adaptive schedulers close that gap by revisiting recently-active and
high-threat bands sooner, estimating periodicity, and spending their scan budget
where it pays off. In the **Periodic Radar-Like** preset the `priority` scheduler
scores an average reward around **−0.6** versus **−18** for both baselines; in the
**Frequency Hopping** and **High-Threat Low-Duty** presets it roughly triples the
high-priority detection rate.

## 4. How the simulator works

- The spectrum is divided into `num_bands` bands; time advances in discrete slots
  (default 1000).
- `RFEnvironment` uses a **seeded RNG** to paint deterministic ground-truth
  matrices `(time_slots × bands)`: `occupancy` (bool), `snr_db`, `power_db`,
  `threat`, plus an `emitter_id` map. Same seed ⇒ identical scenario, which is
  what makes strategy comparison fair.
- Emitter behaviours: `constant` (long on-blocks), `burst` (short random bursts),
  `periodic` (fixed interval pulse train), `hopping` (parks on a band then steps
  ±4), `low_duty` (rare 1–2 slot emissions), `priority` (intermittent, threat
  0.75–1.0). A scenario can override the behaviour mix via `behavior_weights`.
- Activity runs are collapsed into **events** (contiguous per-band activity) used
  for interception and intercept-delay metrics.
- `Receiver` observes the chosen band at time `t`. If a truly-active band is in
  the scan window: `measured_snr = true_snr + N(0, σ)`, `P(detect) =
  sigmoid((true_snr − threshold) / 2)`. If not: a false alarm fires with
  probability `false_alarm_prob`.
- `Simulation.step()` = ask scheduler → tune (maybe pay retune) → observe → score
  with the reward engine → update running estimates + metrics + scheduler
  feedback → advance time.
- A saved dataset can be *replayed* as the environment (`env.replayed == True`),
  a drop-in for the live generator.

## 5. How the schedulers work

| Name | Idea |
| --- | --- |
| `round_robin` | fixed sequential sweep, no adaptation (baseline) |
| `random` | uniform random band each dwell (baseline) |
| `priority` | weighted score per band over **recent activity estimate**, **staleness** (time since last visit), **uncertainty** (`1/√visits`), **threat prior**, **previous hit rate**, and a **periodicity bonus** from an internal per-band period estimator |
| `epsilon_bandit` | each band is an arm; with prob. ε explore a random arm, else exploit the highest mean payoff; payoff = reward squashed to [0,1] |
| `ucb_bandit` | UCB1 — unpulled arms first, then `value + c·√(ln t / n)`; encourages probing under-scanned bands |
| `thompson` | Beta-Bernoulli posterior on P(hit) per band; sample each posterior, scan the argmax |
| `q_learning` | tabular Q. State = (current-band bucket, recent-hit bucket, time-since-last-visit bucket, threat bucket, time mod periodic-window). Action = next band. TD update applied on the next decision; `α, γ, ε` (+ decay) configurable; trains over multiple episodes keeping its Q-table |

Every scheduler returns an explainability payload: `selected_band`, `confidence`,
`predicted_active`, **top-3 reasons**, **alternative candidate bands**, and a
one-line `explanation`.

## 6. Reward function

Computed per dwell by `simulation/reward.py`:

```
+10  high-priority detection      (detected & true active & threat ≥ 0.7)
 +5  normal detection
 +1  correct inactive prediction  (scheduler predicted idle and band was idle)
 -1  retune cost                  (band changed this dwell)
 -2  empty scan                   (idle band, no prediction credit)
 -4  false alarm
 -6  missed active signal         (per active band this slot the receiver did NOT scan)
-10  missed high-priority signal  (same, threat ≥ 0.7)
```

Open-loop baselines accumulate large `missed_active` / `missed_high_priority`
penalties because a 1-band receiver cannot cover a wide spectrum — the *relative*
gap between strategies is the signal.

## 7. Metrics

| Metric | Definition |
| --- | --- |
| Probability of detection | `hits / scans that landed on a truly active band` |
| False alarm rate | `false alarms / inactive scans` |
| Interception ratio | `detected emitter events / emitter events started by the current slot` |
| Average intercept delay | mean of `first_detection_slot − event_start` over detected events |
| Average reward | `total reward / steps` |
| High-priority detection rate | `high-priority events detected / high-priority events` |
| Missed opportunity count | Σ over slots of (active bands that slot the receiver did not scan) |
| Scan coverage | `unique scanned bands / total bands` |
| Average revisit time | mean gap between consecutive visits to the same band |
| Correct prediction % | `correct activity predictions / predictions made` (baselines make none) |

Denominators are guarded against divide-by-zero; snapshot values are rounded to
4 dp. `test_step5.py` recomputes several of these from the raw step history and
asserts they match.

## 8. Run the backend

Requires **Python 3.11+**.

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS / Linux:       source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Health:   http://127.0.0.1:8000/api/health

Key endpoints: `GET /api/state`, `GET /api/presets`,
`POST /api/simulation/{reset,step,run,train}`,
`GET|POST /api/dataset/{generate,list,{id},{id}/stats,{id}/preview,{id}/load}`,
`POST /api/comparison/run` + `GET /api/comparison/export/{json,csv,html}`,
`GET /api/explainability/log`, `GET /api/training/runs`,
`GET /api/report/run` + `/export/{json,csv,html}`.

## 9. Run the frontend

Requires **Node.js 20+**.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api -> :8000)
```

## 10. Run the tests

```bash
cd backend
.venv\Scripts\python -m pytest -q      # Windows
# or: python -m pytest -q              # 75 passed
```

Coverage includes: environment matrix shape, emitter activity present, seed
determinism, receiver step advances time, round-robin cycles correctly, every
scheduler runs 500+ steps, reward-engine signs, Q-learning trains over episodes,
strategy comparison returns all strategies on an identical scenario, dataset
save/load roundtrip + replay reproduces ground truth, all API endpoints, all six
presets run, metric denominators match their definitions, and smart schedulers
beat the baseline on the tuned presets.

## 11. Demo script for judges

Full version with exact clicks: [`docs/DEMO.md`](docs/DEMO.md). Short form:

1. Open the dashboard (`http://localhost:5173`) — **Live Monitor** tab.
2. Scheduler = `round_robin`, click **apply & reset**, then **▶ play**.
3. Watch **missed opportunities** climb and **avg reward** sit deep negative;
   the waterfall shows active bands the sweep walks past.
4. Scheduler = `priority`, **apply & reset**, **▶ play** again.
5. **P(detection)**, **interception ratio** and **avg reward** all improve; the
   scan path clusters on active / high-threat bands.
6. Apply the **Periodic Radar-Like Challenge** preset → **Strategy Comparison**
   tab → **run comparison** → `priority` wins with a large reward margin.
7. Back on **Live Monitor**, inspect the **waterfall + scan-path overlay**
   (hit / miss / false-alarm / empty markers).
8. Open the **Explainability Log** — every decision with confidence, top factors,
   alternatives, reward breakdown; filter to `hit`.
9. **Dataset Lab** → generate a dataset → **preview heatmap** → **load into
   simulation** (replay mode badge appears).
10. **Reports** tab → export the run report and the comparison (**CSV / JSON /
    HTML**).

## 12. Limitations

- Single-band receiver on a wide spectrum: even the best scheduler misses most
  band-slots, so absolute reward stays negative — compare strategies *relative*
  to each other.
- Q-learning uses a coarse hand-designed state and a full-width action space; it
  learns a useful policy over episodes but does not converge to optimal in 1000
  steps. Priority and the bandits are stronger out of the box.
- The synthetic emitter models are deliberately simple (no multipath, Doppler,
  co-channel interference, or realistic modulation).
- The play loop is HTTP polling on localhost; fine for a demo, not a streaming
  telemetry pipeline.
- Metrics count emitter events that begin near the final slot in the denominator,
  which slightly understates interception ratio late in a short run.

## 13. Safety note

SPECTRA-SCAN AI is a **simulation-only, receive-only concept demonstrator**. It
models *listening* to a synthetic spectrum. It contains **no transmission,
jamming, spoofing, direction-finding-for-targeting, real emitter libraries, or
classified data**, and no capability to affect any real RF device. It is intended
for education and research into scan-scheduling algorithms only.

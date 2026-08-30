# SPECTRA-SCAN AI — Function & Theory Reference

A complete walk-through of every module, class, and function in the codebase, with
the theory behind each feature. Read [`../README.md`](../README.md) first for the
high-level picture and [`architecture.md`](architecture.md) for the data-flow
summary.

Contents:

- [Part I — Theory foundations](#part-i--theory-foundations)
- [Part II — Backend reference](#part-ii--backend-reference)
- [Part III — Frontend reference](#part-iii--frontend-reference)
- [Part IV — HTTP API reference](#part-iv--http-api-reference)
- [Part V — End-to-end data flow](#part-v--end-to-end-data-flow)

---

# Part I — Theory foundations

## I.1 The Electronic Support (ES) scan-scheduling problem

An **Electronic Support** receiver listens to the RF spectrum to *intercept* and
characterise transmissions it did not create. A real receiver has **limited
instantaneous bandwidth**: at any instant it can only observe a narrow slice of a
much wider spectrum of interest. It must therefore *schedule* its attention —
decide which frequency band to tune to next, and how long to dwell there — while
emitters switch on and off, move in frequency, and vary in importance.

This is a **sequential decision problem under partial observability**:

- **State** = which bands are active right now, with what power/SNR/threat. The
  receiver never sees the full state; it only gets a measurement of the one band
  it looked at.
- **Action** = the next band to scan (and, in principle, the dwell length).
- **Observation** = "signal present / absent" on the scanned band, with detection
  and false-alarm errors.
- **Reward** = mission value of the outcome: catching a high-value emitter is
  good, an empty look or a false alarm is bad, and *not* looking at a band that
  was transmitting is the worst (a missed intercept).

Formally it is a **Partially Observable Markov Decision Process (POMDP)**. Solving
a POMDP optimally is intractable in general, so practical schedulers use
heuristics (priority scores), **online learning** (multi-armed bandits), or
**approximate reinforcement learning** (tabular Q-learning). SPECTRA-SCAN AI
implements all three families and lets you compare them on identical synthetic
scenarios.

## I.2 Why an open-loop sweep is weak

A **round-robin** scan visits band 0, 1, 2, … N−1, 0, 1, … forever. A **random**
scan picks uniformly. Both are *open-loop*: the next action does not depend on
anything observed. Their weaknesses follow directly from the problem structure:

- **Revisit time is fixed at N.** If an emitter's on-period is shorter than N
  slots, the sweep can walk past it entirely. Sparse and bursty emitters are
  routinely missed.
- **No use of periodicity.** A radar-like emitter that fires every P slots is
  only caught when the sweep phase happens to align with P — a coincidence.
- **No use of mobility.** A frequency-hopping emitter is almost never where a
  linear sweep currently is.
- **No use of value.** A high-threat emitter gets exactly the same 1/N share of
  attention as an empty band.

Every slot in which an active band is *not* the scanned band is a **missed
opportunity**. Adaptive schedulers reduce missed opportunities by shortening the
effective revisit time for bands that are *likely* active or *high value*, at the
cost of longer revisit time for bands that appear quiet.

## I.3 Detection theory (the receiver model)

When the receiver dwells on an active band, it forms an SNR estimate
`measured_snr = true_snr + N(0, σ)` (thermal-noise-limited estimation error).
Detection is modelled as a **logistic (sigmoid) function of SNR margin**:

```
P(detect | true_snr) = 1 / (1 + exp( −(true_snr − threshold) / scale ))
```

with `scale = 2 dB`. This is the standard smooth approximation to a
threshold-crossing detector's ROC behaviour: well below threshold → ~0, well
above → ~1, a soft transition around the threshold. A detection also requires the
noisy estimate itself to clear the threshold, so raising `detection_threshold_db`
lowers P(detect) *and* the false-alarm rate together — the classic
**detection / false-alarm trade-off**.

On an **inactive** band the estimator sees noise only; a **false alarm** is drawn
with fixed probability `false_alarm_prob` per scan (a Bernoulli model of the
constant-false-alarm-rate operating point).

## I.4 Emitter behaviour models

Six synthetic activity patterns, chosen to exercise different scheduler
strengths:

| Behaviour | Model | Which scheduler it rewards |
| --- | --- | --- |
| `constant` | a few long on-blocks covering most of the timeline | any; easy |
| `burst` | short random bursts (1–4 slots), gaps 6–33 | short revisit / recency |
| `periodic` | pulse of 1–3 slots every fixed P ∈ [9,40], random phase | **periodicity estimation** |
| `hopping` | parks on a band for a few slots, then steps ±4 bands | **recency-chasing bandits** |
| `low_duty` | 1–2 slot emissions, 1–4 % duty cycle | coverage + luck |
| `priority` | intermittent 3–8 % duty, threat 0.75–1.0 | **threat-weighted scoring** |

A scenario's `behavior_weights` bias the sampling of behaviours so a preset can be
made hopping-heavy, periodic-heavy, etc.

## I.5 Reward shaping

The reward table (see README §6) encodes the mission objective as a scalar so
that learning schedulers have a signal to optimise. Design points:

- **Asymmetry.** A missed active signal (−6) hurts more than an empty scan (−2),
  and a missed *high-priority* signal (−10) more than a normal detection helps
  (+5). This pushes schedulers toward recall of important emitters even at the
  cost of some wasted looks.
- **Prediction credit (+1).** A scheduler that can say "this band is idle" and be
  right is rewarded, which is what makes `correct_prediction_percentage` a
  meaningful metric and gives the priority/Q schedulers a reason to model
  inactivity, not just activity.
- **Retune cost (−1).** A small friction term so a scheduler does not thrash
  between bands for no gain — the analogue of real retune/settle time.
- **Missed-opportunity term is global.** It is charged every slot for *every*
  active band the receiver is not on, so a 1-band receiver on a wide spectrum
  always runs a negative average reward. The absolute number is not the point;
  the **gap between strategies** is.

## I.6 Multi-armed bandits

Treat each of the N bands as a slot-machine **arm** with an unknown payoff
distribution. Each dwell "pulls" one arm and observes a payoff. The
**exploration/exploitation dilemma**: pull the arm you currently believe is best
(exploit) or pull an uncertain arm to learn about it (explore)?

- **ε-greedy** — with probability ε pull a uniformly random arm, otherwise pull
  the arm with the highest running mean payoff. Simple; ε controls exploration.
  Value update is an incremental sample mean:
  `Q ← Q + (payoff − Q) / count`.
- **UCB1** (Upper Confidence Bound) — pull `argmax_i [ Q_i + c·√(ln t / n_i) ]`.
  The bonus term is a high-probability upper bound on the true mean derived from
  Hoeffding's inequality; it is large for rarely-pulled arms, so UCB1
  **automatically** explores under-scanned bands without an ε parameter. Unpulled
  arms have an infinite bonus and are tried first.
- **Thompson sampling** — keep a **Beta(α, β) posterior** on each band's hit
  probability (Beta is the conjugate prior for a Bernoulli "hit / no-hit"). Each
  slot, draw one sample from every posterior and scan the arm with the largest
  draw. Exploration is probability-matched to posterior uncertainty; it is often
  the strongest simple bandit in practice.

In this codebase the "payoff" for ε-greedy/UCB is the per-dwell reward squashed
to [0, 1] (`_reward_to_unit`); Thompson uses the raw hit/no-hit outcome.

## I.7 Reinforcement learning — tabular Q-learning

Q-learning learns an **action-value function** `Q(s, a)` — the expected
discounted future reward of taking action `a` in state `s` and acting greedily
thereafter — without a model of the environment. The update is the **temporal-
difference** rule:

```
Q(s,a) ← Q(s,a) + α · [ r + γ·max_a' Q(s',a') − Q(s,a) ]
```

- `α` (learning rate) — how much each new experience moves the estimate.
- `γ` (discount) — how much future reward counts vs. immediate.
- `r + γ·max Q(s',·)` is the **TD target**; the bracket is the **TD error**.

Because `Q` is a lookup table, the continuous world must be **discretised** into a
finite state. SPECTRA-SCAN AI's state is the tuple

```
(current-band bucket, recent-hit bucket, time-since-last-visit bucket,
 threat bucket, time-mod-periodic-window bucket)
```

The last feature lets the table represent "we are at a phase of the periodic
window where band X usually fires". The action is the next band index.
**Exploration** is ε-greedy with decay (`ε ← max(ε_min, ε·decay)`), so the policy
explores early and exploits later. Training runs **multiple episodes**: the
environment is regenerated each episode (a different seed) but the Q-table
persists, so the agent learns a policy that generalises rather than memorising one
scenario. The TD update for the previous `(s, a)` is applied at the *start* of the
next decision, when the successor state `s'` is finally known; `end_episode()`
flushes the last transition with no bootstrap.

## I.8 Priority-score scheduling

A hand-designed heuristic that scores every band each slot and scans the argmax.
The score is a weighted sum of normalised features, each with a clear rationale:

| Feature | Formula (per band) | Rationale |
| --- | --- | --- |
| recent activity | running EMA of hit/no-hit | emitters that were on recently tend to still be on |
| staleness | `min(1, since_last_visit / 2N)` | the longer a band is unwatched, the more could have happened there |
| uncertainty | `1 / √(visits + 1)` | information gain is highest where we have the least data (optimism under uncertainty) |
| threat prior | static per-band max threat | spend attention where an intercept is worth most |
| previous hit rate | `hits / max(1, visits)` | empirical productivity of the band |
| periodicity bonus | Gaussian around the predicted next-emission phase | catch radar-like emitters *at* their pulse |

The **periodicity estimator** keeps the last ~12 detection slots per band; if the
gaps between them are consistent (std ≤ ½·mean + 1) it sets the band's period to
their **median gap**. The bonus is `exp(−(d/0.15)²)` where `d` is the fractional
distance from the current phase to a multiple of the period — near 1 when the band
is "due", near 0 otherwise.

## I.9 Metrics theory

The metrics are chosen so that no single one can be gamed without hurting
another, and every denominator is a *fair-chance* count:

- **Probability of detection** = detections / (scans that landed on a truly
  active band). This is *conditional on looking* — it isolates the receiver's
  detector quality from the scheduler's targeting.
- **Interception ratio** = distinct emitter **events** detected / events begun so
  far. An "event" is a contiguous run of activity in one band; detecting it once
  counts. This is the scheduler-level recall metric.
- **Average intercept delay** = mean of `first_detection_slot − event_start` over
  detected events. Lower is better; it measures *timeliness*, not just eventual
  capture.
- **Missed opportunity count** = Σ over slots of (active bands ≠ scanned band).
  The raw cost of limited bandwidth.
- **Scan coverage** = unique bands visited / N. Breadth.
- **Average revisit time** = mean gap between consecutive visits to the same
  band. Adaptivity: a good scheduler drives this *down* for productive bands.
- **High-priority detection rate** = high-threat events detected / high-threat
  events. Mission value.
- **False alarm rate** = false alarms / inactive scans. The cost side of the
  detection trade-off.
- **Correct prediction %** = correct activity predictions / predictions made.
  Rewards a scheduler that *models* the spectrum, not just reacts.

## I.10 Strategy comparison & weighted scoring

To compare schedulers fairly, each is run in its **own simulation seeded
identically** (or replaying the same saved dataset), so the ground-truth
matrices are byte-for-byte the same across strategies — the only variable is the
policy. The **winner** is the argmax of a weighted score over min-max-normalised
metrics:

```
score = 0.35·avg_reward_n
      + 0.25·interception_ratio_n
      + 0.20·high_priority_detection_rate_n
      + 0.10·(1 − missed_opportunity_n)
      + 0.10·(1 − intercept_delay_n)
```

`avg_reward` carries the most weight because it *is* the objective the learning
schedulers optimise; interception and high-priority detection capture mission
value; missed count and delay are secondary and inverted (lower is better).
Min-max normalisation is per-comparison, so the score answers "best **among these
strategies on this scenario**", not an absolute grade.

## I.11 DeepSense-style datasets

"DeepSense" refers to the style of synthetic **time–frequency occupancy datasets**
used to train spectrum-sensing / signal-classification models: a stack of
2-D arrays over (time, frequency) plus labels. Here a dataset is:

- `occupancy` — binary "is a signal present" per (t, band). The classic
  spectrum-sensing target.
- `power_db`, `snr_db` — the analogue measurements a real sensor would digitise.
- `threat` — a synthetic per-cell value score.
- `labels` — per-cell **emitter-type code** (−1 where idle); the target for a
  modulation/type classifier.
- `emitter_id` — which emitter owns each active cell (for event reconstruction).

Datasets are saved as NPY (canonical) + CSV (portable) + a JSON metadata sidecar,
and can be **replayed** as the live environment so a scheduler faces a fixed,
shareable scenario.

---

# Part II — Backend reference

Package root: `backend/app/`. Import-time note: `app/__init__.py` carries the
project safety statement and `__version__`.

## II.1 `app/main.py` — ASGI application

| Symbol | What it does |
| --- | --- |
| `app` | The `FastAPI` instance. Title/description carry the safety note. |
| CORS middleware | Allows the Vite dev origin (`localhost:5173`) by default; override with `SPECTRA_CORS_ORIGINS` (comma-separated). |
| `app.include_router(router)` | Mounts all `/api/*` routes from `app.api.routes`. |
| `root()` → `GET /` | Returns a pointer JSON: product name, `/docs`, `/api/health`, mode. |

**Run:** `uvicorn app.main:app --port 8000`.

## II.2 `app/models/core.py` — Pydantic schemas

These are **data contracts**, not behaviour; they validate request bodies and
shape responses. Key ones:

| Model | Role |
| --- | --- |
| `EmitterBehavior` | `str, Enum` of the six behaviour names. |
| `Band` | index, synthetic `center_mhz`, `width_mhz`. |
| `Emitter` | id, label, behaviour, `home_band`, `threat` (0–1), `high_priority`, nominal `snr_db`, `duty_cycle`, behaviour params. |
| `RFEnvironmentConfig` | scenario knobs: `num_bands` (64), `num_time_slots` (1000), `emitter_density`, `noise_floor_db`, `snr_min_db`/`snr_max_db`, `high_priority_fraction`, `behavior_weights` (optional emitter-mix override), `seed`. |
| `ReceiverConfig` | `dwell_slots`, `retune_delay_slots`, `detection_threshold_db`, `snr_measurement_noise_db`, `false_alarm_prob`, `scan_window`. |
| `ReceiverState` | mutable: `current_band`, `retune_cooldown`, `visited_bands`, `detections`, `total_scans`. |
| `ScanDecision` | scheduler output + **explainability**: `selected_band`, `confidence`, `predicted_active`, `reasons` (≤3), `alternatives`, `explanation`. |
| `DetectionEvent` | outcome of one observation: `true_active`, `detected`, `false_alarm`, `measured_snr_db`, `measured_power_db`, `threat`. |
| `SchedulerMetrics` | the full metric set (see Part I.9) + raw counters. |
| `SimulationStepResult` | everything from one dwell: decision, detection, reward, `reward_breakdown`, `retuned`, `done`, `metrics` snapshot. |
| `ResetRequest` / `StepRequest` / `RunRequest` / `TrainRequest` | request bodies for the simulation endpoints. `ResetRequest.preset` selects a named scenario. |
| `EpisodeResult` / `TrainingReport` | per-episode training summary + roll-up (first/last avg reward, improvement, best episode). |
| `DatasetStats` / `DatasetMeta` | dataset statistics and the JSON sidecar descriptor. |
| `DatasetGenerateRequest` / `DatasetLoadRequest` | dataset endpoint bodies; `preset` generates from a preset's environment. |
| `ComparisonRequest` / `ComparisonSeries` / `ComparisonEntry` / `ComparisonReport` | strategy-comparison request and result shapes. |

## II.3 `app/simulation/environment.py` — synthetic RF ground truth

**Theory:** this module *is* the POMDP's hidden state. Everything is precomputed
deterministically from `seed` so a scenario is fully reproducible and a scheduler
can never "cheat" by reading it (schedulers only get the `SchedulerContext`).

### `EmitterEvent` (dataclass)
A contiguous activity run for one emitter in one band: `emitter_id`, `band`,
`start`, `end` (inclusive), `high_priority`, `threat`, and detection bookkeeping
(`detected`, `first_detection_slot`). `length` property = `end − start + 1`.
Events are the unit for interception ratio and intercept delay.

### `RFEnvironment`

| Method | Purpose / theory |
| --- | --- |
| `__init__(config, prebuilt=None)` | Builds the band plan, allocates the `(T×B)` matrices (`occupancy`, `snr_db`, `power_db`, `threat`, `emitter_id_matrix`), then either `_load_prebuilt` (replay) or `_generate` (fresh). Sets `replayed`. |
| `_load_prebuilt(pb)` | Rehydrates the matrices + emitter list from a saved dataset and rebuilds the event list. Validates the array shape against the config. This is what makes a dataset a drop-in environment. |
| `_generate()` | 1) choose emitter count = `round(density·N)`; 2) sample each emitter's behaviour from `behavior_weights` (or the built-in mix); 3) assign a unique home band, an SNR in `[snr_min, snr_max]`, and a threat (priority emitters 0.75–1.0, other high-priority 0.6–0.85, rest 0.1–0.55); 4) `_paint_emitter` writes its activity; 5) derive `power_db = noise_floor + snr` where active (+ correlated ripple so an empty band is not perfectly flat); 6) `_extract_events`. |
| `_mark(emitter, band, t0, t1)` | Sets `occupancy` True over a slice and writes SNR/threat/emitter-id, keeping the **stronger** emitter where two overlap. |
| `_paint_emitter(emitter)` | Turns a behaviour into activity: `constant` = long on-blocks; `burst` = random short bursts with gaps; `periodic` = pulse every P from a random phase; `hopping` = park-then-step ±4 bands; `low_duty` = a handful of 1–2 slot events; `priority` = more frequent short intermittent events. Fills `emitter.params` and `emitter.duty_cycle`. |
| `_extract_events()` | Scans each band's occupancy column, collapses consecutive True runs into `EmitterEvent`s, tags each with the owning emitter's threat/priority (read at the run midpoint), sorts by `(start, band)`. |
| `is_active(t, band)` / `active_bands(t)` | Ground-truth queries used by the receiver and metrics. |
| `snr_at` / `power_at` / `threat_at` `(t, band)` | Scalar ground-truth lookups. |
| `events_started_by(t)` | Events whose `start ≤ t` — the interception-ratio denominator. |
| `band_threat_prior()` | Static per-band max threat over emitters' home bands. This is the *only* forward-looking hint a scheduler gets — it models a known ES threat library, not live truth. |
| `occupancy_percentage()` | Mean of the occupancy matrix; scenario sparsity. |

## II.4 `app/simulation/receiver.py` — receiver digital twin

**Theory:** implements the detection model of Part I.3. Uses its own RNG stream so
scheduler randomness never perturbs measurement noise.

| Symbol | Purpose |
| --- | --- |
| `_sigmoid(x)` | `1/(1+e^−x)`; the logistic detection curve. |
| `Receiver.__init__(config, rng)` | Stores config, RNG, and a fresh `ReceiverState`. |
| `reset(start_band=0)` | New `ReceiverState` pointed at `start_band`. |
| `tune(band)` | Points the receiver at `band`; if it changed, arms `retune_cooldown = retune_delay_slots` and returns `True` (a retune happened → −1 reward). |
| `_detection_prob(true_snr_db)` | `sigmoid((true_snr − threshold) / 2)` — P(detect) given SNR margin. |
| `observe(env, t, band)` | The measurement. Looks over the `scan_window` around `band`, takes the **strongest active** band in it. If active: draw `measured_snr = true_snr + N(0, σ)`, detect iff `rand < P(detect)` **and** `measured_snr ≥ threshold`. If inactive: draw a noise-only estimate and a false alarm with prob `false_alarm_prob`. Updates `visited_bands`, `detections`, `total_scans`, ages the retune cooldown, and returns a raw measurement dict. |

## II.5 `app/simulation/reward.py` — reward engine

| Symbol | Purpose / theory |
| --- | --- |
| Module constants | `HIGH_PRIORITY_THREAT = 0.7`; the reward values `R_HIGH_PRIORITY_DETECT = 10`, `R_NORMAL_DETECT = 5`, `R_CORRECT_INACTIVE = 1`, `R_EMPTY_SCAN = −2`, `R_FALSE_ALARM = −4`, `R_MISSED_ACTIVE = −6`, `R_MISSED_HIGH_PRIORITY = −10`, `R_RETUNE_COST = −1`. |
| `compute_reward(*, true_active, detected, false_alarm, threat, retuned, predicted_active, missed_active_bands=0, missed_high_priority_bands=0)` | Builds a `breakdown` dict of the components that apply this dwell, sums it. Detection → +10/+5 by threat; scanning an active band but missing → the missed-active penalty (you were in the right place and still lost it); false alarm → −4; a genuinely empty look → +1 if the scheduler predicted "idle", else −2; retune → −1; plus the aggregated global missed-opportunity penalty for every unscanned active band this slot. Returns `(reward, breakdown)`. |
| `RewardEngine` | Thin OO wrapper (`.evaluate(**kwargs)` → `compute_reward`) so the reward policy can be swapped/injected without touching the engine. |

## II.6 `app/metrics/tracker.py` — incremental metrics

**Theory:** an online accumulator so metrics are available every step without
re-scanning history. Denominators follow Part I.9.

| Method | Purpose |
| --- | --- |
| `MetricsTracker.__init__(env)` | Zeroes all counters; builds `_event_lookup` (band → list of that band's events) from `env.events` for O(1) event marking. |
| `record(*, t, scanned_band, true_active, detected, false_alarm, predicted_active, reward, env)` | One dwell: bump `steps`/`total_reward`; classify the scan as hit / miss / false-alarm / empty and update the matching counters and the `active_scans` / `inactive_scans` denominators; on a hit, `_mark_event_detected`; record the prediction if one was made; add this slot's unscanned-active-band count to `missed_opportunities`; log the visit slot for revisit-time. |
| `_mark_event_detected(band, t)` | Finds the (first, still-undetected) event on `band` spanning `t` and stamps `detected` + `first_detection_slot`. Ensures each event is counted once. |
| `snapshot(up_to_t)` | Computes the full `SchedulerMetrics` from the counters: `pod = hits/active_scans`, `far = false_alarms/inactive_scans`, `interception = detected_events/events_started`, `avg_delay = mean(first_detection − start)`, `hp_rate = hp_detected/hp_events`, `coverage = |visited|/N`, `avg_revisit = mean(consecutive-visit gaps)`, `correct_pct = 100·correct/predictions`, `avg_reward = total/steps`. Guards every divide-by-zero; rounds to 4 dp. |

## II.7 `app/schedulers/` — the policies

### `base.py`

| Symbol | Purpose |
| --- | --- |
| `BaseScheduler` (ABC) | Interface. `__init__(num_bands, rng, params)`. Abstract `decide(context) → ScanDecision`. `update(feedback)` (no-op by default — baselines don't learn). `reset()` clears learned state. `_decision(**kwargs)` is a helper that builds a validated `ScanDecision`, clamping confidence to [0,1] and truncating reasons/alternatives to 3. |

### `baseline.py`

| Symbol | Purpose / theory |
| --- | --- |
| `RoundRobinScheduler` | `decide` returns the next band in `0,1,…,N−1,0,…`; advances a cursor. The open-loop reference (Part I.2). |
| `RandomScheduler` | `decide` returns `rng.integers(0, N)`. Memoryless open-loop reference. |

### `smart.py`

| Symbol | Purpose / theory |
| --- | --- |
| `_confidence(scores, idx)` | Min-max position of the chosen score within the score vector → a 0–1 "how clear was this choice". |
| `_reward_to_unit(reward)` | `clip((reward + 10)/20, 0, 1)` — squashes the spec reward into a bounded payoff so ε-greedy/UCB value estimates stay in [0,1] (UCB1's confidence bound assumes bounded rewards). |
| `PriorityScoreScheduler` | Part I.8. `_periodicity_bonus(band, since)` computes the Gaussian phase bonus. `decide` builds six normalised feature vectors, weights them (`params["weights"]` overridable), adds tiny tie-break noise, scans the argmax, and reports the top-3 weighted contributions as `reasons`. `update` feeds detections into the per-band hit-slot history and re-estimates the period from the **median gap** when the gaps are consistent. |
| `_BanditBase` | Shared arm bookkeeping: `values` (mean payoff), `counts`, `hit_est` (running hit rate, used for `predicted_active`). `update` does the incremental-mean value update and hit-rate update. |
| `EpsilonGreedyBanditScheduler` | `decide`: with prob `epsilon` scan a random band (explore), else `argmax(values)` (exploit). `update` also decays `epsilon` toward `epsilon_min` if `epsilon_decay < 1`. |
| `UCB1BanditScheduler` | `decide`: if any arm is unpulled, scan it (infinite bonus); else scan `argmax(values + c·√(ln t / counts))`. `_total` is the running pull count `t`. No ε parameter — exploration is built into the bonus. |
| `ThompsonSamplingScheduler` | Beta-Bernoulli. `decide`: draw `θ_b ~ Beta(α_b, β_b)` for every band, scan `argmax θ`. `update`: `α += 1` on a hit, `β += 1` otherwise, `β += 1` again on a false alarm (penalise noisy bands). |

### `qlearning.py`

| Symbol | Purpose / theory |
| --- | --- |
| `QLearningScheduler` | Part I.7. `q` is `dict[state_tuple → np.ndarray(N)]` (lazily created rows). |
| `_row(state)` | Get-or-create the Q-row for a state, initialised to `optimistic_init`. |
| `_encode(context)` | Discretises the context into the 5-tuple state: current-band bucket (`cb·band_buckets//N`), recent-hit bucket (0–3 from the last-8 hit count), time-since-last-visit bucket (0–3), threat bucket (0–3 from the band's threat prior), and `time % periodic_window` bucketed into 4. |
| `decide(context)` | First applies the **deferred TD update** for the previous `(s,a)` now that `s'` is known: `Q[s,a] += α·(r + γ·max Q[s'] − Q[s,a])`. Then ε-greedy action selection, ε decay, and an explainability payload (state tuple, Q-value, exploration flag, top Q actions as alternatives). |
| `update(feedback)` | Stashes `feedback.reward` as the pending TD reward and pushes the hit/no-hit into the recent-hits deque. |
| `end_episode()` | Terminal update with **no bootstrap** (`Q[s,a] += α·(r − Q[s,a])`), then clears the trajectory. Called between training episodes so the Q-table carries over but the per-episode state does not. |
| `_softmax_confidence(row, idx)` | Softmax probability of the chosen action across the Q-row → confidence. |

### `registry.py`

| Symbol | Purpose |
| --- | --- |
| `SCHEDULER_REGISTRY` | `name → class` for all seven schedulers. |
| `LEARNING_SCHEDULERS` | The subset worth training over episodes (everything except the two baselines). |
| `list_schedulers()` | Registry keys, for the UI dropdown. |
| `create_scheduler(name, num_bands, rng, params)` | Factory; raises `KeyError` with the valid list on a bad name. |

## II.8 `app/simulation/engine.py` — the step loop

| Symbol | Purpose |
| --- | --- |
| `SchedulerContext` (dataclass) | **Exactly** what a scheduler may see: `time_slot`, `num_bands`, `current_band`, `retune_delay`, and the per-band arrays `visit_counts`, `hit_counts`, `miss_counts`, `false_alarm_counts`, `last_visit_slot` (−1 = never), `predicted_activity` (running EMA), `band_threat_prior` (static), plus `recent_reward` and `last_feedback`. No ground-truth matrices. |
| `ScanFeedback` (dataclass) | What the scheduler gets back after a dwell: band, `true_active`, `detected`, `false_alarm`, `reward`, `reward_breakdown`, `predicted_active`. |
| `Simulation.__init__(env_config, receiver_config, scheduler_name, scheduler_params=None, scheduler_instance=None, env_instance=None)` | Wires env + receiver + scheduler + `MetricsTracker`. Independent RNG streams: env from `seed`, receiver from `seed+101`, scheduler from `seed+202`. `scheduler_instance` lets training reuse one learner across episodes; `env_instance` lets a dataset replay stand in for generation. Allocates the running per-band arrays that back the `SchedulerContext`. |
| `max_slots` | `env.num_time_slots`. |
| `_context()` | Snapshots the running arrays into a `SchedulerContext`. |
| `step()` | One dwell: `scheduler.decide(context)` → clamp band → `receiver.tune` (retune?) → `receiver.observe` → count this slot's unscanned active/high-priority bands → `compute_reward` → update running arrays (`visit_counts`, `hit/miss/fa`, `last_visit_slot`, `predicted_activity` EMA with α=0.2) → `scheduler.update(feedback)` → `metrics.record` → build `DetectionEvent` + `SimulationStepResult` (with a metrics snapshot) → advance `t` by `dwell_slots` → append to `history`. |
| `run(steps)` | Calls `step()` up to `steps` times or until `done`. |
| `metrics_snapshot()` | `metrics.snapshot(up_to_t = last history time_slot)`. |

## II.9 `app/simulation/presets.py` — scenario presets

| Symbol | Purpose |
| --- | --- |
| `_PRESETS` | Six entries, each `{description, environment: RFEnvironmentConfig, receiver: ReceiverConfig}`. The descriptions state what the scenario stresses and which scheduler family it favours. `behavior_weights` is what makes e.g. "Frequency Hopping Challenge" actually hopping-dominated. |
| `list_presets()` | All presets as JSON dicts (for `GET /api/presets` and the sidebar). |
| `get_preset(name)` | Returns **deep copies** of `(RFEnvironmentConfig, ReceiverConfig)` so callers can mutate freely; `KeyError` on unknown name. |
| `preset_names()` | Just the names. |

## II.10 `app/dataset/` — DeepSense-style datasets

### `generator.py`

| Symbol | Purpose |
| --- | --- |
| `BEHAVIOR_LABELS` | `behavior name → int code` (stable) for the label matrix; −1 = idle cell. |
| `_label_matrix(env)` | Per-(t, band) emitter-behaviour code, read via `emitter_id_matrix`. The supervised-classification target. |
| `build_dataset(config, name=None)` | Generates an `RFEnvironment`, packs `occupancy / power_db / snr_db / threat / labels / emitter_id` arrays, computes `DatasetStats`, and returns `(DatasetMeta, arrays)`. `dataset_id` is `ds_<UTC-timestamp>_<seed>`. |

### `stats.py`

| Symbol | Purpose |
| --- | --- |
| `compute_stats(occupancy, snr_db, threat, emitters)` | `occupancy_percentage`, `active_band_count` (bands ever active), `active_time_count` (slots ever active), `emitter_type_distribution`, `average_snr_db` (over active cells), `threat_distribution` (low/med/high buckets over emitters), `sparsity_score = 1 − occupancy_fraction`. |

### `store.py`

| Symbol | Purpose |
| --- | --- |
| `DatasetStore.__init__(root=None)` | Roots at `backend/data/datasets/` (creates it). Lock-guarded. |
| `_dir(dataset_id)` | Safe path resolution — rejects an id that escapes the store root. |
| `save(meta, arrays)` | Writes each array as `.npy` (canonical) and, for the human-readable ones, `.csv`; writes `meta.json` with the file map; returns the updated `meta`. |
| `list()` | Every `*/meta.json` parsed back to `DatasetMeta`, newest first; skips corrupt entries. |
| `get(id)` / `load_arrays(id)` | Metadata / all NPY arrays for one dataset; `KeyError` if missing. |
| `delete(id)` | `rmtree` the dataset dir (used by tests and manual cleanup). |
| `build_replay_env(id)` | Rehydrates a dataset into an `RFEnvironment(config, prebuilt=…)` — the bridge from stored data back to a runnable scenario. |
| `config_for(id)` | The dataset's `RFEnvironmentConfig`. |
| `preview(id, max_rows=140, max_cols=96)` | **Block-reduces** the occupancy (max-pool) and power (mean-pool) matrices to a small grid for the Dataset Lab thumbnail heatmap. Uses ceil-division so the output never exceeds the cap. |
| `get_store()` | Process-wide singleton. |

## II.11 `app/comparison/` — strategy comparison

### `engine.py`

| Symbol | Purpose |
| --- | --- |
| `SCORE_WEIGHTS` | The weighting of Part I.10. |
| `_minmax(values)` | Min-max normalise a list to [0,1]; returns all-0.5 if the range is ~0 (degenerate — all strategies equal). |
| `_sample_series(history, n_points)` | Down-samples per-step metric snapshots to ~`n_points` evenly spaced points → `ComparisonSeries` (time, avg reward, detection rate, interception, coverage) for the line charts. |
| `compare_strategies(env_config, receiver_config, schedulers, steps, *, series_points=60, scheduler_params=None, env_factory=None, replayed_dataset=None)` | For each scheduler: build a fresh `Simulation` (same seed, or `env_factory()` for a replayed dataset), run `steps`, snapshot metrics + series. Then min-max normalise the metric columns, compute each strategy's weighted score, rank, and assemble a `ComparisonReport` (entries, `metrics_table`, `winner`, `ranking`, `score_weights`). Nothing is hardcoded per strategy — the only difference is the policy. |
| `col(attr)` (inner) | Pull one metric across all strategies for normalisation. |

### `export.py`

| Symbol | Purpose |
| --- | --- |
| `report_to_csv(report)` | The `metrics_table` as CSV (fixed column order). |
| `report_to_html(report)` | A standalone dark-themed HTML table with the winner highlighted; opened via the "↗ html" links. |

## II.12 `app/reporting.py` — run report rendering

| Symbol | Purpose |
| --- | --- |
| `_flatten(report)` | Turns the nested run-report dict into ordered `(key, value)` rows (config + every metric). |
| `run_report_to_csv(report)` | Two-column `key,value` CSV. |
| `run_report_to_html(report)` | Dark HTML: the flattened table plus a "recent decisions" table. |

## II.13 `app/api/manager.py` — the stateful core

`SimulationManager` is a **process-wide singleton** (`get_manager()`), lock-guarded
(`threading.RLock`), holding the single active `Simulation` plus dataset/preset
context and cached comparison/training results. This is where "the simulation" as
a user concept lives.

| Method | Purpose |
| --- | --- |
| `__init__` | Default configs, no dataset/preset, then `reset(ResetRequest())`. |
| `presets()` | `list_presets()`. |
| `sim` (property) | The active `Simulation` (rebuilds via `reset` if somehow absent). |
| `reset(req)` | Rebuild the `Simulation`. Precedence: `preset` sets the base env+receiver and records `_preset_name`; an explicit `environment` overrides it and clears replay mode; `receiver` overrides the receiver; `scheduler`/`scheduler_params` set the policy. If a dataset is loaded, the env is rebuilt from it (`build_replay_env`). Returns `state()`. |
| `generate_dataset(req)` | `build_dataset` from `req.config` → `req.preset` → current env, then `store.save`. |
| `list_datasets` / `get_dataset` / `dataset_stats` | Pass-throughs to the store. |
| `load_dataset(id, req)` | Switch to **replay mode**: `_dataset_id = id`, adopt the dataset's config, rebuild the `Simulation` with the replay env. Subsequent `reset`/`run` stay in replay until an explicit `environment` is posted. |
| `run_comparison(req)` | Validate scheduler names; build the env factory (replay-aware) and the shared seed (`req.seed` overrides); call `compare_strategies`; cache and return the report. |
| `last_comparison()` | The cached `ComparisonReport` (or `None`). |
| `step(count=1)` | Advance `count` dwells; return `state()` plus `last_step` and `steps_executed`. |
| `run(steps, scheduler, params, reset)` | Optionally `reset` first (preserving preset/replay because it passes **no** `environment`), then `sim.run(steps)`; returns `state()` + `metrics` + `last_step`. Refuses a mid-run scheduler switch without reset. |
| `train(req)` | Multi-episode training. One persisted scheduler instance; per episode a fresh `Simulation` (seed varied by `ep·7919` if `vary_seed`) reusing that instance, `sim.run(steps_per_episode)`, then `scheduler.end_episode()`. Collects an `EpisodeResult` per episode (reward, P(det), interception, hp-rate, missed, `epsilon`, `q_states`, `q_updates`), rolls up first/last/improvement/best-episode into a `TrainingReport`, stores the last 25. |
| `training_runs()` / `last_training()` | The stored `TrainingReport`s (newest first) / the latest. |
| `explainability_log(limit=200)` | The last `limit` `SimulationStepResult`s reduced to decision rows: `time_slot`, `scheduler`, `selected_band`, `confidence`, `predicted_active`, `reward`, `outcome` (hit/miss/false_alarm/empty), `reasons`, `alternatives`, `explanation`, `reward_breakdown`. |
| `run_report()` | A snapshot dict: product/mode/timestamp, scheduler, dataset/preset, env + receiver config, `time_slot`/`max_slots`/`steps_run`, final `metrics`, and the last 10 decisions. |
| `state()` | The big frontend payload — see below. |
| `_utc_now()` / `_round_list()` | Timestamp / list-rounding helpers. |
| `get_manager()` | Double-checked-locked singleton accessor. |

**`state()` returns:** product/mode/running/done, `time_slot`/`max_slots`,
`scheduler` + `available_schedulers`, `dataset_id` + `preset` + `replay_mode`,
`environment` summary (bands, slots, noise, seed, density, occupancy %, emitter
count), `receiver` summary, the full `emitters` and `bands` lists, `spectrum`
(current per-band `power_db`, `active` mask, `threshold_db`, `threat_prior`,
`predicted_activity`), `waterfall` (last 160 slots of `power_db` + `active` +
`start_slot`), `scan_path` (last 240 decisions), `reward_series`, and the current
`metrics`.

## II.14 `app/api/routes.py` — HTTP surface

Thin handlers: validate the body, call the manager, translate `KeyError`/
`ValueError`/`RuntimeError` into `400`/`404`/`409`. Full list in Part IV.

---

# Part III — Frontend reference

`frontend/src/`. React 18 + TypeScript + Vite + Tailwind. No chart library.

## III.1 `main.tsx`
Mounts `<App/>` into `#root` in `React.StrictMode`; imports `index.css` (Tailwind
layers + the `loadbar` keyframe).

## III.2 `api.ts` — typed client

| Symbol | Purpose |
| --- | --- |
| `jget<T>` / `jpost<T>` | `fetch` wrappers that throw `"<path> -> <status> <body>"` on non-2xx. `BASE` comes from `VITE_API_BASE` (empty in dev — the Vite proxy handles `/api`). |
| Interfaces | `Health`, `Metrics`, `Emitter`, `EnvironmentConfig`, `ReceiverConfig`, `DecisionPayload`, `StepResult`, `ScanPathRow`, `SimState`, `DatasetMeta`, `DatasetStats`, `ComparisonEntry`, `ComparisonReport`, `EpisodeResult`, `TrainingReport`, `ExplainRow`, `RunReport`, `ResetBody`, `Preset` — mirror the backend models. |
| `api` object | `health`, `state`, `schedulers`, `presets`, `reset(body)`, `step(count)`, `run(steps, scheduler?, reset?)`, `train(scheduler, episodes, steps)`, `trainingRuns`, `datasetGenerate(name?, config?)`, `datasetList`, `datasetGet(id)`, `datasetPreview(id)`, `datasetLoad(id, scheduler?)`, `comparisonRun(schedulers, steps, seed?)`, `comparisonLast`, `comparisonExportUrl(fmt)`, `explainabilityLog(limit)`, `runReport`, `runReportExportUrl(fmt)`. |
| `ALL_SCHEDULERS` | Ordered name list for the comparison toggles. |

## III.3 `useSim.ts` — central simulation hook

| Symbol | Purpose / theory |
| --- | --- |
| `SimControls` | The hook's return contract: `state`, `connected`, `busy`, `error`, `playing`, `speed`/`setSpeed`, `play`/`pause`, `reset(body)`, `stepOnce()`, `runN(n)`, `refresh()`. |
| `useSim()` | Owns the live `SimState`. `call(fn)` wraps any mutating API call with busy/error/connected handling. `refresh()` re-GETs `/api/state`. The **play loop** is a `setInterval(TICK_MS=700)` that calls `api.step(round(speed))` each tick, stops on `done` or error, and uses an `inflight` guard so ticks never overlap (back-pressure). `speedRef` lets the running interval read the latest slider value without restarting. This is a **polling loop**, not a stream — simple and robust on localhost. |

## III.4 `ui.tsx` — design-system primitives

| Component | Purpose |
| --- | --- |
| `Panel({title, right, children})` | The bordered card used everywhere; scrollable body, optional header-right slot. |
| `Btn({onClick, disabled, active, title})` | Compact button; `active` = accent outline. |
| `Stat({label, value, hint, tone})` | A metric tile; `tone` ∈ good/bad/warn/scan colours the value. |
| `Field({label, value, onChange, step, min, max})` | Labelled numeric input (config fields). |
| `Select({label, value, options, onChange})` | Labelled `<select>`. |
| `Empty({children})` | Centred muted placeholder. |
| `Spinner` / `Loading` | Inline / centred loading indicator. |
| `LoadingBar({visible})` | The 2px indeterminate bar under the header (`loadbar` keyframe) shown while `sim.busy`. |
| `ErrorBanner({message, onRetry})` | Consistent red error strip with an optional retry action. |
| `Badge({tone})` / `OutcomeTag({outcome})` | Small status chips; `OutcomeTag` maps hit/miss/false_alarm/empty → colour. |

## III.5 `charts.tsx` — hand-built responsive charts

**Theory:** the spectrum and waterfall need custom overlays (scanned-band
highlight, hit/miss/FA scan-path markers) that no off-the-shelf chart provides, so
everything is drawn directly. SVG `viewBox` + `preserveAspectRatio="none"` gives
fluid width; `vectorEffect="non-scaling-stroke"` keeps strokes 1px and text is
rendered as HTML so it never stretches. The waterfall uses `<canvas>` because it
paints up to 160×96 cells every frame.

| Symbol | Purpose |
| --- | --- |
| `SERIES_COLORS` | The categorical palette for multi-series charts / comparison rows. |
| `SpectrumChart({power, active, threshold, currentBand, height})` | Per-band power bars: blue = currently scanned, green = active, grey = idle; amber dashed threshold line; faint column highlight on the scanned band. |
| `Waterfall({power, startSlot, scanPath, height})` | Canvas heatmap, dark→bright by normalised power, with the scan path painted over it: teal = hit, amber = miss (active, not detected), red = false alarm, faint blue = empty. Row index = `time_slot − startSlot`. |
| `LineChart({series, height, yFormat, zeroBaseline})` | Multi-series line chart: HTML y-axis labels beside a stretched SVG, 5 grid lines, optional zero baseline, per-series legend. Used for the reward timeline, comparison reward/detection curves, training curve. |
| `BarChart({data, height, valueFormat})` | Vertical bars for one metric across categories (comparison: interception / avg reward per scheduler). |
| `Sparkline({points, color, height})` | Tiny inline trend line. |

## III.6 `ControlSidebar.tsx`

The persistent left panel, present on every tab. Local form state mirrors the
live config and is re-synced whenever the server-side config changes (preset
applied, dataset loaded, apply & reset). Sections:

- **Transport** — play/pause (toggles the `useSim` loop), step, +100, +500, a
  **speed** slider (steps per 700 ms tick), and status chips (t, replay, active
  preset, done).
- **Scheduler** — the `<select>` (options from `state.available_schedulers`).
- **Scenario presets** — fetched from `GET /api/presets`; each button applies the
  preset via `sim.reset({preset})`, shows its description as a tooltip and (when
  active) below the list.
- **Environment / Receiver** — the numeric config fields.
- **apply & reset** posts the assembled `environment` + `receiver` + `scheduler`;
  **refresh** re-GETs state. An `ErrorBanner` shows `sim.error`.

## III.7 `App.tsx`

The shell: product wordmark, a 6-item tab nav, the `LoadingBar`, a flex row of
`<ControlSidebar/>` + the active view, and a status bar (env summary, active
scenario, `t / max`, scheduler, replay flag, busy/playing, the safety string).
`tab` state selects which view renders.

## III.8 `views/` — the six tabs

| View | What it shows / does |
| --- | --- |
| `LiveMonitor.tsx` | The main grid. `SpectrumChart` + `Waterfall` (centre), a 10-tile live **Metrics** panel + an **Active decision** card (`DecisionCard`: confidence, predicted-active, reward, explanation, reasons, alternatives, breakdown), and an `EventLog` + reward `LineChart` (bottom). Falls back to `Loading`/`ErrorBanner` until `state` arrives. |
| `StrategyComparison.tsx` | Scheduler toggle buttons + a steps field + **run comparison** → `api.comparisonRun`. Renders the ranked `metrics_table` (winner highlighted, colour-keyed), `BarChart`s for interception ratio and average reward, and `LineChart`s for reward-over-time and detection-rate-over-time, plus CSV/JSON/HTML export links and the score-weight formula. |
| `DatasetLab.tsx` | Left: a generate form (name, bands, slots, density, seed) → `api.datasetGenerate`, and the dataset list. Right: for the selected dataset, stat tiles, the emitter-type mix as badges, a **preview heatmap** (`Waterfall` fed by `api.datasetPreview`), and **load into simulation** (`api.datasetLoad` → replay mode). `Kv` is a small key/value tile. |
| `TrainingRuns.tsx` | A train form (learner, episodes, steps/episode) → `api.train`; a run-history list; and for the selected run, roll-up badges, the per-episode `LineChart` (avg reward + P(det)×10), and the full episode table (seed, avg R, P(det), interception, hi-pri, missed, epsilon, Q-states, Q-updates), best episode highlighted. |
| `ExplainabilityLog.tsx` | Auto-refreshing (1.5 s) table of every decision from `api.explainabilityLog` with an outcome filter (all/hit/miss/false_alarm/empty). Each row: t, scheduler, band, confidence, prediction, outcome tag, reward, explanation + reason chips + alternatives. |
| `Reports.tsx` | The current **run report** (`api.runReport`) as a badge strip + metric grid + recent-decisions table with CSV/JSON/HTML export, and the **last strategy comparison** (`api.comparisonLast`) as a compact ranked table with its own export links. |

---

# Part IV — HTTP API reference

Base path `/api`. Interactive docs at `/docs`.

| Method & path | Body | Returns |
| --- | --- | --- |
| `GET /health` | — | `{status, product, mode, transmit_capability:false}` |
| `GET /schedulers` | — | `{schedulers[], learning_schedulers[]}` |
| `GET /presets` | — | `{presets: [{name, description, environment, receiver}]}` |
| `GET /state` | — | the full `state()` payload (Part II.13) |
| `POST /simulation/reset` | `ResetRequest` (`preset?`, `environment?`, `receiver?`, `scheduler?`, `scheduler_params?`) | new `state()` |
| `POST /simulation/step` | `StepRequest` (`count` 1–2000) | `state()` + `last_step` + `steps_executed` |
| `POST /simulation/run` | `RunRequest` (`steps`, `scheduler?`, `scheduler_params?`, `reset`) | `state()` + `metrics` + `last_step` + `steps_executed` |
| `POST /simulation/train` | `TrainRequest` (`scheduler`, `episodes`, `steps_per_episode`, `scheduler_params?`, `vary_seed`) | `TrainingReport` |
| `POST /dataset/generate` | `DatasetGenerateRequest` (`name?`, `preset?`, `config?`) | `DatasetMeta` |
| `GET /dataset/list` | — | `{datasets: DatasetMeta[]}` |
| `GET /dataset/{id}` | — | `DatasetMeta` (404 if missing) |
| `GET /dataset/{id}/stats` | — | `DatasetStats` |
| `GET /dataset/{id}/preview` | — | down-sampled `{occupancy[][], power_db[][], bands, time_slots}` |
| `POST /dataset/{id}/load` | `DatasetLoadRequest` (`receiver?`, `scheduler?`, `scheduler_params?`) | `state()` in replay mode |
| `POST /comparison/run` | `ComparisonRequest` (`schedulers[]`, `steps`, `seed?`, `scheduler_params?`, `series_points`) | `ComparisonReport` |
| `GET /comparison/last` | — | the cached `ComparisonReport` (404 if none) |
| `GET /comparison/export/{json\|csv\|html}` | — | file download / HTML page |
| `GET /explainability/log?limit=` | — | `{log: ExplainRow[]}` |
| `GET /training/runs` | — | `{runs: TrainingReport[]}` (newest first) |
| `GET /training/last` | — | latest `TrainingReport` (404 if none) |
| `GET /report/run` | — | the run-report dict |
| `GET /report/run/export/{json\|csv\|html}` | — | file download / HTML page |

Error mapping: unknown scheduler/preset/dataset → `400`/`404`; stepping a
finished simulation → `409`; bad export format → `400`.

---

# Part V — End-to-end data flow

## V.1 One `POST /api/simulation/step`

```
routes.simulation_step
  └─ manager.step(count)
       └─ Simulation.step()                          ×count
            ├─ scheduler.decide(_context())      → ScanDecision (+explainability)
            ├─ receiver.tune(band)               → retuned?  (arms cooldown, −1)
            ├─ receiver.observe(env, t, band)    → measurement (SNR, detect, FA)
            ├─ count unscanned active bands at t (missed-opportunity context)
            ├─ compute_reward(...)               → reward, breakdown
            ├─ update running arrays  (visit/hit/miss/fa/last_visit/pred_activity)
            ├─ scheduler.update(ScanFeedback)    → learning step
            ├─ metrics.record(...)               → counters + event marking
            └─ build SimulationStepResult (with metrics.snapshot)
  └─ manager.state()  +  last_step  →  JSON
```

The frontend `useSim` play loop calls this every 700 ms with `count = speed`,
and every view re-renders from the returned `SimState`.

## V.2 A strategy comparison

```
StrategyComparison → api.comparisonRun(schedulers, steps, seed?)
  └─ routes.comparison_run → manager.run_comparison
       └─ compare_strategies(env_config, receiver_config, schedulers, steps, ...)
            for each scheduler:
              Simulation(same seed / same replay env).run(steps)
              → metrics snapshot + down-sampled series
            min-max normalise metric columns → weighted score → rank
       → ComparisonReport  (cached for /comparison/last and the exports)
```

## V.3 Dataset generate → replay

```
DatasetLab → api.datasetGenerate → manager.generate_dataset
  └─ build_dataset(config)                    (RFEnvironment + label matrix + stats)
  └─ DatasetStore.save                        (meta.json + *.npy + *.csv)

DatasetLab → api.datasetLoad(id) → manager.load_dataset
  └─ DatasetStore.build_replay_env(id)        (RFEnvironment(config, prebuilt=arrays))
  └─ Simulation(env_instance = replay env)    (replay_mode = true)
```

## V.4 Q-learning training

```
TrainingRuns → api.train(scheduler, episodes, steps) → manager.train
  scheduler = create_scheduler(...)           (one instance, persisted)
  for ep in episodes:
      env_cfg.seed = base_seed + ep·7919      (if vary_seed)
      Simulation(env_cfg, scheduler_instance = scheduler).run(steps)
      scheduler.end_episode()                 (flush terminal TD update, clear trajectory)
      record EpisodeResult
  → TrainingReport (first/last/improvement/best) ; stored (last 25)
```

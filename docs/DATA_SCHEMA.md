# SPECTRA-SCAN AI — Data Schema

`schema_version` on every persisted record. Current: **1**.

Sessions are stored under `<data_dir>/sessions/<session_id>/`:

| file | contents |
| --- | --- |
| `meta.json` | session metadata (below) |
| `<kind>.parquet` **or** `<kind>.jsonl.gz` | one row per record; Parquet when `pyarrow` is installed, gzip-JSONL otherwise |

A session export (`GET /api/sessions/{id}/export`) is a ZIP of all of the above
plus `manifest.json` (per-file SHA-256) and a copy of this document. Import
verifies every checksum and rejects a `schema_version` mismatch.

Units: dB / dBm as noted; frequencies in Hz; positions in km on a local plane;
time in integer **slots** (one receiver dwell) unless a field says `*_ts`
(Unix seconds) or `*_at` (ISO-8601 UTC).

---

## `meta.json`

| field | type | notes |
| --- | --- | --- |
| `session_id` | string | `sess_<hex12>` |
| `name` | string | operator label |
| `tags` | string[] | free-form |
| `schema_version` | int | = 1 |
| `started_at` / `finished_at` | ISO-8601 UTC | |
| `mode` | string | `simulation` \| `live_es` at start |
| `scenario` | string | loaded scenario / preset name, if any |
| `scheduler` | string | active scheduler at start |
| `row_counts` | object | `{kind: int}` |
| `format` | string | `parquet` \| `jsonl.gz` |

## `decisions.*` — one row per receiver dwell

| field | type | notes |
| --- | --- | --- |
| `schema_version` | int | 1 |
| `time_slot` | int | dwell index |
| `scheduler` | string | may differ from session start if the online guardrail reverted |
| `selected_band` | int | 0-based band index (post protected-band override) |
| `detected` | bool | a real signal was detected this dwell |
| `false_alarm` | bool | reported signal where none was truly present (or was deceived by a synthetic EW effect) |
| `reward` | float | ground-truth reward (`simulation`) or proxy reward semantics (`live_es`) |

## `metrics.*` — one row per `step` / `run` batch

`time_slot` (int) + the full `SchedulerMetrics` snapshot at that point:
`steps, total_reward, average_reward, hits, misses, false_alarms, empty_scans,
probability_of_detection, false_alarm_rate, interception_ratio,
average_intercept_delay, high_priority_detection_rate, missed_opportunity_count,
scan_coverage, average_revisit_time, correct_prediction_percentage,
emitter_events_total, emitter_events_detected` — all floats/ints, ratios in
`[0,1]`, `*_db` in dB. `schema_version` = 1.

## `alerts.*`

`alert_id, ts, rule_kind, severity (info|warn|critical), track_id?, band?,
detail, state (open|ack|closed), schema_version`.

## `tracks.*`

`track_id, first_seen, last_seen, bands[], primary_band, class,
class_confidence, modulation, pri_estimate, pri_jitter, duty_cycle,
snr_mean_db, threat, is_synthetic_effect, schema_version`.

## `df_fixes.*`

`track_id, time_slot, est_x_km, est_y_km, true_x_km?, true_y_km?,
ellipse_a_km, ellipse_b_km, ellipse_theta_deg, cep_km, error_km?, n_nodes,
method, solvable, schema_version`. `true_*` / `error_km` are present only for
`simulation` sessions.

---

## Related on-disk stores (not part of a session export)

| path | format | notes |
| --- | --- | --- |
| `platform.db` | SQLite | users, audit, session index, library entries + revisions |
| `audit/<date>.jsonl` | JSONL | append-only mirror of the audit table |
| `recordings/<id>/frames.jsonl` + `meta.json` | JSONL | receive-only sweep captures (`SweepFrame` per line) |
| `scenarios/<id>.json` | JSON | `Scenario` documents |
| `sim2real/<id>.json` | JSON | `CalibrationProfile` documents |
| `rl/<job_id>/checkpoint.json` \| `.pt` | JSON / torch | trained scheduler state |

## Versioning / migration

`schema_version` is bumped on any breaking change to a row shape. Readers must
reject a version they do not understand (import does). Additive fields do not
bump the version; consumers ignore unknown keys.

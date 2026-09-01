# SPECTRA-SCAN AI — Security & Air-Gap Posture

## 1. Threat model / scope

SPECTRA-SCAN AI is a **receive-only, air-gapped** analysis platform. It is *not*
internet-facing and holds no real signal data. The security surface that matters:

- unauthenticated access to simulation/analysis functions,
- privilege escalation between roles,
- tampering with persisted sessions / evidence,
- accidental egress from a facility network,
- accidental introduction of a transmit path.

Out of scope: multi-tenant isolation, DDoS resistance, and anything requiring an
outbound connection (there are none).

## 2. Authentication

- **Local users only**, in `backend/data/platform.db` (SQLite), created on first
  boot. No external IdP, no network calls.
- Passwords hashed with **Argon2** (bcrypt fallback). First-login
  password-change flag on the seeded non-demo accounts, enforced for
  `operator`+ actions.
- Sessions are **signed JWT** (HS256, key from `SPECTRA_JWT_KEY`), 12 h expiry
  (`SPECTRA_TOKEN_TTL_HOURS`). Endpoints: `POST /api/auth/login`, `/logout`,
  `GET /api/auth/me`, `POST /api/auth/change-password`.
- `POST /api/auth/demo` issues a read-only `viewer` token with a `demo: true`
  claim — no credentials, rate-limited. Backs the login **Skip** button.
- `POST /api/auth/quick-login {role}` issues a real token for the seeded account
  whose username == role. **Refused in production** and when seeds are off.
- The token is parsed **only from the `Authorization: Bearer` header** (and the
  `/ws?token=` query param for the WebSocket). No cookies.

## 3. Authorization (RBAC)

Roles, ascending: `viewer` < `analyst` < `operator` < `admin`.

| Capability | Min role |
| --- | --- |
| Read anything; run the simulation | `viewer` |
| Ack / close alerts | `analyst` |
| Hardware start/stop/config, mode switch, scenario/library/tasking edits, protected bands, RL training, sessions start/finish/import, online learning | `operator` |
| User management, audit export | `admin` |

- Enforced by `require_role(min_role, allow_demo=…)` dependencies. `allow_demo=False`
  additionally blocks the demo session even when its nominal `viewer` rank would
  pass (all hardware / config / user / library / scenario mutations).
- The only unauthenticated endpoints are `GET /api/health` and the auth
  endpoints themselves.

## 4. Audit

- `audit(actor, action, target, detail, mode, role)` → append-only SQLite table
  **and** a daily JSONL mirror under `backend/data/audit/`.
- Audited: login/logout, mode switches, hardware start/stop, config changes,
  scenario / library / tasking edits, protected-band overrides, exports
  (incl. evidence pack), RL promote, online-guardrail reverts, session
  import/finish, user changes.
- `GET /api/audit` (operator+) — filter by actor/action, paginated, CSV/JSONL
  export. **No update or delete route exists.**

## 5. Transport & headers

- **TLS** via `SPECTRA_TLS_CERT` / `SPECTRA_TLS_KEY` (passed to uvicorn
  `--ssl-certfile` / `--ssl-keyfile`). Required in production.
- **Rate limiting** — per-IP sliding window, `SPECTRA_RATE_LIMIT_RPM` (default
  600); `429` on exceed. The test client is exempt.
- **Security headers** on every response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Content-Security-Policy: default-src 'self'; connect-src 'self' ws: wss:`.
- **CORS** locked to `SPECTRA_CORS_ORIGINS` (default `http://localhost:5173` for
  dev only).
- Token redaction in logs.

## 6. Data at rest

- `platform.db` and the audit JSONL may be encrypted at rest with
  `SPECTRA_DB_ENCRYPTION_KEY` (from config or an OS keyring). Optional; off by
  default in dev.
- Session data (`data/sessions/<id>/`) is plain Parquet/JSONL; protect it with
  filesystem permissions. Exports are integrity-protected (SHA-256 manifest), not
  encrypted — encrypt the `.zip` out-of-band if it leaves the facility.
- Retention / rotation: `SPECTRA_RETENTION_DAYS` (default 30).

## 7. Air-gap posture

- **No outbound network capability** anywhere in the product: no CDNs, no
  telemetry, no license checks, no remote model/tile downloads. Frontend deps are
  vendored; fonts and map tiles are bundled or have an offline fallback.
- `python -m scripts.preflight` monkeypatches `socket.connect`, runs a full smoke
  (boot, sim, dataset, comparison, sessions, report) and asserts
  **`0 outbound connections`**. `test_ext_step7.py` runs it in CI.
- `deploy/spectra.service` sets `IPAddressDeny=any`; `docker-compose.yml` puts
  the service on an internal network with no egress.

## 8. Receive-only / no-transmit enforcement

- `GET /api/health` → `transmit_capability: false`, `hardware_mode: "receive_only"`.
- `HardwareAdapter` (base class) has **no** `transmit` / `tx` / `start_tx`
  attribute. `test_ext_step2*.py` asserts this and greps
  `backend/app/hardware/` for `hackrf_transfer`, `writeStream`, TX SoapySDR/UHD
  calls, IQ playback — the test **fails if any appear**.
- `hackrf_sweep_adapter.py` spawns `hackrf_sweep` only, documents every arg, and
  its source contains no `hackrf_transfer`.
- `app/simulation/ew_effects.py` cannot import `app.hardware`
  (`test_ext_step3.py`).

## 9. Production checklist

`config.validate_production()` **refuses to boot** if any of these is wrong; run
through it before deploying:

- [ ] `SPECTRA_PRODUCTION=1`
- [ ] `SPECTRA_JWT_KEY` set to a real secret (not the dev default)
- [ ] `SPECTRA_SEED_USERS=0` and the seeded accounts removed / re-passworded
- [ ] `SPECTRA_TLS_CERT` and `SPECTRA_TLS_KEY` present and valid
- [ ] `SPECTRA_CORS_ORIGINS` does **not** contain `localhost` / `127.0.0.1`
- [ ] `SPECTRA_DB_ENCRYPTION_KEY` set if the DB may leave the host
- [ ] `SPECTRA_RETENTION_DAYS` matches your retention policy
- [ ] `python -m scripts.preflight` prints `0 outbound connections`
- [ ] `pytest -q` green, including `test_ext_step2*` (no-transmit grep) and
      `test_ext_step7` (`--production` refusal, preflight)
- [ ] host firewalled to deny egress (`IPAddressDeny=any` / internal network)

## 10. Reporting a concern

This is a research prototype. If you find a class of issue (e.g. a missing role
check, a path that could open a socket, a way to persist unverified session
data), describe the **class** of problem and the affected module — do not attach
a working exploit or an extraction path.

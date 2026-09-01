"""Extension Step 2 verification: receive-only hardware layer, DSP, capture/replay.

Uses the default conftest principal override (admin), so these focus on
behaviour; role/demo gating for the hardware controls is in
``test_ext_step2_auth.py``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from app.dsp.process import SweepProcessor, detect_hops
from app.hardware import base as hw_base
from app.hardware.file_replay_adapter import FileReplayAdapter
from app.hardware.manager import _reset_for_tests as reset_hw
from app.hardware.recordings import recordings_dir
from app.main import app
from app.models.core import HardwareConfig, SweepFrame

client = TestClient(app)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_frame(seq: int, ts: float, tone_bins: range | None) -> SweepFrame:
    n = 200  # 88..108 MHz @ 100 kHz
    power = np.full(n, -95.0)
    if tone_bins is not None:
        power[list(tone_bins)] = -40.0
    return SweepFrame(
        ts=ts,
        seq=seq,
        f_start_hz=88_000_000.0,
        f_stop_hz=108_000_000.0,
        bin_hz=100_000.0,
        power_dbm=[float(x) for x in power],
        source="test",
    )


def _write_recording(frames: list[SweepFrame]) -> str:
    rid = f"testrec{int(time.time() * 1000) % 100000}"
    d = recordings_dir() / rid
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "frames.jsonl", "w", encoding="utf-8") as fh:
        for fr in frames:
            fh.write(fr.model_dump_json() + "\n")
    meta = {
        "recording_id": rid,
        "created_at": "2026-01-01T00:00:00Z",
        "name": "unit-test recording",
        "source": "test",
        "device_label": None,
        "start_freq_hz": frames[0].f_start_hz,
        "stop_freq_hz": frames[0].f_stop_hz,
        "bin_hz": frames[0].bin_hz,
        "frame_count": len(frames),
        "duration_s": frames[-1].ts - frames[0].ts,
        "first_frame_ts": frames[0].ts,
        "last_frame_ts": frames[-1].ts,
    }
    (d / "meta.json").write_text(json.dumps(meta), "utf-8")
    return rid


# --------------------------------------------------------------------------- #
# DSP
# --------------------------------------------------------------------------- #
def test_dsp_flags_the_tone_band_with_plausible_snr():
    proc = SweepProcessor(num_bands=20, smoothing_alpha=1.0, threshold_db=6.0)
    obs = proc.ingest(_make_frame(0, 0.0, tone_bins=range(98, 103)))  # ~98 MHz

    active = [o.band for o in obs if o.active]
    assert set(active) & {9, 10}, active
    assert len(active) <= 3  # a clean tone lights up ~one band, not the whole sweep

    tone = next(o for o in obs if o.band in (9, 10) and o.active)
    assert tone.snr_db > 40.0
    assert -100.0 <= tone.noise_floor_dbm <= -88.0
    assert 0.0 <= tone.confidence <= 1.0


def test_detect_hops_pairs_lost_and_gained_bands():
    prev = np.zeros(16, dtype=bool)
    curr = np.zeros(16, dtype=bool)
    prev[5] = True
    curr[7] = True
    assert detect_hops(prev, curr) == [(5, 7)]
    # too far apart -> not treated as a hop
    prev2 = np.zeros(16, dtype=bool)
    curr2 = np.zeros(16, dtype=bool)
    prev2[1] = True
    curr2[15] = True
    assert detect_hops(prev2, curr2) == []


def test_processor_detects_a_hop_across_two_frames():
    proc = SweepProcessor(num_bands=20, smoothing_alpha=1.0, threshold_db=6.0)
    proc.ingest(_make_frame(0, 0.0, tone_bins=range(98, 103)))   # band ~9/10
    proc.ingest(_make_frame(1, 0.1, tone_bins=range(118, 123)))  # band ~11/12
    assert proc.last_hops, "expected a hop to be reported"
    lost, gained = proc.last_hops[0]
    assert lost in (9, 10) and gained in (11, 12)


# --------------------------------------------------------------------------- #
# FileReplayAdapter
# --------------------------------------------------------------------------- #
def test_file_replay_roundtrips_frames_and_stops_at_eof():
    originals = [
        _make_frame(i, i * 0.1, tone_bins=range(90 + i, 95 + i)) for i in range(4)
    ]
    rid = _write_recording(originals)

    adapter = FileReplayAdapter()
    adapter.start_scan(
        HardwareConfig(
            source_mode="file_replay",
            recording_id=rid,
            replay_speed=100.0,
            replay_loop=False,
        )
    )

    got: list[SweepFrame] = []
    deadline = time.monotonic() + 3.0
    while len(got) < 4 and time.monotonic() < deadline:
        fr = adapter.read_frame()
        if fr is not None:
            got.append(fr)
        else:
            time.sleep(0.01)

    assert len(got) == 4
    for orig, replayed in zip(originals, got):
        assert replayed.f_start_hz == orig.f_start_hz
        assert replayed.f_stop_hz == orig.f_stop_hz
        assert replayed.bin_hz == orig.bin_hz
        assert replayed.power_dbm == orig.power_dbm

    # exhausted, not looping
    time.sleep(0.05)
    assert adapter.read_frame() is None
    adapter.stop_scan()


# --------------------------------------------------------------------------- #
# Receive-only guarantee
# --------------------------------------------------------------------------- #
def test_adapter_base_class_has_no_transmit_surface():
    for name in ("transmit", "tx", "start_tx", "send", "write_samples", "writeStream"):
        assert not hasattr(hw_base.HardwareAdapter, name)


def test_no_transmit_symbol_anywhere_in_hardware_package():
    hw_dir = Path(hw_base.__file__).parent
    for py in hw_dir.glob("*.py"):
        if py.name == "base.py":
            continue  # defines the forbidden-symbol allowlist
        text = py.read_text("utf-8")
        for sym in hw_base.FORBIDDEN_TX_SYMBOLS:
            assert sym not in text, f"{py.name} contains forbidden symbol {sym!r}"


def test_hackrf_command_never_references_the_transmit_tool():
    from app.hardware.hackrf_sweep_adapter import HackrfSweepAdapter

    for cfg in (
        HardwareConfig(source_mode="hackrf_sweep"),
        HardwareConfig(source_mode="hackrf_sweep", gain_db=32.0),
    ):
        cmd = " ".join(HackrfSweepAdapter().build_command(cfg))
        assert "hackrf_transfer" not in cmd
        assert cmd.startswith("hackrf_sweep ")


# --------------------------------------------------------------------------- #
# End-to-end: file_replay drives the same dashboard + live Simulation
# --------------------------------------------------------------------------- #
def _admin_headers():
    # conftest overrides the principal, but the hardware routes still read a
    # bearer for audit actor; any string works under the override.
    return {"Authorization": "Bearer test"}


def test_live_mode_runs_simulation_off_replayed_frames():
    reset_hw()
    frames = [
        _make_frame(i, i * 0.05, tone_bins=range(40 + (i % 3) * 10, 46 + (i % 3) * 10))
        for i in range(30)
    ]
    rid = _write_recording(frames)
    h = _admin_headers()

    try:
        # switch to live mode + start the receive-only file-replay source
        assert client.post(
            "/api/mode", json={"mode": "live_es", "confirm": True}, headers=h
        ).status_code == 200
        start = client.post(
            "/api/hardware/start",
            json={
                "config": {
                    "source_mode": "file_replay",
                    "recording_id": rid,
                    "num_bands": 24,
                    "replay_speed": 50.0,
                    "replay_loop": True,
                    "start_freq_hz": 88_000_000,
                    "stop_freq_hz": 108_000_000,
                    "bin_hz": 100_000,
                }
            },
            headers=h,
        )
        assert start.status_code == 200, start.text
        assert start.json()["running"] is True
        assert start.json()["frames_read"] >= 1
        assert start.json()["transmit_capability"] is False

        # frames + observations are being served
        frames_resp = client.get("/api/hardware/frames", headers=h).json()
        assert len(frames_resp["frames"]) >= 1
        assert len(frames_resp["observations"]) == 24

        # the existing simulation endpoints now run on the live environment
        client.post("/api/simulation/reset", json={"scheduler": "priority"}, headers=h)
        st = client.post("/api/simulation/step", json={"count": 25}, headers=h).json()
        assert st["live"] is True
        assert st["metrics_applicability"] == "proxy"
        assert st["metrics"]["steps"] == 25
        assert st["last_step"]["decision"]["scheduler"] == "priority"
        assert isinstance(st["last_step"]["decision"]["reasons"], list)
        assert len(st["spectrum"]["power_db"]) == 24
    finally:
        client.post("/api/hardware/stop", headers=h)
        client.post("/api/mode", json={"mode": "simulation", "confirm": True}, headers=h)
        reset_hw()


def test_hardware_status_and_devices_without_hardware():
    reset_hw()
    h = _admin_headers()
    status = client.get("/api/hardware/status", headers=h).json()
    assert status["running"] is False
    assert status["transmit_capability"] is False
    assert status["hardware_mode"] == "receive_only"

    devices = client.get("/api/hardware/devices", headers=h).json()["devices"]
    drivers = {d["driver"] for d in devices}
    assert {"rtl_power", "hackrf_sweep"} <= drivers
    for d in devices:
        assert d["receive_only"] is True


def test_missing_cli_tool_reports_actionable_error_and_sim_still_works():
    reset_hw()
    h = _admin_headers()
    client.post("/api/mode", json={"mode": "live_es", "confirm": True}, headers=h)
    try:
        r = client.post(
            "/api/hardware/start",
            json={"config": {"source_mode": "rtl_power"}},
            headers=h,
        )
        # rtl_power is not installed in CI -> a clear 409, not a crash
        assert r.status_code == 409
        assert "rtl_power" in r.json()["detail"]
        assert "file_replay" in r.json()["detail"]

        # simulation path is unaffected
        client.post("/api/mode", json={"mode": "simulation", "confirm": True}, headers=h)
        run = client.post(
            "/api/simulation/run",
            json={"steps": 60, "scheduler": "round_robin", "reset": True},
            headers=h,
        )
        assert run.status_code == 200
        assert run.json()["metrics"]["steps"] == 60
        assert run.json()["live"] is False
    finally:
        client.post("/api/mode", json={"mode": "simulation", "confirm": True}, headers=h)
        reset_hw()


def test_recording_roundtrip_via_api():
    reset_hw()
    frames = [_make_frame(i, i * 0.05, tone_bins=range(60, 66)) for i in range(20)]
    rid = _write_recording(frames)
    h = _admin_headers()
    try:
        client.post("/api/mode", json={"mode": "live_es", "confirm": True}, headers=h)
        client.post(
            "/api/hardware/start",
            json={"config": {"source_mode": "file_replay", "recording_id": rid,
                             "num_bands": 16, "replay_speed": 50.0, "replay_loop": True}},
            headers=h,
        )
        rec = client.post("/api/hardware/record/start", json={"name": "roundtrip"}, headers=h)
        assert rec.status_code == 200
        new_id = rec.json()["recording_id"]
        time.sleep(0.4)
        stop = client.post("/api/hardware/record/stop", headers=h)
        assert stop.status_code == 200
        assert stop.json()["frame_count"] >= 1

        listing = client.get("/api/hardware/recordings", headers=h).json()["recordings"]
        assert any(m["recording_id"] == new_id for m in listing)
        one = client.get(f"/api/hardware/recordings/{new_id}", headers=h)
        assert one.status_code == 200 and one.json()["name"] == "roundtrip"
    finally:
        client.post("/api/hardware/stop", headers=h)
        client.post("/api/mode", json={"mode": "simulation", "confirm": True}, headers=h)
        reset_hw()

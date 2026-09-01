"""File-replay adapter — the default source and the no-hardware demo path.

Plays a recorded sweep file back as if it were a live device. Accepts our own
``frames.jsonl`` recordings and raw ``rtl_power`` / ``hackrf_sweep`` ``.csv``.
Honours ``replay_speed`` (wall-clock accelerated) and ``replay_loop``.
"""

from __future__ import annotations

import time
from pathlib import Path

from ..models.core import HardwareConfig, HardwareDevice, SweepFrame
from .base import HardwareAdapter, HardwareUnavailable
from .recordings import get_recording_meta, iter_recording_frames, list_recordings, recordings_dir
from .sweep_csv import SweepAssembler


class FileReplayAdapter(HardwareAdapter):
    source_mode = "file_replay"

    def __init__(self) -> None:
        self._frames: list[SweepFrame] = []
        self._idx = 0
        self._speed = 1.0
        self._loop = True
        self._t0_wall = 0.0
        self._t0_frame = 0.0
        self._started = False
        self._label = ""

    # ------------------------------------------------------------------ #
    def list_devices(self) -> list[HardwareDevice]:
        return [
            HardwareDevice(
                id=f"recording:{m.recording_id}",
                label=f"{m.name} ({m.frame_count} frames)",
                driver="file_replay",
                available=True,
                note=f"{m.source} · {m.start_freq_hz/1e6:.1f}-{m.stop_freq_hz/1e6:.1f} MHz",
            )
            for m in list_recordings()
        ]

    def is_available(self) -> tuple[bool, str]:
        return True, "file replay is always available (needs a recording or .csv)"

    # ------------------------------------------------------------------ #
    def _load(self, config: HardwareConfig) -> list[SweepFrame]:
        rec_id = (config.recording_id or "").strip()
        if not rec_id:
            raise HardwareUnavailable(
                "file_replay needs recording_id (a recording id or a path to a .csv)"
            )

        # A path to a raw sweep .csv?
        p = Path(rec_id)
        if p.suffix.lower() == ".csv" and p.is_file():
            asm = SweepAssembler(source=f"file_replay:{p.name}")
            frames: list[SweepFrame] = []
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    out = asm.feed_line(line)
                    if out is not None:
                        frames.append(out)
            tail = asm.flush_remaining()
            if tail is not None:
                frames.append(tail)
            self._label = p.name
            if not frames:
                raise HardwareUnavailable(f"no sweeps parsed from {p}")
            return frames

        # Otherwise a recording id.
        try:
            meta = get_recording_meta(rec_id)
        except KeyError as exc:
            raise HardwareUnavailable(str(exc)) from exc
        self._label = meta.name
        frames = list(iter_recording_frames(rec_id))
        if not frames:
            raise HardwareUnavailable(f"recording {rec_id} has no frames")
        return frames

    def start_scan(self, config: HardwareConfig) -> None:
        self._frames = self._load(config)
        self._idx = 0
        self._speed = max(float(config.replay_speed), 1e-3)
        self._loop = bool(config.replay_loop)
        self._t0_wall = time.monotonic()
        self._t0_frame = self._frames[0].ts
        self._started = True

    def stop_scan(self) -> None:
        self._started = False
        self._frames = []
        self._idx = 0

    def read_frame(self) -> SweepFrame | None:
        if not self._started or not self._frames:
            return None
        if self._idx >= len(self._frames):
            if not self._loop:
                return None
            self._idx = 0
            self._t0_wall = time.monotonic()

        frame = self._frames[self._idx]
        elapsed = (time.monotonic() - self._t0_wall) * self._speed
        if (frame.ts - self._t0_frame) <= elapsed:
            self._idx += 1
            # Re-stamp so downstream frame-rate / recording timing is wall-clock.
            return frame.model_copy(update={"ts": time.time(), "seq": self._idx - 1})
        return None

    def get_status(self) -> dict:
        return {
            "source_mode": self.source_mode,
            "available": True,
            "detail": f"replaying {self._label} ({len(self._frames)} frames)"
            if self._started
            else "idle",
            "device_label": self._label or None,
        }


def _recordings_root() -> Path:  # convenience for callers/tests
    return recordings_dir()

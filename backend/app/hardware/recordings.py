"""On-disk sweep recordings.

Layout (under ``<data_dir>/recordings/<recording_id>/``)::

    frames.jsonl   one SweepFrame per line
    meta.json      RecordingMeta

Recordings are valid inputs to :class:`FileReplayAdapter` and to the Dataset Lab.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..models.core import RecordingMeta, SweepFrame


def recordings_dir() -> Path:
    d = get_settings().data_dir / "recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_recordings() -> list[RecordingMeta]:
    out: list[RecordingMeta] = []
    for meta_path in sorted(recordings_dir().glob("*/meta.json")):
        try:
            out.append(RecordingMeta(**json.loads(meta_path.read_text("utf-8"))))
        except (ValueError, OSError):
            continue
    out.sort(key=lambda m: m.created_at, reverse=True)
    return out


def get_recording_meta(recording_id: str) -> RecordingMeta:
    path = recordings_dir() / recording_id / "meta.json"
    if not path.is_file():
        raise KeyError(f"recording not found: {recording_id}")
    return RecordingMeta(**json.loads(path.read_text("utf-8")))


def iter_recording_frames(recording_id: str):
    path = recordings_dir() / recording_id / "frames.jsonl"
    if not path.is_file():
        raise KeyError(f"recording not found: {recording_id}")
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield SweepFrame(**json.loads(line))


class RecordingWriter:
    """Appends live frames to a new recording directory."""

    def __init__(self, name: str | None, source: str, device_label: str | None) -> None:
        self.recording_id = uuid.uuid4().hex[:12]
        self._dir = recordings_dir() / self.recording_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._handle = open(self._dir / "frames.jsonl", "w", encoding="utf-8")
        self._lock = threading.Lock()
        self.name = name or f"rec-{self.recording_id}"
        self.source = source
        self.device_label = device_label
        self.frame_count = 0
        self.first_ts: float | None = None
        self.last_ts: float | None = None
        self._f_start = 0.0
        self._f_stop = 0.0
        self._bin_hz = 0.0

    def write(self, frame: SweepFrame) -> None:
        with self._lock:
            self._handle.write(frame.model_dump_json() + "\n")
            self.frame_count += 1
            if self.first_ts is None:
                self.first_ts = frame.ts
                self._f_start = frame.f_start_hz
                self._f_stop = frame.f_stop_hz
                self._bin_hz = frame.bin_hz
            self.last_ts = frame.ts

    def close(self) -> RecordingMeta:
        with self._lock:
            self._handle.flush()
            self._handle.close()
        duration = (
            (self.last_ts - self.first_ts)
            if (self.first_ts is not None and self.last_ts is not None)
            else 0.0
        )
        meta = RecordingMeta(
            recording_id=self.recording_id,
            created_at=_utc_now(),
            name=self.name,
            source=self.source,
            device_label=self.device_label,
            start_freq_hz=self._f_start,
            stop_freq_hz=self._f_stop,
            bin_hz=self._bin_hz,
            frame_count=self.frame_count,
            duration_s=round(float(duration), 3),
            first_frame_ts=self.first_ts,
            last_frame_ts=self.last_ts,
        )
        (self._dir / "meta.json").write_text(meta.model_dump_json(indent=2), "utf-8")
        return meta

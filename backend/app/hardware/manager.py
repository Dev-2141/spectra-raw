"""Process-wide hardware manager.

Owns the active receive-only adapter, a background reader thread, a bounded ring
buffer of recent :class:`SweepFrame`, the DSP processor that turns frames into
:class:`BandObservation`, and the optional recorder.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from ..dsp.process import SweepProcessor
from ..models.core import (
    BandObservation,
    HardwareConfig,
    HardwareDevice,
    HardwareStatus,
    RecordingMeta,
    SourceMode,
    SweepFrame,
)
from .base import HardwareAdapter, HardwareUnavailable
from .file_replay_adapter import FileReplayAdapter
from .hackrf_sweep_adapter import HackrfSweepAdapter
from .recordings import RecordingWriter
from .rtl_power_adapter import RtlPowerAdapter
from .soapysdr_adapter import SoapySdrAdapter

_ADAPTERS: dict[str, type[HardwareAdapter]] = {
    SourceMode.FILE_REPLAY.value: FileReplayAdapter,
    SourceMode.RTL_POWER.value: RtlPowerAdapter,
    SourceMode.HACKRF_SWEEP.value: HackrfSweepAdapter,
    SourceMode.SOAPYSDR.value: SoapySdrAdapter,
}

_BUFFER_FRAMES = 512


class HardwareManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config = HardwareConfig()
        self._adapter: HardwareAdapter | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        self._buffer: deque[SweepFrame] = deque(maxlen=_BUFFER_FRAMES)
        self._latest_obs: list[BandObservation] = []
        self._processor = SweepProcessor(self._config.num_bands)

        self._frames_read = 0
        self._last_frame_ts: float | None = None
        self._recent_ts: deque[float] = deque(maxlen=20)
        self._error: str | None = None

        self._recorder: RecordingWriter | None = None
        self._last_recording: RecordingMeta | None = None

    # ------------------------------------------------------------------ #
    @property
    def config(self) -> HardwareConfig:
        return self._config

    @property
    def running(self) -> bool:
        return self._running

    def list_devices(self) -> list[HardwareDevice]:
        out: list[HardwareDevice] = []
        for cls in _ADAPTERS.values():
            try:
                out.extend(cls().list_devices())
            except Exception:  # pragma: no cover - defensive
                continue
        return out

    def configure(self, config: HardwareConfig) -> HardwareConfig:
        with self._lock:
            if self._running:
                raise HardwareUnavailable("stop the current scan before reconfiguring")
            self._config = config
            self._processor = SweepProcessor(config.num_bands)
            return self._config

    # ------------------------------------------------------------------ #
    def start(self, config: HardwareConfig | None = None, *, wait_first: float = 3.0) -> HardwareStatus:
        with self._lock:
            if self._running:
                return self.status()
            if config is not None:
                self._config = config
                self._processor = SweepProcessor(config.num_bands)

            mode = self._config.source_mode.value
            if mode == SourceMode.SIMULATION.value:
                raise HardwareUnavailable("source_mode 'simulation' has no hardware adapter")
            cls = _ADAPTERS.get(mode)
            if cls is None:
                raise HardwareUnavailable(f"unknown source_mode: {mode}")

            adapter = cls()
            ok, reason = adapter.is_available()
            if not ok and mode != SourceMode.FILE_REPLAY.value:
                raise HardwareUnavailable(reason)

            adapter.start_scan(self._config)  # raises HardwareUnavailable on failure
            self._adapter = adapter
            self._buffer.clear()
            self._latest_obs = []
            self._frames_read = 0
            self._last_frame_ts = None
            self._recent_ts.clear()
            self._error = None
            self._stop.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._reader_loop, name="hw-reader", daemon=True
            )
            self._thread.start()

        # Give the stream a moment to produce its first frame.
        deadline = time.monotonic() + max(0.0, wait_first)
        while time.monotonic() < deadline:
            if self._frames_read > 0:
                break
            time.sleep(0.02)
        return self.status()

    def _reader_loop(self) -> None:
        assert self._adapter is not None
        adapter = self._adapter
        while not self._stop.is_set():
            try:
                frame = adapter.read_frame()
            except Exception as exc:  # pragma: no cover - defensive
                self._error = f"{type(exc).__name__}: {exc}"
                frame = None
            if frame is None:
                time.sleep(0.01)
                continue
            with self._lock:
                self._buffer.append(frame)
                self._frames_read += 1
                self._last_frame_ts = frame.ts
                self._recent_ts.append(time.monotonic())
                try:
                    self._latest_obs = self._processor.ingest(frame)
                except Exception as exc:  # pragma: no cover - defensive
                    self._error = f"dsp: {exc}"
                if self._recorder is not None:
                    self._recorder.write(frame)

    def stop(self) -> HardwareStatus:
        with self._lock:
            self._stop.set()
            adapter = self._adapter
            recorder = self._recorder
            self._recorder = None
        if recorder is not None:
            self._last_recording = recorder.close()
        if adapter is not None:
            try:
                adapter.stop_scan()
            except Exception:  # pragma: no cover - defensive
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self._lock:
            self._adapter = None
            self._thread = None
            self._running = False
        return self.status()

    # ------------------------------------------------------------------ #
    def latest_frame(self) -> SweepFrame | None:
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def frames_since(self, seq: int) -> list[SweepFrame]:
        with self._lock:
            return [f for f in self._buffer if f.seq > seq]

    def latest_observations(self) -> list[BandObservation]:
        with self._lock:
            return list(self._latest_obs)

    def _frame_rate(self) -> float:
        if len(self._recent_ts) < 2:
            return 0.0
        span = self._recent_ts[-1] - self._recent_ts[0]
        return round((len(self._recent_ts) - 1) / span, 3) if span > 0 else 0.0

    def status(self) -> HardwareStatus:
        with self._lock:
            adapter_detail = ""
            available = True
            device_label = None
            if self._adapter is not None:
                st = self._adapter.get_status()
                adapter_detail = st.get("detail", "")
                available = bool(st.get("available", True))
                device_label = st.get("device_label")
                self._error = st.get("error") or self._error
            return HardwareStatus(
                source_mode=self._config.source_mode.value,
                running=self._running,
                available=available,
                device_label=device_label,
                frames_read=self._frames_read,
                last_frame_ts=self._last_frame_ts,
                frame_rate_hz=self._frame_rate(),
                buffer_len=len(self._buffer),
                latest_seq=self._buffer[-1].seq if self._buffer else -1,
                error=self._error,
                recording=self._recorder is not None,
                recording_id=self._recorder.recording_id if self._recorder else None,
                detail=adapter_detail,
            )

    # ------------------------------------------------------------------ #
    def start_recording(self, name: str | None) -> dict:
        with self._lock:
            if not self._running:
                raise HardwareUnavailable("start a scan before recording")
            if self._recorder is not None:
                raise HardwareUnavailable("already recording")
            self._recorder = RecordingWriter(
                name=name,
                source=self._config.source_mode.value,
                device_label=self.status().device_label,
            )
            return {"recording_id": self._recorder.recording_id, "recording": True}

    def stop_recording(self) -> RecordingMeta:
        with self._lock:
            recorder = self._recorder
            self._recorder = None
        if recorder is None:
            raise HardwareUnavailable("not recording")
        self._last_recording = recorder.close()
        return self._last_recording


# --------------------------------------------------------------------------- #
_manager: HardwareManager | None = None


def get_hardware_manager() -> HardwareManager:
    global _manager
    if _manager is None:
        _manager = HardwareManager()
    return _manager


def _reset_for_tests() -> None:
    global _manager
    if _manager is not None and _manager.running:
        try:
            _manager.stop()
        except Exception:
            pass
    _manager = None

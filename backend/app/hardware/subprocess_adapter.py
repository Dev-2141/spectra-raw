"""Shared plumbing for CLI-backed receive-only sweep tools.

Spawns a subprocess (``rtl_power`` or ``hackrf_sweep``), reads its CSV stdout on
a background thread, assembles whole sweeps, and hands them out via a queue.
Concrete adapters only supply the binary name and the argument list — and those
argument lists are RX-only by construction.
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading

from ..models.core import HardwareConfig, HardwareDevice, SweepFrame
from .base import HardwareAdapter, HardwareUnavailable
from .sweep_csv import SweepAssembler


class SubprocessSweepAdapter(HardwareAdapter):
    binary: str = ""
    driver: str = ""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._q: "queue.Queue[SweepFrame]" = queue.Queue(maxsize=256)
        self._err_tail: list[str] = []

    # ------------------------------------------------------------------ #
    def build_command(self, config: HardwareConfig) -> list[str]:  # pragma: no cover
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    def _bin_path(self) -> str | None:
        return shutil.which(self.binary)

    def list_devices(self) -> list[HardwareDevice]:
        ok, reason = self.is_available()
        return [
            HardwareDevice(
                id=self.driver,
                label=f"{self.driver} ({'ready' if ok else 'unavailable'})",
                driver=self.driver,
                available=ok,
                note=reason,
            )
        ]

    def is_available(self) -> tuple[bool, str]:
        path = self._bin_path()
        if path:
            return True, f"{self.binary} found at {path}"
        return (
            False,
            f"{self.binary} not on PATH — install it, or use source_mode=file_replay",
        )

    # ------------------------------------------------------------------ #
    def start_scan(self, config: HardwareConfig) -> None:
        if not self._bin_path():
            raise HardwareUnavailable(self.is_available()[1])
        cmd = self.build_command(config)
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - args built from typed config
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise HardwareUnavailable(f"failed to start {self.binary}: {exc}") from exc

        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, name=f"{self.driver}-reader", daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        assert self._proc is not None
        asm = SweepAssembler(source=self.driver)
        stdout = self._proc.stdout
        if stdout is None:
            return
        for line in stdout:
            if self._stop.is_set():
                break
            frame = asm.feed_line(line)
            if frame is not None:
                try:
                    self._q.put_nowait(frame)
                except queue.Full:
                    try:
                        self._q.get_nowait()
                        self._q.put_nowait(frame)
                    except queue.Empty:
                        pass
        # Drain stderr tail for diagnostics.
        if self._proc.stderr is not None:
            self._err_tail = self._proc.stderr.read().splitlines()[-5:]

    def stop_scan(self) -> None:
        self._stop.set()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        with self._q.mutex:
            self._q.queue.clear()

    def read_frame(self) -> SweepFrame | None:
        try:
            return self._q.get_nowait()
        except queue.Empty:
            return None

    def get_status(self) -> dict:
        ok, reason = self.is_available()
        return {
            "source_mode": self.source_mode,
            "available": ok,
            "detail": reason if not self._proc else f"{self.driver} streaming",
            "error": " ".join(self._err_tail) or None,
        }

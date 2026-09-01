"""Common receive-only adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.core import HardwareConfig, HardwareDevice, SweepFrame

# Symbols that must never appear anywhere under app/hardware/. Enforced by test.
FORBIDDEN_TX_SYMBOLS: tuple[str, ...] = (
    "hackrf_transfer",
    "writeStream",
    "SOAPY_SDR_TX",
    "send_waveform",
    "transmit(",
    "start_tx",
    "TX_MODE",
)


class HardwareUnavailable(RuntimeError):
    """Raised when a requested SDR source cannot be started (missing tool/device)."""


class HardwareAdapter(ABC):
    """A receive-only spectrum source.

    Implementations turn an SDR sweep (or a recorded file) into a stream of
    :class:`SweepFrame`. There is intentionally **no** transmit method on this
    class and none may be added.
    """

    source_mode: str = "base"

    @abstractmethod
    def list_devices(self) -> list[HardwareDevice]:
        """Enumerate candidate devices for this adapter (may be empty)."""

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Return ``(ok, reason)``. ``reason`` is a human hint when not ok."""

    @abstractmethod
    def start_scan(self, config: HardwareConfig) -> None:
        """Begin producing frames. Raise :class:`HardwareUnavailable` on failure."""

    @abstractmethod
    def stop_scan(self) -> None:
        """Stop producing frames and release resources. Idempotent."""

    @abstractmethod
    def read_frame(self) -> SweepFrame | None:
        """Return the next available frame, or ``None`` if none is ready yet."""

    def get_status(self) -> dict:
        ok, reason = self.is_available()
        return {"source_mode": self.source_mode, "available": ok, "detail": reason}

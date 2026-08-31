"""Generic SDR adapter via SoapySDR — RECEIVE-ONLY, flag-gated.

Only ever opens a receive stream (``SOAPY_SDR_RX``) and reads samples from it.
It never opens a transmit stream and never writes samples to a device. Disabled
unless ``FLAG_SOAPYSDR`` is set *and* the ``SoapySDR`` module is importable.
"""

from __future__ import annotations

import time

import numpy as np

from ..config import get_settings
from ..models.core import HardwareConfig, HardwareDevice, SweepFrame
from .base import HardwareAdapter, HardwareUnavailable


def _try_import_soapy():
    try:
        import SoapySDR  # type: ignore

        return SoapySDR
    except Exception:  # pragma: no cover - depends on host
        return None


class SoapySdrAdapter(HardwareAdapter):
    source_mode = "soapysdr"

    def __init__(self) -> None:
        self._soapy = None
        self._dev = None
        self._stream = None
        self._config: HardwareConfig | None = None
        self._seq = 0

    def list_devices(self) -> list[HardwareDevice]:
        soapy = _try_import_soapy()
        if soapy is None:
            return [
                HardwareDevice(
                    id="soapysdr",
                    label="SoapySDR (module not installed)",
                    driver="soapysdr",
                    available=False,
                    note="pip/OS package 'SoapySDR' not importable",
                )
            ]
        out: list[HardwareDevice] = []
        for info in soapy.Device.enumerate():
            d = dict(info)
            out.append(
                HardwareDevice(
                    id=d.get("serial", d.get("label", "soapysdr")),
                    label=d.get("label", "SoapySDR device"),
                    driver=d.get("driver", "soapysdr"),
                    available=True,
                    note="RX stream only",
                )
            )
        return out

    def is_available(self) -> tuple[bool, str]:
        if not get_settings().flag_soapysdr:
            return False, "SoapySDR support disabled (set FLAG_SOAPYSDR=1)"
        if _try_import_soapy() is None:
            return False, "SoapySDR module not importable"
        return True, "SoapySDR available"

    def start_scan(self, config: HardwareConfig) -> None:  # pragma: no cover - needs hw
        ok, reason = self.is_available()
        if not ok:
            raise HardwareUnavailable(reason)
        soapy = _try_import_soapy()
        self._soapy = soapy
        self._config = config
        self._dev = soapy.Device()
        center = 0.5 * (config.start_freq_hz + config.stop_freq_hz)
        rate = max(config.stop_freq_hz - config.start_freq_hz, 2_000_000.0)
        self._dev.setSampleRate(soapy.SOAPY_SDR_RX, 0, rate)
        self._dev.setFrequency(soapy.SOAPY_SDR_RX, 0, center)
        if config.gain_db is not None:
            self._dev.setGain(soapy.SOAPY_SDR_RX, 0, float(config.gain_db))
        self._stream = self._dev.setupStream(soapy.SOAPY_SDR_RX, soapy.SOAPY_SDR_CF32)
        self._dev.activateStream(self._stream)
        self._seq = 0

    def stop_scan(self) -> None:  # pragma: no cover - needs hw
        if self._dev is not None and self._stream is not None and self._soapy is not None:
            try:
                self._dev.deactivateStream(self._stream)
                self._dev.closeStream(self._stream)
            except Exception:
                pass
        self._dev = self._stream = self._soapy = None

    def read_frame(self) -> SweepFrame | None:  # pragma: no cover - needs hw
        if self._dev is None or self._stream is None or self._config is None:
            return None
        cfg = self._config
        n = 4096
        buff = np.zeros(n, dtype=np.complex64)
        sr = self._dev.readStream(self._stream, [buff], n)
        if getattr(sr, "ret", 0) <= 0:
            return None
        window = np.hanning(n)
        spectrum = np.fft.fftshift(np.fft.fft(buff * window))
        psd = 20.0 * np.log10(np.abs(spectrum) + 1e-12)
        nbins = max(1, int((cfg.stop_freq_hz - cfg.start_freq_hz) / cfg.bin_hz))
        idx = np.linspace(0, n - 1, nbins).astype(int)
        self._seq += 1
        return SweepFrame(
            ts=time.time(),
            seq=self._seq - 1,
            f_start_hz=cfg.start_freq_hz,
            f_stop_hz=cfg.stop_freq_hz,
            bin_hz=cfg.bin_hz,
            power_dbm=[float(x) for x in psd[idx]],
            source="soapysdr",
        )

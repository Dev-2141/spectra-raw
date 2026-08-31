"""HackRF adapter — RECEIVE-ONLY, via the ``hackrf_sweep`` CLI.

HackRF One is a transceiver. This adapter is deliberately limited to the
**receive** sweep tool. It never invokes the HackRF transmit CLI, never passes
a transmit-related flag, and exposes no transmit method.

Exact invocation (all receive-only)::

    hackrf_sweep -f <min_MHz>:<max_MHz> -w <bin_Hz> [-l <lna_dB>] [-g <vga_dB>]

``-f`` frequency range in MHz, ``-w`` FFT bin width in Hz, ``-l`` LNA (RX) gain,
``-g`` VGA (RX baseband) gain. CSV is written to stdout. The sweep tool has no
transmit option and none is used here.
"""

from __future__ import annotations

from ..models.core import HardwareConfig
from .subprocess_adapter import SubprocessSweepAdapter


class HackrfSweepAdapter(SubprocessSweepAdapter):
    source_mode = "hackrf_sweep"
    binary = "hackrf_sweep"
    driver = "hackrf_sweep"

    def build_command(self, config: HardwareConfig) -> list[str]:
        f_min_mhz = int(config.start_freq_hz // 1_000_000)
        f_max_mhz = max(f_min_mhz + 1, int(round(config.stop_freq_hz / 1_000_000)))
        cmd = [
            self.binary,
            "-f",
            f"{f_min_mhz}:{f_max_mhz}",
            "-w",
            str(int(config.bin_hz)),
        ]
        if config.gain_db is not None:
            # Split the requested gain across LNA (RX) and VGA (RX baseband).
            lna = int(min(40, max(0, round(config.gain_db * 0.5 / 8) * 8)))
            vga = int(min(62, max(0, round(config.gain_db * 0.5 / 2) * 2)))
            cmd += ["-l", str(lna), "-g", str(vga)]
        return cmd

"""RTL-SDR adapter — receive-only, via the ``rtl_power`` CLI.

``rtl_power`` is a power-measurement tool with no transmit capability. This
adapter only ever spawns ``rtl_power`` with a frequency range, bin width and
integration interval, and parses its CSV stdout.
"""

from __future__ import annotations

from ..models.core import HardwareConfig
from .subprocess_adapter import SubprocessSweepAdapter


class RtlPowerAdapter(SubprocessSweepAdapter):
    source_mode = "rtl_power"
    binary = "rtl_power"
    driver = "rtl_power"

    def build_command(self, config: HardwareConfig) -> list[str]:
        interval_s = max(1, round(config.sweep_interval_ms / 1000))
        cmd = [
            self.binary,
            "-f",
            f"{int(config.start_freq_hz)}:{int(config.stop_freq_hz)}:{int(config.bin_hz)}",
            "-i",
            f"{interval_s}s",
            "-e",
            f"{interval_s}s",
        ]
        if config.gain_db is not None:
            cmd += ["-g", str(config.gain_db)]
        if config.ppm is not None:
            cmd += ["-p", str(int(config.ppm))]
        cmd += ["-"]  # CSV to stdout
        return cmd

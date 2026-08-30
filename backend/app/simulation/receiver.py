"""Receiver digital twin.

A receive-only sensor that can observe one band (or a small contiguous window)
per dwell. Detection is a probabilistic function of the synthetic SNR; false
alarms occur at a fixed rate on inactive scans.
"""

from __future__ import annotations

import numpy as np

from ..models.core import ReceiverConfig, ReceiverState
from .environment import RFEnvironment


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


class Receiver:
    """Stateful receiver twin driven by :class:`RFEnvironment` ground truth."""

    def __init__(self, config: ReceiverConfig, rng: np.random.Generator):
        self.config = config
        self.rng = rng
        self.state = ReceiverState()

    # ------------------------------------------------------------------ #
    def reset(self, start_band: int = 0) -> None:
        self.state = ReceiverState(current_band=start_band)

    def tune(self, band: int) -> bool:
        """Point the receiver at ``band``. Returns True if a retune occurred."""
        retuned = band != self.state.current_band
        self.state.current_band = band
        if retuned:
            self.state.retune_cooldown = self.config.retune_delay_slots
        return retuned

    def _detection_prob(self, true_snr_db: float) -> float:
        """Logistic P(detect) centred on the detection threshold."""
        margin = true_snr_db - self.config.detection_threshold_db
        return float(_sigmoid(margin / 2.0))

    def observe(self, env: RFEnvironment, t: int, band: int) -> dict:
        """Observe ``band`` at time ``t``. Returns a raw measurement dict."""
        cfg = self.config
        self.state.total_scans += 1
        self.state.visited_bands.append(band)

        # A scan window observes a few neighbouring bands; report the strongest.
        half = (cfg.scan_window - 1) // 2
        lo = max(0, band - half)
        hi = min(env.num_bands - 1, lo + cfg.scan_window - 1)
        window = range(lo, hi + 1)

        best = {
            "band": band,
            "true_active": False,
            "true_snr_db": 0.0,
            "threat": 0.0,
        }
        for b in window:
            if env.is_active(t, b):
                snr = env.snr_at(t, b)
                if not best["true_active"] or snr > best["true_snr_db"]:
                    best = {
                        "band": b,
                        "true_active": True,
                        "true_snr_db": snr,
                        "threat": env.threat_at(t, b),
                    }

        true_active = best["true_active"]
        true_snr = best["true_snr_db"]
        report_band = best["band"] if true_active else band

        measured_snr = 0.0
        detected = False
        false_alarm = False

        if true_active:
            measured_snr = true_snr + float(
                self.rng.normal(0.0, cfg.snr_measurement_noise_db)
            )
            p_d = self._detection_prob(true_snr)
            detected = bool(
                self.rng.random() < p_d and measured_snr >= cfg.detection_threshold_db
            )
        else:
            # Noise-only: occasionally the estimator crosses threshold.
            measured_snr = float(
                abs(self.rng.normal(0.0, cfg.snr_measurement_noise_db))
            )
            false_alarm = bool(self.rng.random() < cfg.false_alarm_prob)
            detected = false_alarm

        if detected and true_active:
            self.state.detections.append(report_band)

        measured_power = env.noise_floor_db + measured_snr

        # Age the retune cooldown for this dwell.
        if self.state.retune_cooldown > 0:
            self.state.retune_cooldown -= 1

        return {
            "band": report_band,
            "scanned_band": band,
            "true_active": true_active,
            "detected": detected,
            "false_alarm": false_alarm,
            "measured_snr_db": round(measured_snr, 3),
            "measured_power_db": round(measured_power, 3),
            "threat": round(float(best["threat"]), 3),
            "true_snr_db": round(true_snr, 3),
        }

"""Synthetic RF environment generator.

Builds fully deterministic ground-truth matrices (given a seed) describing which
band is active at which time slot, the received power / SNR, and a threat score.
Everything is synthetic: no real emitter libraries, no captured RF data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..models.core import (
    Band,
    Emitter,
    EmitterBehavior,
    RFEnvironmentConfig,
)


@dataclass
class EmitterEvent:
    """A contiguous run of activity for one emitter in one band."""

    emitter_id: int
    band: int
    start: int
    end: int  # inclusive
    high_priority: bool
    threat: float
    detected: bool = False
    first_detection_slot: int | None = None

    @property
    def length(self) -> int:
        return self.end - self.start + 1


_BEHAVIOR_WEIGHTS = {
    EmitterBehavior.CONSTANT: 0.18,
    EmitterBehavior.BURST: 0.24,
    EmitterBehavior.PERIODIC: 0.20,
    EmitterBehavior.HOPPING: 0.14,
    EmitterBehavior.LOW_DUTY: 0.14,
    EmitterBehavior.PRIORITY: 0.10,
}


class RFEnvironment:
    """Owns the synthetic ground truth for one scenario."""

    def __init__(self, config: RFEnvironmentConfig):
        self.config = config
        self.rng = np.random.default_rng(config.seed)

        self.num_bands = config.num_bands
        self.num_time_slots = config.num_time_slots
        self.noise_floor_db = config.noise_floor_db

        self.bands: list[Band] = [
            Band(
                index=i,
                center_mhz=config.base_center_mhz + i * config.band_width_mhz,
                width_mhz=config.band_width_mhz,
            )
            for i in range(self.num_bands)
        ]

        self.emitters: list[Emitter] = []
        # (T, B) matrices
        self.occupancy = np.zeros((self.num_time_slots, self.num_bands), dtype=bool)
        self.snr_db = np.zeros((self.num_time_slots, self.num_bands), dtype=np.float32)
        self.power_db = np.full(
            (self.num_time_slots, self.num_bands),
            self.noise_floor_db,
            dtype=np.float32,
        )
        self.threat = np.zeros((self.num_time_slots, self.num_bands), dtype=np.float32)
        self.emitter_id_matrix = np.full(
            (self.num_time_slots, self.num_bands), -1, dtype=np.int32
        )
        self.events: list[EmitterEvent] = []

        self._generate()

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #
    def _generate(self) -> None:
        cfg = self.config
        n_emitters = max(1, int(round(cfg.emitter_density * self.num_bands)))
        behaviors = list(_BEHAVIOR_WEIGHTS.keys())
        probs = np.array([_BEHAVIOR_WEIGHTS[b] for b in behaviors], dtype=float)
        probs /= probs.sum()

        home_bands = self.rng.permutation(self.num_bands)[:n_emitters]

        for eid in range(n_emitters):
            behavior = behaviors[int(self.rng.choice(len(behaviors), p=probs))]
            home = int(home_bands[eid % len(home_bands)])
            snr = float(self.rng.uniform(cfg.snr_min_db, cfg.snr_max_db))

            high_priority = behavior == EmitterBehavior.PRIORITY or (
                self.rng.random() < cfg.high_priority_fraction
            )
            if behavior == EmitterBehavior.PRIORITY:
                threat = float(self.rng.uniform(0.75, 1.0))
            elif high_priority:
                threat = float(self.rng.uniform(0.6, 0.85))
            else:
                threat = float(self.rng.uniform(0.1, 0.55))

            emitter = Emitter(
                id=eid,
                label=f"E{eid:02d}-{behavior.value}",
                behavior=behavior,
                home_band=home,
                threat=round(threat, 3),
                high_priority=bool(high_priority),
                snr_db=round(snr, 2),
                duty_cycle=0.0,  # filled after painting
            )
            self._paint_emitter(emitter)
            self.emitters.append(emitter)

        # Per-cell power from SNR (only where something is active).
        active = self.occupancy
        self.power_db = np.where(
            active,
            self.noise_floor_db + self.snr_db,
            self.noise_floor_db,
        ).astype(np.float32)
        # A little correlated background ripple so an empty spectrum is not flat.
        ripple = self.rng.normal(0.0, 0.6, size=self.power_db.shape).astype(np.float32)
        self.power_db = self.power_db + ripple

        self._extract_events()

    def _mark(self, emitter: Emitter, band: int, t0: int, t1: int) -> None:
        t0 = max(0, t0)
        t1 = min(self.num_time_slots - 1, t1)
        if t1 < t0:
            return
        sl = slice(t0, t1 + 1)
        # Keep the strongest emitter if bands overlap.
        stronger = emitter.snr_db >= self.snr_db[sl, band]
        write = stronger | ~self.occupancy[sl, band]
        self.occupancy[sl, band] = self.occupancy[sl, band] | True
        self.snr_db[sl, band] = np.where(
            write, emitter.snr_db, self.snr_db[sl, band]
        )
        self.threat[sl, band] = np.where(
            write, emitter.threat, self.threat[sl, band]
        )
        self.emitter_id_matrix[sl, band] = np.where(
            write, emitter.id, self.emitter_id_matrix[sl, band]
        )

    def _paint_emitter(self, emitter: Emitter) -> None:
        T = self.num_time_slots
        rng = self.rng
        b = emitter.home_band
        behavior = emitter.behavior

        if behavior == EmitterBehavior.CONSTANT:
            # A few long on-blocks covering most of the timeline.
            t = int(rng.integers(0, max(1, T // 20)))
            while t < T:
                on = int(rng.integers(T // 6, T // 3))
                self._mark(emitter, b, t, t + on)
                gap = int(rng.integers(T // 40, T // 12))
                t += on + gap
            emitter.params = {"note": "long on-blocks"}

        elif behavior == EmitterBehavior.BURST:
            t = 0
            while t < T:
                gap = int(rng.integers(6, 34))
                t += gap
                burst = int(rng.integers(1, 5))
                self._mark(emitter, b, t, t + burst - 1)
                t += burst
            emitter.params = {"burst_len": "1-4", "gap": "6-33"}

        elif behavior == EmitterBehavior.PERIODIC:
            period = int(rng.integers(9, 41))
            pulse = int(rng.integers(1, 4))
            phase = int(rng.integers(0, period))
            for t in range(phase, T, period):
                self._mark(emitter, b, t, t + pulse - 1)
            emitter.params = {"period": period, "pulse": pulse, "phase": phase}

        elif behavior == EmitterBehavior.HOPPING:
            hop_interval = int(rng.integers(3, 12))
            band = b
            t = 0
            touched = set()
            while t < T:
                dwell = hop_interval
                # Mostly on while parked on a band.
                if rng.random() < 0.85:
                    self._mark(emitter, band, t, t + dwell - 1)
                    touched.add(int(band))
                step = int(rng.integers(-4, 5))
                band = int(np.clip(band + step, 0, self.num_bands - 1))
                t += dwell
            emitter.params = {"hop_interval": hop_interval, "bands": sorted(touched)}

        elif behavior == EmitterBehavior.LOW_DUTY:
            n_events = max(1, int(T * rng.uniform(0.01, 0.04)))
            for _ in range(n_events):
                t = int(rng.integers(0, T))
                dur = int(rng.integers(1, 3))
                self._mark(emitter, b, t, t + dur - 1)
            emitter.params = {"events": n_events}

        elif behavior == EmitterBehavior.PRIORITY:
            n_events = max(1, int(T * rng.uniform(0.03, 0.08)))
            for _ in range(n_events):
                t = int(rng.integers(0, T))
                dur = int(rng.integers(1, 4))
                self._mark(emitter, b, t, t + dur - 1)
            emitter.params = {"events": n_events, "note": "intermittent high-value"}

        emitter.duty_cycle = round(
            float(self.occupancy[:, b].mean()) if b < self.num_bands else 0.0, 4
        )

    def _extract_events(self) -> None:
        """Collapse the occupancy matrix into per-(emitter, band) activity runs."""
        events: list[EmitterEvent] = []
        eid_mat = self.emitter_id_matrix
        for band in range(self.num_bands):
            col_active = self.occupancy[:, band]
            if not col_active.any():
                continue
            t = 0
            T = self.num_time_slots
            while t < T:
                if not col_active[t]:
                    t += 1
                    continue
                start = t
                while t < T and col_active[t]:
                    t += 1
                end = t - 1
                mid = (start + end) // 2
                eid = int(eid_mat[mid, band])
                emitter = self.emitters[eid] if 0 <= eid < len(self.emitters) else None
                events.append(
                    EmitterEvent(
                        emitter_id=eid,
                        band=band,
                        start=start,
                        end=end,
                        high_priority=bool(emitter.high_priority) if emitter else False,
                        threat=float(self.threat[mid, band]),
                    )
                )
        events.sort(key=lambda e: (e.start, e.band))
        self.events = events

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def is_active(self, t: int, band: int) -> bool:
        return bool(self.occupancy[t, band])

    def active_bands(self, t: int) -> list[int]:
        return np.nonzero(self.occupancy[t])[0].tolist()

    def snr_at(self, t: int, band: int) -> float:
        return float(self.snr_db[t, band])

    def power_at(self, t: int, band: int) -> float:
        return float(self.power_db[t, band])

    def threat_at(self, t: int, band: int) -> float:
        return float(self.threat[t, band])

    def events_started_by(self, t: int) -> list[EmitterEvent]:
        return [e for e in self.events if e.start <= t]

    def band_threat_prior(self) -> np.ndarray:
        """Static per-band max threat (known ES library metadata, not live truth)."""
        prior = np.zeros(self.num_bands, dtype=np.float32)
        for e in self.emitters:
            prior[e.home_band] = max(prior[e.home_band], e.threat)
        return prior

    def occupancy_percentage(self) -> float:
        return float(self.occupancy.mean())

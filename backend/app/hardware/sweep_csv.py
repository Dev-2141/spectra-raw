"""Parser for ``rtl_power`` / ``hackrf_sweep`` CSV output.

Both tools emit the same row shape, one row per frequency *segment*::

    date, time, hz_low, hz_high, hz_bin_width, num_samples, dB, dB, dB, ...

A full sweep spans many consecutive rows. :class:`SweepAssembler` stitches the
segments of one sweep into a single :class:`SweepFrame` and flushes it when the
timestamp changes or the frequency wraps back to a lower value.
"""

from __future__ import annotations

import time as _time
from datetime import datetime

from ..models.core import SweepFrame


def _parse_ts(date_s: str, time_s: str) -> float:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"{date_s.strip()} {time_s.strip()}", fmt).timestamp()
        except ValueError:
            continue
    return _time.time()


class _Segment:
    __slots__ = ("ts", "hz_low", "hz_high", "hz_bin", "powers")

    def __init__(self, ts: float, hz_low: float, hz_high: float, hz_bin: float, powers: list[float]):
        self.ts = ts
        self.hz_low = hz_low
        self.hz_high = hz_high
        self.hz_bin = hz_bin
        self.powers = powers


def parse_sweep_csv_line(line: str) -> _Segment | None:
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 7:
        return None
    try:
        ts = _parse_ts(parts[0], parts[1])
        hz_low = float(parts[2])
        hz_high = float(parts[3])
        hz_bin = float(parts[4])
        powers = [float(p) for p in parts[6:] if p not in ("", "-inf", "nan")]
    except ValueError:
        return None
    if not powers:
        return None
    return _Segment(ts, hz_low, hz_high, hz_bin, powers)


class SweepAssembler:
    """Feed CSV lines in; get whole :class:`SweepFrame` objects out."""

    def __init__(self, source: str) -> None:
        self.source = source
        self._segments: list[_Segment] = []
        self._seq = 0

    def _flush(self) -> SweepFrame | None:
        if not self._segments:
            return None
        segs = sorted(self._segments, key=lambda s: s.hz_low)
        self._segments = []
        f_start = segs[0].hz_low
        f_stop = segs[-1].hz_high
        bin_hz = segs[0].hz_bin or 1.0
        powers: list[float] = []
        for s in segs:
            powers.extend(s.powers)
        frame = SweepFrame(
            ts=segs[0].ts,
            seq=self._seq,
            f_start_hz=f_start,
            f_stop_hz=f_stop,
            bin_hz=bin_hz,
            power_dbm=powers,
            source=self.source,
        )
        self._seq += 1
        return frame

    def feed_line(self, line: str) -> SweepFrame | None:
        seg = parse_sweep_csv_line(line)
        if seg is None:
            return None
        out: SweepFrame | None = None
        if self._segments:
            last = self._segments[-1]
            wrapped = seg.hz_low <= last.hz_low
            new_ts = abs(seg.ts - last.ts) > 1e-6
            if wrapped or new_ts:
                out = self._flush()
        self._segments.append(seg)
        return out

    def flush_remaining(self) -> SweepFrame | None:
        return self._flush()

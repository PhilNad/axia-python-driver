"""Timestamps for the Axia's samples, from its sample counter.

RDT carries no time, only counters. Stamping at arrival inherits the network and scheduler
jitter; the sensor's counter is exact. SequenceClock keeps the counter's regularity and puts it
on the local clock: over a sliding window it fits t_recv ~ a + b * n (b: seconds per count,
which also absorbs the sensor's crystal drift) and shifts the line down to the LOWER ENVELOPE
of the arrivals, i.e. stamp = the earliest each sample could have arrived. The estimator maps
every stream that way (ft_payload_ros2/clock.py), so the Axia and the robot share one clock.
"""

from __future__ import annotations

from collections import deque

import numpy as np


class SequenceClock:
    def __init__(self, nominal_rate, window_s=30.0, refit_s=1.0, max_rate_error=0.02):
        self.nominal_period = 1.0 / float(nominal_rate)
        self.window_s = float(window_s)
        self.refit_s = float(refit_s)
        self.max_rate_error = float(max_rate_error)
        self.reset()

    def reset(self):
        self._n = deque()
        self._t = deque()
        self._wrap = 0
        self._last_raw = None
        self.period = self.nominal_period
        self.offset = None              # a: t = a + period * n
        self._next_fit = None
        self.resets = getattr(self, "resets", -1) + 1

    def unwrap(self, raw):
        raw = int(raw)
        if self._last_raw is not None:
            if raw < self._last_raw - 2 ** 31:
                self._wrap += 2 ** 32
            elif raw < self._last_raw - 1000:          # counter restarted (sensor reboot)
                self.reset()
        self._last_raw = raw
        return raw + self._wrap

    def stamp(self, raw_counter, t_recv):
        n = self.unwrap(raw_counter)
        t_recv = float(t_recv)
        self._n.append(n)
        self._t.append(t_recv)
        while self._t and self._t[0] < t_recv - self.window_s:
            self._n.popleft()
            self._t.popleft()
        candidate = t_recv - self.period * n
        if self.offset is None or candidate < self.offset:
            self.offset = candidate          # the envelope only moves down between refits
        if self._next_fit is None:
            self._next_fit = t_recv + self.refit_s
        elif t_recv >= self._next_fit and len(self._n) > 50:
            self._refit()
            self._next_fit = t_recv + self.refit_s
        return self.offset + self.period * n

    def _refit(self):
        n = np.fromiter(self._n, float)
        t = np.fromiter(self._t, float)
        n0 = n[0]
        A = np.column_stack([np.ones_like(n), n - n0])
        coef, *_ = np.linalg.lstsq(A, t, rcond=None)
        period = coef[1]
        lo, hi = self.nominal_period * (1 - self.max_rate_error), self.nominal_period * (1 + self.max_rate_error)
        if lo <= period <= hi:
            self.period = float(period)
        # lower envelope of the arrivals with that slope
        self.offset = float(np.min(t - self.period * n))

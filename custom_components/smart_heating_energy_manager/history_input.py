"""Convert aligned historical samples to calibration intervals.

Timestamp units are Unix seconds; temperature series are in Celsius and
energy counters in kWh. Counter input for fuel generators is useful heat,
not raw fuel energy. Never treat missing samples as zero.
"""
from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite
from .calibration import Interval

@dataclass(frozen=True)
class Sample:
    timestamp: float
    value: float | None

class Series:
    def __init__(self, samples):
        self.samples = sorted(samples, key=lambda s:s.timestamp)
        self.times = [s.timestamp for s in self.samples]

    def value_at(self, timestamp, max_age):
        idx = bisect_right(self.times,timestamp)-1
        if idx < 0 or timestamp-self.times[idx] > max_age:
            return None
        value = self.samples[idx].value
        return value if value is not None and isfinite(value) else None

    def counter_delta(self, start, end, max_age):
        a = self.value_at(start,max_age)
        b = self.value_at(end,max_age)
        if a is None or b is None or a < 0 or b < a:
            return None
        previous = a
        for s in self.samples[bisect_right(self.times,start):bisect_right(self.times,end)]:
            if s.value is None or not isfinite(s.value) or s.value < previous:
                return None
            previous = s.value
        return b-a

    def average(self, start, end, max_age):
        value = self.value_at(start,max_age)
        if value is None:
            return None
        pos = start
        total = 0.
        for s in self.samples[bisect_right(self.times,start):bisect_right(self.times,end)]:
            if self.value_at(s.timestamp,max_age) is None or s.timestamp-pos > max_age:
                return None
            total += value*(s.timestamp-pos)
            value,pos = s.value,s.timestamp
        if self.value_at(end,max_age) is None or end-pos > max_age:
            return None
        return (total+value*(end-pos))/(end-start)

class MeanSeries:
    """Fixed-membership mean: every thermometer must cover the interval."""
    def __init__(self, series):
        self.series=tuple(series)

    def value_at(self,timestamp,max_age):
        values=[s.value_at(timestamp,max_age) for s in self.series]
        return sum(values)/len(values) if values and all(v is not None for v in values) else None

    def average(self,start,end,max_age):
        values=[s.average(start,end,max_age) for s in self.series]
        return sum(values)/len(values) if values and all(v is not None for v in values) else None

class RateSeries(Series):
    """Integrate a recorded rate in kW, or a user-defined rate mapped from state."""
    def counter_delta(self, start, end, max_age):
        avg = self.average(start,end,max_age)
        return None if avg is None or avg < 0 else avg*(end-start)/3600

class ConfirmedOffSeries(Series):
    """Bounded OFF evidence from a change-only state history.

    A long unchanged OFF period is usable only between recorded OFF
    observations. Unknown
    or active states interrupt that evidence. Never extrapolate past
    the final observation beyond the ordinary freshness limit.
    """
    def counter_delta(self,start,end,max_age):
        if end<=start:
            return None
        left=bisect_right(self.times,start)-1
        if left<0 or self.samples[left].value!=0:
            return None
        right=bisect_right(self.times,end)
        if any(s.value!=0 for s in self.samples[left:right]):
            return None
        last=self.samples[right-1]
        if end-last.timestamp<=max_age and start-self.samples[left].timestamp<=max_age:
            return 0.
        if right<len(self.samples) and self.samples[right].value==0:
            return 0.
        if last.timestamp>=end:
            return 0.
        return None

class AlternativeSeries:
    """Choose one valid source per interval; never add overlapping meters.

    Primary source wins when available. Missing data remain missing.
    """
    def __init__(self, alternatives):
        self.alternatives=tuple(alternatives)

    def counter_delta(self,start,end,max_age):
        for series in self.alternatives:
            value=series.counter_delta(start,end,max_age)
            if value is not None:
                return value
        return None

def build_intervals(indoor,outdoor,counters,start,end,step_seconds=3600,max_age_seconds=7200):
    """Use complete intervals only; counters is a sequence of (kind, Series)."""
    if not all(isfinite(v) for v in (start,end,step_seconds,max_age_seconds)) or step_seconds <= 0 or max_age_seconds <= 0:
        raise ValueError("Invalid history interval")
    if not counters or any(kind not in ("fuel","heat_pump","resistance") for kind,_ in counters):
        return []
    result = []
    while start+step_seconds <= end:
        stop=start+step_seconds
        a=indoor.value_at(start,max_age_seconds)
        b=indoor.value_at(stop,max_age_seconds)
        t=outdoor.average(start,stop,max_age_seconds)
        totals={"fuel":0.,"heat_pump":0.,"resistance":0.}
        valid=all(v is not None for v in (a,b,t,indoor.average(start,stop,max_age_seconds)))
        for kind,series in counters:
            energy=series.counter_delta(start,stop,max_age_seconds)
            if energy is None:
                valid=False
                break
            totals[kind]+=energy
        if valid:
            result.append(Interval(step_seconds/3600,a,b,t,totals["fuel"],totals["heat_pump"],totals["resistance"]))
        start=stop
    return result


def recent_counter_power(samples, now, max_age=7200, min_interval=1800):
    """Mean power between actual recorded observations, not an instantaneous reading.

    Reject resets, invalid samples, stale endpoints and unchanged counters:
    a quantized cloud counter that has not advanced cannot prove zero input.
    """
    series=Series(samples)
    if not series.samples:
        return None
    end=series.samples[-1]
    if not 0<=now-end.timestamp<=max_age or end.value is None or not isfinite(end.value):
        return None
    for start in reversed(series.samples[:-1]):
        duration=end.timestamp-start.timestamp
        if duration>max_age:
            break
        if duration<min_interval:
            continue
        energy=series.counter_delta(start.timestamp,end.timestamp,max_age)
        if energy is None:
            return None
        if energy>0:
            return {"power_w":energy*3600000/duration,"interval_minutes":duration/60,"end_timestamp":end.timestamp}
    return None

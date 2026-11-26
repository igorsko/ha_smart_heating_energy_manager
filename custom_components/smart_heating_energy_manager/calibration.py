"""Offline identification of a first-order building thermal model.

Inputs are interval-average measurements, not instantaneous samples.
No actuator control. Estimates are conditional on omitted heat gains.
"""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Interval:
    hours: float
    indoor_start: float
    indoor_end: float
    outdoor: float
    stove_kwh: float
    hp_kwh: float
    resistance_kwh: float

@dataclass(frozen=True)
class Fit:
    loss_w_k: float
    capacity_kwh_k: float
    cop: float
    rmse_kw: float
    samples: int

def fit(intervals):
    """Fit H, C and COP by scaled least squares; reject weak identification.

    Balance: H*deltaT + C*dT/dt - COP*P_hp = P_stove + P_resistance.
    H is in kW/K. Zero Celsius is valid. Invalid intervals are skipped.
    """
    rows, targets = [], []
    for s in intervals:
        vals = (s.hours, s.indoor_start, s.indoor_end, s.outdoor,
                s.stove_kwh, s.hp_kwh, s.resistance_kwh)
        if not all(math.isfinite(x) for x in vals):
            continue
        if not .25 <= s.hours <= 6 or min(vals[4:]) < 0:
            continue
        if not all(-60 <= x <= 70 for x in vals[1:4]):
            continue
        delta = (s.indoor_start + s.indoor_end) / 2 - s.outdoor
        rate = (s.indoor_end - s.indoor_start) / s.hours
        if abs(rate) > 4:
            continue
        rows.append([delta, rate, -s.hp_kwh / s.hours])
        targets.append((s.stove_kwh + s.resistance_kwh) / s.hours)
    if len(rows) < 24:
        return None
    scales = [math.sqrt(sum(r[i]**2 for r in rows)) for i in range(3)]
    if min(scales) < 1e-8:
        return None
    normalized = [[r[i]/scales[i] for i in range(3)] for r in rows]
    a = [[sum(r[i]*r[j] for r in normalized) for j in range(3)] +
         [sum(r[i]*y for r,y in zip(normalized, targets))] for i in range(3)]
    for i in range(3):
        pivot = max(range(i,3), key=lambda k: abs(a[k][i]))
        a[i],a[pivot] = a[pivot],a[i]
        p = a[i][i]
        if abs(p) < .02:
            return None
        a[i] = [v/p for v in a[i]]
        for j in range(3):
            if j != i:
                factor = a[j][i]
                a[j] = [v-factor*w for v,w in zip(a[j],a[i])]
    h,c,cop = [a[i][3]/scales[i] for i in range(3)]
    if not (.01 <= h <= 5 and .1 <= c <= 200 and 1 <= cop <= 8):
        return None
    rmse = math.sqrt(sum((sum(v*w for v,w in zip(r,(h,c,cop)))-y)**2
                         for r,y in zip(rows,targets))/len(rows))
    return Fit(h*1000,c,cop,rmse,len(rows))

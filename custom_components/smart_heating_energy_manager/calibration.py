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
    cop: float | None
    rmse_kw: float
    samples: int
    cop_source: str = "estimated"

@dataclass(frozen=True)
class CalibrationSettings:
    min_hours: float = .25
    max_hours: float = 6
    min_temperature: float = -60
    max_temperature: float = 70
    max_rate: float = 4
    min_samples: int = 24
    min_pivot: float = .02
    min_loss_w_k: float = 10
    max_loss_w_k: float = 5000
    min_capacity: float = .1
    max_capacity: float = 200
    min_cop: float = 1
    max_cop: float = 8
    max_rmse_kw: float = 2

    def __post_init__(self):
        pairs = ((self.min_hours,self.max_hours),
                 (self.min_temperature,self.max_temperature),
                 (self.min_loss_w_k,self.max_loss_w_k),
                 (self.min_capacity,self.max_capacity),
                 (self.min_cop,self.max_cop))
        if any(not math.isfinite(a) or not math.isfinite(b) or a >= b for a,b in pairs):
            raise ValueError("Invalid calibration bounds")
        if (min(self.min_hours,self.min_loss_w_k,self.min_capacity,self.min_cop) <= 0
                or not isinstance(self.min_samples,int) or self.min_samples < 3
                or not all(math.isfinite(x) and x > 0 for x in
                           (self.max_rate,self.min_pivot,self.max_rmse_kw))
                or self.min_pivot > 1):
            raise ValueError("Invalid calibration settings")

def fit(intervals, settings=None, known_cop=None):
    """Fit H, C and COP by scaled least squares; reject weak identification.

    Balance: H*deltaT + C*dT/dt - COP*P_hp = P_stove + P_resistance.
    H is in kW/K. Zero Celsius is valid. Invalid intervals are skipped.
    """
    cfg = settings or CalibrationSettings()
    if known_cop is not None and (not math.isfinite(known_cop) or not cfg.min_cop <= known_cop <= cfg.max_cop):
        return None
    rows, targets = [], []
    hp_present = False
    for s in intervals:
        vals = (s.hours, s.indoor_start, s.indoor_end, s.outdoor,
                s.stove_kwh, s.hp_kwh, s.resistance_kwh)
        if not all(math.isfinite(x) for x in vals):
            continue
        if not cfg.min_hours <= s.hours <= cfg.max_hours or min(vals[4:]) < 0:
            continue
        if not all(cfg.min_temperature <= x <= cfg.max_temperature for x in vals[1:4]):
            continue
        delta = (s.indoor_start + s.indoor_end) / 2 - s.outdoor
        rate = (s.indoor_end - s.indoor_start) / s.hours
        if abs(rate) > cfg.max_rate:
            continue
        hp_present |= s.hp_kwh > 0
        rows.append([delta, rate, -s.hp_kwh / s.hours])
        targets.append((s.stove_kwh + s.resistance_kwh) / s.hours)
    if len(rows) < cfg.min_samples:
        return None
    estimate_cop = hp_present and known_cop is None
    if not estimate_cop:
        targets = [y-r[2]*(known_cop or 0) for r,y in zip(rows,targets)]
        rows = [r[:2] for r in rows]
    n = 3 if estimate_cop else 2
    if max(targets,default=0) <= 0:
        return None
    scales = [math.sqrt(sum(r[i]**2 for r in rows)) for i in range(n)]
    if min(scales) < 1e-8:
        return None
    normalized = [[r[i]/scales[i] for i in range(n)] for r in rows]
    a = [[sum(r[i]*r[j] for r in normalized) for j in range(n)] +
         [sum(r[i]*y for r,y in zip(normalized, targets))] for i in range(n)]
    for i in range(n):
        pivot = max(range(i,n), key=lambda k: abs(a[k][i]))
        a[i],a[pivot] = a[pivot],a[i]
        p = a[i][i]
        if abs(p) < cfg.min_pivot:
            return None
        a[i] = [v/p for v in a[i]]
        for j in range(n):
            if j != i:
                factor = a[j][i]
                a[j] = [v-factor*w for v,w in zip(a[j],a[i])]
    params = [a[i][n]/scales[i] for i in range(n)]
    h,c = params[:2]
    cop = params[2] if estimate_cop else known_cop if hp_present else None
    if not (cfg.min_loss_w_k <= h*1000 <= cfg.max_loss_w_k and cfg.min_capacity <= c <= cfg.max_capacity and (cop is None or cfg.min_cop <= cop <= cfg.max_cop)):
        return None
    rmse = math.sqrt(sum((sum(v*w for v,w in zip(r,params))-y)**2
                         for r,y in zip(rows,targets))/len(rows))
    if rmse > cfg.max_rmse_kw:
        return None
    return Fit(h*1000,c,cop,rmse,len(rows),"estimated" if estimate_cop else "configured" if hp_present else "not_applicable")


def validate_holdout(intervals, known_cop=None, settings=None):
    """Chronological out-of-sample one-step thermal error; never fit on holdout."""
    cfg = settings or CalibrationSettings()
    samples = list(intervals)
    count = max(12, len(samples)//4)
    if len(samples)-count < cfg.min_samples:
        return {"status":"insufficient_data"}
    model = fit(samples[:-count], cfg, known_cop)
    if model is None:
        return {"status":"unidentifiable_training"}
    errors, baseline = [], []
    h = model.loss_w_k/1000
    c = model.capacity_kwh_k
    for s in samples[-count:]:
        values = (s.hours,s.indoor_start,s.indoor_end,s.outdoor,s.stove_kwh,s.hp_kwh,s.resistance_kwh)
        if not all(math.isfinite(v) for v in values) or not cfg.min_hours <= s.hours <= cfg.max_hours or min(values[4:]) < 0:
            continue
        if not all(cfg.min_temperature <= v <= cfg.max_temperature for v in values[1:4]) or abs(s.indoor_end-s.indoor_start)/s.hours > cfg.max_rate:
            continue
        if s.hp_kwh > 0 and model.cop is None:
            continue
        heat = (s.stove_kwh+s.resistance_kwh+s.hp_kwh*(model.cop or 0))/s.hours
        decay = math.exp(-h*s.hours/c)
        predicted = s.outdoor+(s.indoor_start-s.outdoor)*decay+heat*(-math.expm1(-h*s.hours/c))/h
        errors.append(predicted-s.indoor_end)
        baseline.append(abs(s.indoor_end-s.indoor_start))
    if len(errors)<12:
        return {"status":"insufficient_holdout","samples":len(errors)}
    return {"status":"evaluated","training_samples":model.samples,"samples":len(errors),
            "mae_c":sum(abs(e) for e in errors)/len(errors),
            "rmse_c":math.sqrt(sum(e*e for e in errors)/len(errors)),
            "bias_c":sum(errors)/len(errors),
            "baseline_mae_c":sum(baseline)/len(baseline),
            "method":"chronological_one_step_measured_inputs"}

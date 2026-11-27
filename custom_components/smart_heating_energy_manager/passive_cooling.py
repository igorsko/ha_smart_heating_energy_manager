"""Read-only apparent thermal time constant from confirmed nighttime OFF periods."""
from dataclasses import dataclass
from math import exp, log, isfinite
from statistics import median

@dataclass(frozen=True)
class CoolingSample:
    timestamp: float
    hours: float
    indoor_start: float
    indoor_end: float
    outdoor: float

def collect(indoor,outdoor,off_series,sun,start,end,step,age):
    """Require all generators OFF for two preceding hours and the interval.
    Require recorded nighttime throughout that same window.
    """
    if not off_series or sun is None or step<=0:
        return []
    rows=[]
    while start+step<=end:
        stop=start+step
        pre=start-7200
        if all(s.counter_delta(pre,stop,age)==0 for s in (*off_series,sun)):
            a,b,t=indoor.value_at(start,age),indoor.value_at(stop,age),outdoor.average(start,stop,age)
            if all(v is not None and isfinite(v) for v in (a,b,t,indoor.average(start,stop,age))) and a-t>=3 and b>t:
                rows.append(CoolingSample(start,step/3600,a,b,t))
        start=stop
    return rows

def _tau(rows):
    # Median of positive apparent decay rates; reject implausible extremes.
    rates=[-log((s.indoor_end-s.outdoor)/(s.indoor_start-s.outdoor))/s.hours for s in rows if s.indoor_end<s.indoor_start and s.indoor_end>s.outdoor and s.hours>0]
    if len(rates)<max(8,len(rows)//2):
        return None
    rate=median(rates)
    return 1/rate if 1/240<=rate<=1/2 else None

def analyze(rows):
    rows=sorted(rows,key=lambda s:s.timestamp)
    result={"status":"insufficient_data","samples":len(rows),"method":"nighttime_confirmed_off","settling_hours":2}
    if len(rows)<24:
        return result
    # Split chronologically with a gap to avoid adjacent boundary overlap.
    split=len(rows)*2//3
    training=rows[:split]
    validation=[s for s in rows[split:] if s.timestamp>=training[-1].timestamp+training[-1].hours*3600+7200]
    result.update(training_samples=len(training),validation_samples=len(validation))
    if len(validation)<6:
        return result
    tau=_tau(training)
    if tau is None:
        return {**result,"status":"unidentifiable"}
    errors=[s.outdoor+(s.indoor_start-s.outdoor)*exp(-s.hours/tau)-s.indoor_end for s in validation]
    mae=sum(abs(e) for e in errors)/len(errors)
    baseline=sum(abs(s.indoor_start-s.indoor_end) for s in validation)/len(validation)
    # Keep training-only estimate; no holdout leakage.
    return {**result,"status":"validated" if mae<=.5 and mae<baseline else "poor_validation",
            "tau_hours":tau,"mae_c":mae,"baseline_mae_c":baseline,
            "bias_c":sum(errors)/len(errors),
            "curve":[{"hours":h,"remaining_fraction":exp(-h/tau)} for h in (0,1,2,4,8,12,24,48)]}

"""Diagnostic COP curve, conditional on a separately fitted building model."""
from math import exp, expm1, isfinite, sqrt
from statistics import median
from .calibration import fit

def estimate(intervals):
    rows=list(intervals)
    count=max(12,len(rows)//4)
    if len(rows)-count<36:
        return {"status":"insufficient_data","scope":"aggregate"}
    train,test=rows[:-count],rows[-count:]
    # Identify H and C without using heat-pump observations.
    model=fit([s for s in train if s.hp_kwh==0])
    if model is None:
        return {"status":"independent_model_unavailable","scope":"aggregate"}
    h,c=model.loss_w_k/1000,model.capacity_kwh_k
    def usable(s):
        return all(isfinite(v) for v in (s.hours,s.indoor_start,s.indoor_end,s.outdoor,s.hp_kwh,s.stove_kwh,s.resistance_kwh)) and .25<=s.hours<=6 and s.hp_kwh>=.15 and s.stove_kwh==0 and s.resistance_kwh==0
    def apparent(s):
        decay=exp(-h*s.hours/c)
        gain=-expm1(-h*s.hours/c)/h
        return (s.indoor_end-s.outdoor-(s.indoor_start-s.outdoor)*decay)/gain*s.hours/s.hp_kwh
    bins={}
    for s in train:
        if usable(s):
            bins.setdefault(int(s.outdoor//5)*5+2.5,[]).append(apparent(s))
    points=sorted((t,median(v)) for t,v in bins.items() if len(v)>=6 and 1<=median(v)<=8)
    if len(points)<2:
        return {"status":"insufficient_temperature_range","scope":"aggregate","bins":len(points)}
    def interpolate(t):
        for (a,x),(b,y) in zip(points,points[1:]):
            if a<=t<=b and b-a<=5:
                return x+(y-x)*(t-a)/(b-a)
        return None
    constant=median([v for _,v in points])
    errors,baseline=[],[]
    for s in test:
        if not usable(s):
            continue
        cop=interpolate(s.outdoor)
        if cop is None:
            continue
        decay=exp(-h*s.hours/c)
        free=s.outdoor+(s.indoor_start-s.outdoor)*decay
        gain=-expm1(-h*s.hours/c)/h*s.hp_kwh/s.hours
        errors.append(free+cop*gain-s.indoor_end)
        baseline.append(abs(free+constant*gain-s.indoor_end))
    n=len(errors)
    result={"status":"insufficient_holdout","scope":"aggregate","points":points,"samples":n,"training_samples":sum(map(len,bins.values()))}
    if n<12:
        return result
    mae=sum(map(abs,errors))/n
    rmse=sqrt(sum(e*e for e in errors)/n)
    bias=sum(errors)/n
    reference=sum(baseline)/n
    return {**result,"status":"validated" if mae<=.5 and rmse<=.75 and abs(bias)<=.3 and mae<reference else "poor_validation","mae_c":mae,"rmse_c":rmse,"bias_c":bias,"constant_baseline_mae_c":reference,"method":"independent_non_hp_model_chronological_holdout"}

def shared_sources(devices):
    """Only detect identical entity IDs; never infer physical outdoor units."""
    owners={}
    for key,g in devices.items():
        if g.get("kind")!="heat_pump":
            continue
        for entity in set([g.get("energy_entity"),g.get("power_entity"),*g.get("energy_alternatives",[])]):
            if entity:
                owners.setdefault(entity,[]).append(key)
    return {e:sorted(ids) for e,ids in owners.items() if len(ids)>1}

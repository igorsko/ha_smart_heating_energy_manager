"""Diagnostic solar gain proxy, never a direct irradiance measurement."""
from math import exp, expm1, isfinite, sqrt
from .calibration import fit

def estimate(night, daylight):
    """Fit H/C on nighttime inputs, then fit solar gain on earlier daylight.
    Daylight rows are (Interval, gross PV kWh); all sets chronological.
    """
    rows=list(daylight)
    ntest=max(12,len(rows)//4)
    if len(rows)-ntest<24:
        return {"status":"insufficient_data","samples":len(rows)}
    train,test=rows[:-ntest],rows[-ntest:]
    # Night rows carry timestamp; do not use future thermal observations.
    model=fit([s for stamp,s in night if stamp<test[0][0] and s.hp_kwh==0])
    if model is None:
        return {"status":"independent_model_unavailable","samples":len(rows)}
    h,c=model.loss_w_k/1000,model.capacity_kwh_k
    def terms(row):
        _,s,pv=row
        vals=(s.hours,s.indoor_start,s.indoor_end,s.outdoor,s.stove_kwh,s.hp_kwh,s.resistance_kwh,pv)
        if not all(isfinite(v) for v in vals) or not .25<=s.hours<=6 or pv<.05 or s.hp_kwh!=0 or min(s.stove_kwh,s.resistance_kwh)<0:
            return None
        gain=-expm1(-h*s.hours/c)/h
        base=s.outdoor+(s.indoor_start-s.outdoor)*exp(-h*s.hours/c)+gain*(s.stove_kwh+s.resistance_kwh)/s.hours
        return gain*pv/s.hours,s.indoor_end-base
    a=[v for row in train if (v:=terms(row)) is not None]
    z=[v for row in test if (v:=terms(row)) is not None]
    if len(a)<24 or len(z)<12:
        return {"status":"insufficient_usable_samples","training_samples":len(a),"samples":len(z)}
    den=sum(x*x for x,y in a)
    if den<=1e-8:
        return {"status":"unidentifiable"}
    factor=sum(x*y for x,y in a)/den
    if not 0<factor<=10:
        return {"status":"unidentifiable","training_samples":len(a),"samples":len(z)}
    errors=[x*factor-y for x,y in z]
    mae=sum(map(abs,errors))/len(z)
    rmse=sqrt(sum(e*e for e in errors)/len(z))
    bias=sum(errors)/len(z)
    baseline=sum(abs(y) for x,y in z)/len(z)
    return {"status":"validated" if mae<=.5 and rmse<=.75 and abs(bias)<=.3 and mae<baseline else "poor_validation","factor":factor,"training_samples":len(a),"samples":len(z),"mae_c":mae,"rmse_c":rmse,"bias_c":bias,"baseline_mae_c":baseline,"method":"nighttime_non_hp_fit_pv_proxy_holdout"}

def collect(indoor,outdoor,counters,pv,sun,start,end,step,age):
    from .history_input import build_intervals
    night,day=[],[]
    while start+step<=end:
        stop=start+step
        rows=build_intervals(indoor,outdoor,counters,start,stop,step,age)
        if rows:
            if sun.counter_delta(start,stop,age)==0:
                night.append((start,rows[0]))
            elif pv:
                energy=pv.counter_delta(start,stop,age)
                if energy is not None and energy>=.05:
                    day.append((start,rows[0],energy))
        start=stop
    return night,day

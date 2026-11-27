"""Prospective forecast verification; never reconstruct a forecast from future data."""
from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt

def number(value):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and isfinite(value) else None

def timestamp(value):
    try:
        t=datetime.fromisoformat(value)
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError,ValueError):
        return None

def issue(rows, now, reference, forecast, thermal, indoor, solar=(), pv_reference=None):
    """Freeze the first forecast for each target and series, with >=45 min lead."""
    keys={(r["kind"],r["target"],r["reference"]) for r in rows}
    def add(kind,target,value,baseline=None,ref=reference):
        if target is None or target-now<timedelta(minutes=45) or target-now>timedelta(hours=24) or number(value) is None:
            return
        key=(kind,target.isoformat(),ref)
        if key in keys:
            return
        keys.add(key)
        rows.append({"kind":kind,"target":key[1],"reference":ref,"issued":now.isoformat(),"prediction":value,"baseline":number(baseline),"status":"pending"})
    for row in forecast:
        add("outdoor",timestamp(row.get("datetime")),row.get("temperature_c"))
    # Conditional scenario, not a promise that the recommended plan is followed.
    for row in thermal.get("baseline",[]):
        start=timestamp(row.get("datetime"))
        if start:
            add("indoor_scenario",start+timedelta(hours=1),row.get("end_c"),indoor)
    for row in solar:
        start=timestamp(row.get("datetime"))
        value=number(row.get("pv_kwh"))
        if pv_reference and start and start-now>=timedelta(minutes=45) and value is not None and value>=0:
            add("pv_hour",start+timedelta(hours=1),value,ref=pv_reference)
    return rows

def observe(rows, now, reference, indoor, outdoor, tolerance_minutes=10):
    """Use only observations made at or shortly after the forecast target."""
    for row in rows:
        if row.get("status")!="pending" or row.get("kind")=="pv_hour":
            continue
        target=timestamp(row.get("target"))
        if target is None or row.get("reference")!=reference:
            row["status"]="expired"
        elif now>=target:
            value=number(outdoor if row["kind"]=="outdoor" else indoor)
            if now-target>timedelta(minutes=tolerance_minutes):
                row["status"]="expired"
            elif value is not None:
                row.update(status="observed",actual=value,observed=now.isoformat())
    cutoff=now-timedelta(days=30)
    return [r for r in rows if (timestamp(r.get("target")) or cutoff)>=cutoff][-2000:]

def observe_pv(rows,now,reference,actuals):
    for row in rows:
        if row.get("kind")!="pv_hour" or row.get("status")!="pending":
            continue
        target=timestamp(row.get("target"))
        if target is None or row.get("reference")!=reference:
            row["status"]="expired"
        elif target<=now:
            actual=number(actuals.get(row["target"]))
            if actual is not None and actual>=0:
                row.update(status="observed",actual=actual,observed=now.isoformat())
            elif now-target>timedelta(hours=6):
                row["status"]="expired"
    return rows

def summarize(rows, reference, pv_reference=None):
    result={}
    for kind in ("outdoor","indoor_scenario","pv_hour"):
        selected=[r for r in rows if r.get("kind")==kind and r.get("reference")== (pv_reference if kind=="pv_hour" else reference)]
        observed=[r for r in selected if r.get("status")=="observed" and number(r.get("actual")) is not None and number(r.get("prediction")) is not None]
        errors=[r["prediction"]-r["actual"] for r in observed]
        n=len(errors)
        baseline=[abs(r["baseline"]-r["actual"]) for r in observed if number(r.get("baseline")) is not None]
        result[kind]={"samples":n,"pending":sum(r["status"]=="pending" for r in selected),"expired":sum(r["status"]=="expired" for r in selected),"mae_c":sum(map(abs,errors))/n if n else None,"rmse_c":sqrt(sum(e*e for e in errors)/n) if n else None,"bias_c":sum(errors)/n if n else None,"baseline_mae_c":sum(baseline)/len(baseline) if baseline else None,"status":"evaluated" if n>=24 else "collecting","conditional":kind=="indoor_scenario"}
        metric=result[kind]
        metric["unit"]="kWh" if kind=="pv_hour" else "°C"
        metric["mae"]=metric["mae_c"]
        metric["rmse"]=metric["rmse_c"]
        metric["bias"]=metric["bias_c"]
        if kind=="pv_hour":
            for key in ("mae_c","rmse_c","bias_c","baseline_mae_c"):
                metric.pop(key,None)
        metric["lead_hours"]={}
        for lo,hi in ((0,6),(6,12),(12,18),(18,25)):
            group=[]
            for row in observed:
                target,issued=timestamp(row.get("target")),timestamp(row.get("issued"))
                if target and issued and lo<=(target-issued).total_seconds()/3600<hi:
                    group.append(row["prediction"]-row["actual"])
            if group:
                metric["lead_hours"][f"{lo}-{hi}"]={"samples":len(group),"mae":sum(map(abs,group))/len(group)}
    return result

def pv_identity(sources):
    """Bind comparison to explicitly configured production counters and providers."""
    import hashlib
    import json
    solar=sources.get("solar",[])
    meters=[s.get("stat_energy_from") for s in solar]
    if not meters or any(not isinstance(e,str) or not e.startswith("sensor.") for e in meters) or len(set(meters))!=len(meters):
        return None,[]
    providers=sorted({i for s in solar for i in (s.get("config_entry_solar_forecast") or [])})
    if not providers:
        return None,[]
    return hashlib.sha256(json.dumps([sorted(meters),providers]).encode()).hexdigest(),sorted(meters)

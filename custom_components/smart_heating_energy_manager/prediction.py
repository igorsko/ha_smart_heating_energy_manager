"""Advisory hourly heat dispatch with explicit forecast and tariff assumptions."""
from math import isfinite
from datetime import datetime

def number(value):
    try:
        x=float(value)
        return x if isfinite(x) else None
    except (TypeError,ValueError):
        return None

def kw(value,unit):
    x=number(value)
    return x*{"W":.001,"kW":1,"MW":1000}[unit] if x is not None and unit in ("W","kW","MW") else None

def plan(hours, loss, target, generators, price):
    """Steady-state hourly dispatch; no thermal storage or future PV assumptions."""
    if loss is None or loss<=0 or target is None:
        return []
    rows=[]
    for hour in hours[:24]:
        outside=number(hour.get("temperature_c"))
        if outside is None:
            continue
        demand=max(0,target-outside)*loss/1000
        choices=[]
        for g in generators:
            if not g.enabled or g.capacity_kw<demand:
                continue
            cost=g.thermal_cost(price)
            if cost is not None:
                choices.append((cost,g.identifier))
        choice=min(choices) if choices and demand>0 else None
        rows.append({"datetime":hour["datetime"],"outdoor_c":outside,"heat_kw":round(demand,3),
            "generator":choice[1] if choice else None,"cost_per_hour":round(choice[0]*demand,4) if choice else (0 if demand==0 else None)})
    return rows

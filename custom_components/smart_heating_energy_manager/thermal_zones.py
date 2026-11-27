"""Optional thermal parameters and manufacturer/user COP curves."""
from math import isfinite

def parse_curve(text):
    points={}
    for line in text.splitlines():
        if not line.strip():
            continue
        a,sep,b=line.partition("=")
        if not sep:
            raise ValueError("Expected temperature=COP")
        t,c=float(a),float(b)
        if not isfinite(t) or not isfinite(c) or not -60<=t<=70 or not 0<c<=15 or t in points:
            raise ValueError("Invalid COP curve point")
        points[t]=c
    if points and len(points)<2:
        raise ValueError("At least two COP points required")
    return sorted(points.items())

def cop_at(points,outdoor,fallback):
    if outdoor is None or not isfinite(outdoor) or not points or not points[0][0]<=outdoor<=points[-1][0]:
        return fallback,"manual"
    for (a,x),(b,y) in zip(points,points[1:]):
        if a<=outdoor<=b:
            return x+(y-x)*(outdoor-a)/(b-a),"configured_curve"
    return fallback,"manual"

def zone_demand(indoor,outdoor,loss,target=None):
    values=(indoor,outdoor,loss)
    if any(v is None or not isinstance(v,(int,float)) or not isfinite(v) for v in values) or loss<=0:
        return None
    # Steady heat loss at current temperature, not a recovery-power forecast.
    return max(0,indoor-outdoor)*loss/1000

def zone_status(zone,indoor,outdoor):
    target=zone.get("target_c")
    demand=zone_demand(indoor,outdoor,zone.get("loss_w_k"))
    return {"temperature_c":indoor,"target_c":target,"heat_demand_kw":demand,
            "below_target":indoor<target if indoor is not None and target is not None else None,
            "model_source":"manual" if demand is not None else "unconfigured"}

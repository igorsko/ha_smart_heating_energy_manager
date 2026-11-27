"""Discover possible electricity price indices without silently changing a tariff."""
from math import isfinite

def index_value(value, unit):
    try:
        n=float(value)
    except (ValueError,TypeError):
        return None
    units={"eur/kwh":1,"€/kwh":1,"eur/mwh":.001,"€/mwh":.001,"eur/wh":1000,"€/wh":1000}
    factor=units.get(str(unit).strip().lower().replace(" ",""))
    return n*factor if factor is not None and isfinite(n) else None

def candidates(entries,get_state):
    result=[]
    for e in entries:
        if not e.entity_id.startswith("sensor.") or getattr(e,"disabled_by",None):
            continue
        s=get_state(e.entity_id)
        if not s:
            continue
        name=(e.entity_id+" "+str(getattr(e,"platform",""))+" "+str(s.attributes.get("friendly_name",""))).lower()
        if index_value(s.state,s.attributes.get("unit_of_measurement")) is not None and any(x in name for x in ("pun","prezzo zonale","day_ahead","day ahead","spot price","electricity price")):
            result.append(e.entity_id)
    return sorted(set(result))

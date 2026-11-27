"""Explicit thermal groups: no inferred grouping from shared equipment."""
from .temperature_zones import thermometer, average_temperature

def group_name(value):
    return " ".join(str(value or "").split())[:80]

def groups(zones,read):
    result={}
    for area,z in zones.items():
        name=group_name(z.get("thermal_group"))
        if z.get("outdoor") or not name:
            continue
        item=result.setdefault(name.casefold(),{"name":name,"areas":[],"thermometers":set(),"sources":set()})
        item["areas"].append(area)
        if entity:=thermometer(z):
            item["thermometers"].add(entity)
        item["sources"].update(z.get("sources",[]) if z.get("confirmed") else z.get("source_candidates",[]))
    for item in result.values():
        item["thermometers"]=sorted(item["thermometers"])
        item["sources"]=sorted(item["sources"])
        item["temperature_c"],item["sensor_count"]=average_temperature(item["thermometers"],read)
    return result

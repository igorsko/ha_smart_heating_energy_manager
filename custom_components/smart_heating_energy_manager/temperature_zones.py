"""Resolve indoor/outdoor sensors without counting a shared thermometer twice."""
from math import isfinite
import unicodedata

def is_outdoor(area, zone, outdoor=None):
    if "outdoor" in zone:
        return bool(zone["outdoor"])
    name=unicodedata.normalize("NFKD",zone.get("name",area)).casefold().strip()
    return name in {"esterno","esterna","esterni","zona esterna","outdoor","outside","exterior","external","garden","giardino","zunaj","zunanjost"} or bool(outdoor and zone.get("temperature")==outdoor)

def thermometer(zone):
    return zone.get("temperature") or (zone["temperature_candidates"][0] if not zone.get("confirmed") and len(zone.get("temperature_candidates",[]))==1 else None)

def resolve(zones, indoor=None, outdoor=None):
    exterior=[thermometer(z) for k,z in zones.items() if is_outdoor(k,z,outdoor)]
    candidates=set(exterior)-{None}
    outside=outdoor or (next(iter(candidates)) if len(candidates)==1 else None)
    excluded=set(exterior)|{outside,outdoor,None}
    inside=sorted({thermometer(z) for k,z in zones.items() if not is_outdoor(k,z,outdoor)}-excluded)
    if not inside and indoor not in excluded:
        inside=[indoor]
    return inside,outside

def average_temperature(ids,read):
    values=[v for entity in ids if (v:=read(entity)) is not None and isfinite(v)]
    return (sum(values)/len(values) if values else None,len(values))


def reference_config(config,zones):
    indoor,outdoor=resolve(zones,config.get("indoor"),config.get("outdoor"))
    references={}
    groups={}
    for key,z in zones.items():
        entity=thermometer(z)
        if is_outdoor(key,z,outdoor) or entity not in indoor:
            continue
        references["zone:"+key]={"name":z.get("name",key),"kind":"zone","entities":[entity]}
        name=" ".join(str(z.get("thermal_group") or "").split())[:80]
        if name:
            item=groups.setdefault(name.casefold(),{"name":name,"kind":"group","entities":[]})
            if entity not in item["entities"]:
                item["entities"].append(entity)
    references.update({"group:"+k:v for k,v in groups.items()})
    return {**config,"indoor_reference":indoor,"outdoor_reference":outdoor,"cooling_references":references}

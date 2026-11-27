"""Conservative onboarding: never invent technical ratings or meter semantics."""
def merge_basic(old, user, name):
    kind=user["kind"]
    if kind not in ("heat_pump","resistance","fuel"):
        raise ValueError("kind")
    data=dict(old)
    entity=user.get("control_entity") or old.get("control_entity")
    changed=bool(old.get("kind") and (old["kind"]!=kind or (entity and old.get("control_entity") and entity!=old["control_entity"])))
    if changed:
        # Preserve the generator ID, but never transfer meters or technical ratings to another appliance.
        data={"enabled":old.get("enabled",True),"technical_configured":False}
    data.update(name=name,kind=kind)
    if entity:
        data["control_entity"]=entity
    data.setdefault("enabled",True)
    # Legacy complete configurations remain usable; new incomplete ones are monitored only.
    data.setdefault("technical_configured",all(k in old for k in ("efficiency","capacity_kw","fuel_price","fuel_quantity","fuel_energy_kwh")))
    data.setdefault("efficiency",1.0)
    data.setdefault("capacity_kw",1.0)
    data.setdefault("fuel_price",0.0)
    data.setdefault("fuel_quantity",1.0)
    data.setdefault("fuel_energy_kwh",1.0)
    return data

def suggest_sensors(entries, get_state, kind):
    """Only unambiguous same-device candidates; fuel heat semantics require confirmation."""
    if kind=="fuel":
        return {}
    result={}
    for field,klass,units in (("energy_entity","energy",("Wh","kWh","MWh")),("power_entity","power",("W","kW","MW"))):
        matches=[]
        for entry in entries:
            if not entry.entity_id.startswith("sensor."):
                continue
            state=get_state(entry.entity_id)
            if state and state.attributes.get("device_class")==klass and state.attributes.get("unit_of_measurement") in units:
                matches.append(entry.entity_id)
        if len(matches)==1:
            result[field]=matches[0]
    return result

def ready(data):
    return data.get("technical_configured",True)

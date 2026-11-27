"""Explicit provisional parameters; never mutate installation configuration."""
from .model import finite
from .onboarding import ready

def building_estimate(config):
    area=finite(config.get("building_area"))
    if area is None or area<=0:
        return None,None
    # Broad engineering prior, not a building survey.
    profile=config.get("building_profile","medium")
    h,c={"low_loss":(1.2,.04),"medium":(2.5,.075),"high_loss":(4.5,.09)}.get(profile,(2.5,.075))
    return area*h,area*c

def economic_parameters(data):
    kind=data.get("kind")
    if ready(data):
        return dict(data),"configured"
    if kind=="heat_pump":
        return {**data,"efficiency":3.0},"estimated"
    if kind=="resistance":
        return {**data,"efficiency":1.0},"estimated"
    # Fuel type and price cannot be inferred from a generic fuel generator.
    if kind=="fuel" and data.get("fuel_price") and data.get("fuel_quantity") and data.get("fuel_energy_kwh",0)>1 and 0<data.get("efficiency",0)<=1:
        return dict(data),"estimated"
    return None,"missing_fuel_parameters"

def economic_costs(devices,electricity):
    result=[]
    for key,data in devices.items():
        if not data.get("enabled",True):
            continue
        g,origin=economic_parameters(data)
        if not g:
            continue
        eff=finite(g.get("efficiency"))
        if eff is None or eff<=0:
            continue
        if g["kind"]=="fuel":
            p,q,e=map(finite,(g.get("fuel_price"),g.get("fuel_quantity"),g.get("fuel_energy_kwh")))
            cost=p/(q*e*eff) if p is not None and q and e and q>0 and e>0 else None
        else:
            cost=electricity/eff if electricity is not None else None
        if cost is not None:
            result.append({"id":key,"cost":cost,"source":origin})
    return sorted(result,key=lambda x:(x["cost"],x["id"]))

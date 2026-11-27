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

def winnet_parameters(data, entries, read):
    """Read fuel economics from the selected WiNET device only.

    These are provisional economic parameters, not calibrated capacity.
    Never promote an incomplete generator to technical readiness.
    """
    if data.get("kind")!="fuel" or ready(data):
        return dict(data)
    entries=list(entries)
    from .discovery import winnet_siblings
    siblings=winnet_siblings(entries,data)
    if not siblings:
        return dict(data)
    def read_one(suffix, units):
        matches=[e.entity_id for e in siblings if e.entity_id.endswith(suffix) or str(getattr(e,"unique_id","")).endswith(suffix)]
        if len(matches)!=1:
            return None,None
        s=read(matches[0])
        if not s or s.attributes.get("unit_of_measurement") not in units:
            return None,None
        v=finite(s.state)
        return (v,matches[0]) if v is not None and v>0 else (None,None)
    price,price_id=read_one("_pellet_price_per_bag",("EUR","€"))
    mass,mass_id=read_one("_pellet_bag_weight",("kg",))
    if price is None or mass is None:
        return dict(data)
    # Existing positive, non-placeholder manual values retain priority.
    g=dict(data)
    if not finite(g.get("fuel_price")) or g["fuel_price"]<=0:
        g["fuel_price"]=price
        g["fuel_quantity"]=mass
    if not finite(g.get("fuel_energy_kwh")) or g["fuel_energy_kwh"]<=1:
        g["fuel_energy_kwh"]=4.8
    if not finite(g.get("efficiency")) or not 0<g["efficiency"]<1:
        g["efficiency"]=.90
    g["_economic_origin"]="winnet_estimated"
    g["_economic_entities"]={"price":price_id,"mass":mass_id}
    rate,rate_id=read_one("_effective_pellet_consumption",("kg/h",))
    if rate is not None:
        g["_estimated_fuel_rate"]=rate
        g["_economic_entities"]["rate"]=rate_id
    return g

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
            row={"id":key,"cost":cost,"source":g.get("_economic_origin",origin)}
            if g.get("_economic_entities"):
                row["entities"]=g["_economic_entities"]
                row["parameters"]={k:g[k] for k in ("fuel_price","fuel_quantity","fuel_energy_kwh","efficiency")}
                rate=g.get("_estimated_fuel_rate")
                if rate is not None:
                    row["estimated_burning_cost_per_hour"]=rate*p/q
                    row["estimated_burning_heat_kw"]=rate*e*eff
            result.append(row)
    return sorted(result,key=lambda x:(x["cost"],x["id"]))


def declared_capacity(data, entries, read):
    """Resolve explicit rated useful heating output, never electrical input.

    Preserve confirmed configuration. Only same-device, same-integration
    entities may supply a rating; conflicting ratings remain unresolved.
    """
    g=dict(data)
    if ready(g):
        g["_capacity_origin"]="configured"
        return g
    control=next((e for e in entries if e.entity_id==g.get("control_entity")),None)
    if not control:
        return g
    values=[]
    def add(value,unit,entity):
        n=finite(value)
        if n is not None and unit in ("W","kW"):
            n=n/1000 if unit=="W" else n
            if 0<n<=100:
                values.append((n,entity))
    state=read(control.entity_id)
    if state:
        for field,unit in (("rated_heating_capacity_kw","kW"),("nominal_heating_capacity_kw","kW"),("rated_heat_output_kw","kW"),("rated_heating_capacity_w","W"),("nominal_heating_capacity_w","W"),("rated_heat_output_w","W")):
            add(state.attributes.get(field),unit,control.entity_id)
    suffixes=("_rated_heating_capacity","_nominal_heating_capacity","_rated_heat_output","_nominal_heat_output")
    for e in entries:
        if not control.device_id or e.device_id!=control.device_id or e.platform!=control.platform or getattr(e,"disabled_by",None):
            continue
        if not e.entity_id.startswith("sensor.") or not (e.entity_id.endswith(suffixes) or str(getattr(e,"unique_id","")).endswith(suffixes)):
            continue
        s=read(e.entity_id)
        if s:
            add(s.state,s.attributes.get("unit_of_measurement"),e.entity_id)
    if values and max(v for v,_ in values)-min(v for v,_ in values)<=.01:
        g["capacity_kw"]=min(v for v,_ in values)
        g["_capacity_origin"]="declared"
        g["_capacity_entities"]=sorted({e for _,e in values})
    return g


def advisory_generator(data, identifier, outdoor=None):
    """Build a candidate only with a real declared or configured rating."""
    from .generators import Generator
    from .thermal_zones import parse_curve, cop_at
    if not ready(data) and data.get("_capacity_origin")!="declared":
        return None
    g,origin=economic_parameters(data)
    if not g:
        return None
    try:
        eff=g["efficiency"]
        if g["kind"]=="heat_pump":
            eff,_=cop_at(parse_curve(g.get("cop_curve","")),outdoor,eff)
        return Generator(identifier,g["kind"],eff,g["capacity_kw"],g.get("fuel_price",0),g.get("fuel_quantity",1),g.get("fuel_energy_kwh",1),g.get("enabled",True))
    except (KeyError,ValueError,TypeError):
        return None

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

def effective_cop(data,outdoor=None):
    from .thermal_zones import parse_curve, cop_at
    fallback=data.get('efficiency',3) if ready(data) else 3.
    value,origin=cop_at(parse_curve(data.get('cop_curve','')),outdoor,fallback)
    if origin=='configured_curve':
        return value,origin
    if ready(data):
        return value,'manual'
    if data.get('_learned_cop') is not None:
        return data['_learned_cop'],'learned'
    return value,'estimated'


def economic_costs(devices,electricity,outdoor=None):
    result=[]
    for key,data in devices.items():
        if not data.get("enabled",True):
            continue
        g,origin=economic_parameters(data)
        if not g:
            continue
        eff=finite(effective_cop(g,outdoor)[0] if g["kind"]=="heat_pump" else g.get("efficiency"))
        if eff is None or eff<=0:
            continue
        if g["kind"]=="fuel":
            p,q,e=map(finite,(g.get("fuel_price"),g.get("fuel_quantity"),g.get("fuel_energy_kwh")))
            cost=p/(q*e*eff) if p is not None and q and e and q>0 and e>0 else None
        else:
            cost=electricity/eff if electricity is not None else None
        if cost is not None:
            row={"id":key,"cost":cost,"source":effective_cop(g,outdoor)[1] if g["kind"]=="heat_pump" else g.get("_economic_origin",origin)}
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
            eff,_=effective_cop(g,outdoor)
        return Generator(identifier,g["kind"],eff,g["capacity_kw"],g.get("fuel_price",0),g.get("fuel_quantity",1),g.get("fuel_energy_kwh",1),g.get("enabled",True))
    except (KeyError,ValueError,TypeError):
        return None


def heat_pump_live(data, read, outdoor, now, average=None, electricity=None):
    """Instantaneous electrical input and conditional heat estimate, not a measured COP."""
    from .thermal_zones import parse_curve, cop_at
    if data.get("kind")!="heat_pump":
        return None
    cop,origin=effective_cop(data,outdoor)
    entity=data.get("power_entity")
    state=read(entity) if entity else None
    power=None
    if state is not None and 0<=(now-state.last_updated).total_seconds()<=900:
        factor={"W":1,"kW":1000,"MW":1000000}.get(state.attributes.get("unit_of_measurement"))
        value=finite(state.state)
        if factor is not None and value is not None and value>=0:
            power=value*factor
    control=read(data.get("control_entity")) if data.get("control_entity") else None
    action=control.attributes.get("hvac_action") if control else None
    mode=control.state if control else "unknown"
    operating=read(data.get("state_entity")) if data.get("state_entity") else None
    raw=str(operating.state).lower() if operating else None
    status="unknown"
    evidence=None
    if mode=="off":
        status,evidence="off","climate_mode"
    elif mode not in ("unknown","unavailable"):
        if action in ("heating","cooling","idle","fan","drying","defrosting"):
            status,evidence=action,"hvac_action"
        elif raw in ("heating","cooling","idle","defrosting"):
            status,evidence=raw,"operating_sensor"
        elif raw=="on" and operating and mode=="heat" and str(data.get("state_entity","")).endswith(("_heating_active","_heating_running")):
            status,evidence="heating","operating_sensor"
        elif raw=="on" and operating and str(data.get("state_entity","")).endswith(("_compressor_running","_compressor_active")):
            status,evidence="compressor_running","operating_sensor"
        elif raw=="off" and operating and str(data.get("state_entity","")).endswith(("_compressor_running","_compressor_active")):
            status,evidence="compressor_stopped","operating_sensor"
    heating=status=="heating"
    # Without explicit heating action, the electrical input is still useful,
    # but fan/standby/defrost cannot be distinguished from useful heat.
    source="sensor" if power is not None else "unavailable"
    interval=None
    if power is None and average:
        power=average["power_w"]
        entity=average["power_entity"]
        interval=average["interval_minutes"]
        source="counter_average"
    if status=="unknown" and source=="counter_average" and power>0:
        status,evidence="recent_consumption","energy_counter"
    return {"mode":mode,"operating_status":status,"operating_evidence":evidence,"hvac_action":action,"state_entity":data.get("state_entity"),"state_value":raw,"operating_candidates":data.get("_operating_candidates",[]),"power_w":power,"power_entity":entity,"power_source":source,"interval_minutes":interval,"cop":cop,"cop_source":origin,
            "heat_kw":power*cop/1000 if power is not None and heating and source=="sensor" and cop is not None and cop>0 else None,
            "cost_per_hour":power*electricity/1000 if power is not None and electricity is not None else None,
            "heating_confirmed":heating}


def fuel_live(data, read, now):
    """Burning-rate estimate; never display a nominal burn rate as current use."""
    if data.get("kind")!="fuel":
        return None
    entity=data.get("fuel_rate_entity") or data.get("_economic_entities",{}).get("rate")
    state=read(entity) if entity else None
    status=read(data.get("state_entity")) if data.get("state_entity") else None
    active={s.strip() for s in data.get("active_states","").split(",") if s.strip()}
    inactive={s.strip() for s in data.get("inactive_states","").split(",") if s.strip()}
    rate=None
    if status and status.state in inactive and status.state not in active:
        rate=0.
    elif status and status.state in active and status.state not in inactive and state and 0<=(now-state.last_updated).total_seconds()<=900:
        if state.attributes.get("unit_of_measurement")=="kg/h":
            rate=finite(state.state)
            if rate is not None and rate<0:
                rate=None
    p,q,e,eff=map(finite,(data.get("fuel_price"),data.get("fuel_quantity"),data.get("fuel_energy_kwh"),data.get("efficiency")))
    kg=data.get("fuel_mass_unit","kg")=="kg"
    return {"rate_kg_h":rate,"rate_entity":entity,"cost_per_hour":rate*p/q if rate is not None and kg and p is not None and q and q>0 else None,
            "heat_kw":rate*e*eff if rate is not None and kg and e and eff else None,"efficiency":eff,"fuel_energy_kwh":e}

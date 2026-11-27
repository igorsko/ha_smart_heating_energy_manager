"""Read Energy dashboard preferences without altering Home Assistant settings."""
from .prediction import kw, number

def discover_power(prefs, read, siblings):
    """Use explicit semantic suffixes on devices linked to Energy counters.

    Never choose a generic power sensor merely because it shares a device.
    Net grid and battery direction cannot safely be guessed.
    """
    from copy import deepcopy
    prefs=deepcopy(prefs or {})
    sources=prefs.get("energy_sources",[])
    def choose(anchor, suffixes, klass, units):
        matches=[]
        for entity in siblings(anchor):
            state=read(entity)
            if (state and entity.endswith(suffixes)
                and state.attributes.get("unit_of_measurement") in units
                and state.attributes.get("device_class") in (None,klass)):
                matches.append(entity)
        return matches[0] if len(matches)==1 else None
    homes=set()
    for s in sources:
        if s.get("type")!="solar":
            continue
        anchor=s.get("stat_energy_from")
        if not anchor:
            continue
        if not s.get("stat_rate"):
            candidate=choose(anchor,("_production_ct_power","_production_power","_solar_power","_pv_power"),"power",("W","kW","MW"))
            if candidate:
                s["stat_rate"]=candidate
        home=choose(anchor,("_consumption_ct_power","_consumption_power","_home_power"),"power",("W","kW","MW"))
        if home:
            homes.add(home)
    if len(homes)==1 and not any(s.get("type")=="home" for s in sources):
        sources.append({"type":"home","stat_rate":next(iter(homes))})
    # Explicit directional names only; generic signed power is ambiguous.
    def linked(s,keys):
        return sorted({e for key in keys if s.get(key) for e in siblings(s[key])})
    def unique(pool,suffixes,klass,units):
        matches=[]
        for entity in pool:
            state=read(entity)
            if state and entity.endswith(suffixes) and state.attributes.get("unit_of_measurement") in units and state.attributes.get("device_class") in (None,klass):
                matches.append(entity)
        return matches[0] if len(matches)==1 else None
    watts=("W","kW","MW")
    for s in sources:
        kind=s.get("type")
        if kind not in ("grid","battery"):
            continue
        pool=linked(s,("stat_energy_from","stat_energy_to","stat_rate","stat_soc"))
        if not s.get("power_config") and not s.get("stat_rate") and not s.get("power"):
            if kind=="grid":
                incoming=unique(pool,("_grid_import_power","_import_power"),"power",watts)
                outgoing=unique(pool,("_grid_export_power","_export_power"),"power",watts)
            else:
                incoming=unique(pool,("_battery_discharge_power","_discharge_power"),"power",watts)
                outgoing=unique(pool,("_battery_charge_power","_charge_power"),"power",watts)
            if incoming and outgoing and incoming!=outgoing:
                s["power_config"]={"stat_rate_from":incoming,"stat_rate_to":outgoing}
                s["_discovered_directional"]=True
        if kind=="battery":
            # Only a named capacity, never remaining/stored energy.
            if not s.get("entity_capacity") and not s.get("capacity"):
                candidate=unique(pool,("_battery_capacity","_capacita_della_batteria"),"energy_storage",("Wh","kWh","MWh"))
                if candidate:
                    s["entity_capacity"]=candidate
            if not s.get("stat_soc"):
                candidate=unique(pool,("_battery_soc","_state_of_charge","_battery","_batteria"),"battery",("%",))
                if candidate:
                    s["stat_soc"]=candidate
    # A single system-level battery can expose capacity on the solar-linked
    # gateway even when charge/discharge counters are virtual helpers.
    batteries=[s for s in sources if s.get("type")=="battery"]
    solar_pool=sorted({e for s in sources if s.get("type")=="solar" and s.get("stat_energy_from") for e in siblings(s["stat_energy_from"])})
    if len(batteries)==1:
        s=batteries[0]
        if not s.get("entity_capacity") and not s.get("capacity"):
            candidate=unique(solar_pool,("_battery_capacity","_capacita_della_batteria"),"energy_storage",("Wh","kWh","MWh"))
            if candidate:
                s["entity_capacity"]=candidate
        if not s.get("stat_soc"):
            candidate=unique(solar_pool,("_battery_soc","_state_of_charge","_battery","_batteria"),"battery",("%",))
            if candidate:
                s["stat_soc"]=candidate
    return prefs

def snapshot(prefs, read):
    sources=prefs.get("energy_sources",[]) if prefs else []
    solar=[s for s in sources if s.get("type")=="solar"]
    grid=[s for s in sources if s.get("type")=="grid"]
    batteries=[s for s in sources if s.get("type")=="battery"]
    homes=[s for s in sources if s.get("type")=="home"]
    def power(entity):
        state=read(entity) if entity else None
        return kw(state.state,state.attributes.get("unit_of_measurement")) if state else None
    def net(s):
        p=s.get("power_config") or {}
        if p.get("stat_rate"):
            return power(p["stat_rate"])
        if p.get("stat_rate_inverted"):
            v=power(p["stat_rate_inverted"])
            return -v if v is not None else None
        if p.get("stat_rate_from") and p.get("stat_rate_to"):
            a,b=power(p["stat_rate_from"]),power(p["stat_rate_to"])
            return a-b if a is not None and b is not None and (not s.get("_discovered_directional") or (a>=0 and b>=0)) else None
        charge=["stat_rate_from_grid","stat_rate_from_solar"]
        discharge=["stat_rate_to_home","stat_rate_to_grid"]
        if any(k in p for k in charge+discharge):
            values=[(power(p[k]) if k in p else 0) for k in discharge+charge]
            return sum(values[:2])-sum(values[2:]) if all(v is not None for v in values) else None
        return power(s.get("stat_rate"))
    def total(values):
        return sum(values) if values and all(v is not None for v in values) else None
    home_ids={s.get("stat_rate") for s in homes if s.get("stat_rate")}
    pv_ids=[s.get("stat_rate") for s in solar]
    pv=total([power(e) if e not in home_ids else None for e in pv_ids])
    if len(set(pv_ids))!=len(pv_ids):
        pv=None
    grid_values=[net(p) for s in grid for p in (s.get("power") or [s])]
    grid_net=total(grid_values)
    battery_net=total([net(s) for s in batteries])
    home=total([power(s.get("stat_rate")) for s in homes])
    if not homes and grid_net is not None and (not solar or pv is not None) and (not batteries or battery_net is not None):
        home=grid_net+(pv or 0)+(battery_net or 0)
    # Derive at most one missing flow, and only with all other terms known.
    origins={"grid_net_kw":"measured" if grid_net is not None else "unavailable",
             "battery_net_kw":"measured" if battery_net is not None else "unavailable",
             "home_kw":"measured" if homes and home is not None else "balance" if home is not None else "unavailable"}
    if home is not None and home>=0 and (pv is not None and pv>=0 or not solar):
        production=pv if solar else 0
        if grid and grid_net is None and (battery_net is not None or not batteries):
            grid_net=home-production-(battery_net if batteries else 0)
            origins["grid_net_kw"]="balance"
        elif batteries and battery_net is None and (grid_net is not None or not grid):
            battery_net=home-production-(grid_net if grid else 0)
            origins["battery_net_kw"]="balance"
    def flow_ids(group):
        ids=set()
        for s in group:
            for p in s.get("power") or [s]:
                if p.get("stat_rate"):
                    ids.add(p["stat_rate"])
                ids.update(v for k,v in (p.get("power_config") or {}).items() if k.startswith("stat_rate") and isinstance(v,str))
        return sorted(ids)
    socs=[]
    for s in batteries:
        state=read(s["stat_soc"]) if s.get("stat_soc") else None
        value=number(state.state) if state and state.attributes.get("unit_of_measurement")=="%" else None
        capacity=number(s.get("capacity"))
        if s.get("entity_capacity"):
            cs=read(s["entity_capacity"])
            if cs:
                v=number(cs.state)
                factor={"Wh":.001,"kWh":1,"MWh":1000}.get(cs.attributes.get("unit_of_measurement"))
                capacity=v*factor if v is not None and factor else None
        socs.append((value if value is not None and 0<=value<=100 else None,capacity))
    soc=None
    if len(socs)==1:
        soc=socs[0][0]
    elif socs and all(v is not None and c is not None and c>0 for v,c in socs):
        soc=sum(v*c for v,c in socs)/sum(c for _,c in socs)
    return {"pv_kw":pv if pv is not None and pv>=0 else None,
            "home_kw":home if home is not None and home>=0 else None,"grid_net_kw":grid_net,"export_kw":max(0,-grid_net) if grid_net is not None else None,
            "battery_net_kw":battery_net,"battery_soc":soc,
            "battery_capacity_kwh":sum(c for _,c in socs) if socs and all(c is not None and c>0 for _,c in socs) else None,
            "energy_flow_origins":origins,
            "energy_power_entities":{"pv":[e for e in pv_ids if e],"home":sorted(home_ids),"grid":flow_ids(grid),"battery":flow_ids(batteries),"battery_capacity":[s["entity_capacity"] for s in batteries if s.get("entity_capacity")],"battery_soc":[s["stat_soc"] for s in batteries if s.get("stat_soc")]},
            "energy_dashboard_sources":{kind:[{k:v for k,v in s.items() if k.startswith("stat_") or k=="config_entry_solar_forecast"} for s in group] for kind,group in (("solar",solar),("grid",grid),("battery",batteries))}}

async def async_snapshot(hass):
    if "energy" not in hass.config.components:
        return {}
    from homeassistant.components.energy.data import async_get_manager
    manager=await async_get_manager(hass)
    from homeassistant.helpers import entity_registry as er
    registry=er.async_get(hass)
    def siblings(anchor):
        record=registry.async_get(anchor)
        if not record or not record.device_id:
            return []
        return [e.entity_id for e in registry.entities.values()
                if e.device_id==record.device_id and not e.disabled_by
                and e.entity_id.startswith("sensor.")]
    prefs=discover_power(manager.data,hass.states.get,siblings)
    return snapshot(prefs,hass.states.get)

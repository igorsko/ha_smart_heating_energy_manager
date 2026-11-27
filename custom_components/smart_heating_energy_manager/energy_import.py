"""Read Energy dashboard preferences without altering Home Assistant settings."""
from .prediction import kw, number

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
            return a-b if a is not None and b is not None else None
        charge=["stat_rate_from_grid","stat_rate_from_solar"]
        discharge=["stat_rate_to_home","stat_rate_to_grid"]
        if any(k in p for k in charge+discharge):
            values=[(power(p[k]) if k in p else 0) for k in discharge+charge]
            return sum(values[:2])-sum(values[2:]) if all(v is not None for v in values) else None
        return power(s.get("stat_rate"))
    def total(values):
        return sum(values) if values and all(v is not None for v in values) else None
    pv=total([power(s.get("stat_rate")) for s in solar])
    grid_values=[net(p) for s in grid for p in (s.get("power") or [s])]
    grid_net=total(grid_values)
    battery_net=total([net(s) for s in batteries])
    home=total([power(s.get("stat_rate")) for s in homes])
    if not homes and grid_net is not None and (not solar or pv is not None) and (not batteries or battery_net is not None):
        home=grid_net+(pv or 0)+(battery_net or 0)
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
            "energy_dashboard_sources":{kind:[{k:v for k,v in s.items() if k.startswith("stat_") or k=="config_entry_solar_forecast"} for s in group] for kind,group in (("solar",solar),("grid",grid),("battery",batteries))}}

async def async_snapshot(hass):
    if "energy" not in hass.config.components:
        return {}
    from homeassistant.components.energy.data import async_get_manager
    manager=await async_get_manager(hass)
    return snapshot(manager.data,hass.states.get)

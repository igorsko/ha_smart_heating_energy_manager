"""Read Home Assistant areas without guessing appliance specifications."""
def discover_areas(hass):
    from homeassistant.helpers import area_registry, device_registry, entity_registry
    areas=area_registry.async_get(hass)
    devices=device_registry.async_get(hass)
    entities=entity_registry.async_get(hass)
    result={a.id:{"name":a.name,"temperature_candidates":[],"source_candidates":[]} for a in areas.async_list_areas()}
    for e in entities.entities.values():
        if e.disabled_by or e.platform=="smart_heating_energy_manager":
            continue
        device=devices.async_get(e.device_id) if e.device_id else None
        area=e.area_id or (device.area_id if device else None)
        if area not in result:
            continue
        state=hass.states.get(e.entity_id)
        klass=(state.attributes.get("device_class") if state else None) or e.device_class or e.original_device_class
        if e.domain=="sensor" and klass=="temperature":
            result[area]["temperature_candidates"].append(e.entity_id)
        if e.domain=="climate":
            modes=state.attributes.get("hvac_modes",[]) if state else []
            if not modes or any(m in modes for m in ("heat","heat_cool","auto")):
                result[area]["source_candidates"].append(e.entity_id)
    for zone in result.values():
        for field in ("temperature_candidates","source_candidates"):
            zone[field].sort()
    return result

def zone_view(discovered, saved):
    """Preserve confirmed mappings; never treat a suggestion as confirmation."""
    return {key:{**area,**saved.get(key,{}),"name":area["name"]} for key,area in discovered.items()}

"""Optional WiNET suggestions, using stable registry IDs rather than entity names."""

def suggest(entries, device_id):
    """Return mappings for a single explicitly selected WiNET device."""
    candidates = [e for e in entries if e.device_id == device_id and e.platform == "winnet_stove" and not e.disabled_by]
    suffixes = {"fuel_mass_entity": "_pellet_pellet_used",
                "fuel_rate_entity": "_insights_effective_rate",
                "level_entity": "_power", "state_entity": "_burning"}
    result = {}
    for field, suffix in suffixes.items():
        matches = [e.entity_id for e in candidates if e.unique_id.endswith(suffix)]
        if len(matches) == 1:
            result[field] = matches[0]
    if "state_entity" in result:
        result.update(active_states="on", inactive_states="off")
    return result

def winnet_siblings(entries,data):
    """Match configured device; allow unique integration device only without a conflicting binding."""
    entries=list(entries)
    active=[e for e in entries if e.platform=="winnet_stove" and not e.disabled_by and e.device_id]
    references={data.get(k) for k in ("control_entity","state_entity","fuel_mass_entity","fuel_rate_entity")}-{None,""}
    linked={e.device_id for e in active if e.entity_id in references}
    if len(linked)==1:
        device=next(iter(linked))
    elif linked or data.get("control_entity"):
        return []
    else:
        devices={e.device_id for e in active}
        if len(devices)!=1:
            return []
        device=next(iter(devices))
    return [e for e in active if e.device_id==device]

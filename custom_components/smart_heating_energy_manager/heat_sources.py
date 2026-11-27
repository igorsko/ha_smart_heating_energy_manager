"""Conservative heat-source selection; never list arbitrary switches."""
def eligible(entity_id, attrs, configured=False, diagnostic=False):
    if diagnostic and not configured:
        return False
    domain=entity_id.split(".",1)[0]
    if configured:
        return domain in ("climate","switch","script")
    if domain=="climate":
        return any(m in attrs.get("hvac_modes",[]) for m in ("heat","heat_cool","auto"))
    return domain=="switch" and attrs.get("device_class") in ("heater",)

def configured_sources(generators):
    return {g["control_entity"] for g in generators.values() if g.get("control_entity")}


def zone_candidates(hass,generators):
    configured=configured_sources(generators)
    return sorted(s.entity_id for s in hass.states.async_all() if eligible(s.entity_id,s.attributes,s.entity_id in configured))

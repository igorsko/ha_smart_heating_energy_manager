"""Optional WiNET suggestions, using stable registry IDs rather than entity names."""

def suggest(entries, device_id):
    """Return mappings for a single explicitly selected WiNET device."""
    candidates = [e for e in entries if e.device_id == device_id and e.platform == "winnet_stove" and not e.disabled_by]
    suffixes = {"fuel_mass_entity": "_pellet_pellet_used",
                "fuel_rate_entity": "_insights_effective_rate",
                "level_entity": "_power"}
    result = {}
    for field, suffix in suffixes.items():
        matches = [e.entity_id for e in candidates if e.unique_id.endswith(suffix)]
        if len(matches) == 1:
            result[field] = matches[0]
    return result

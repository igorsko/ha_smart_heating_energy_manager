"""Technical form visibility and non-destructive mapping preferences."""
ENTITY_FIELDS={"state_entity","energy_entity","power_entity","fuel_rate_entity","fuel_mass_entity","level_entity"}

def generator_fields(kind):
    # Name, type and control are managed by the basic form; room temperature by zones.
    common={"efficiency","capacity_kw","enabled","energy_entity","power_entity"}
    if kind=="heat_pump":
        return common|{"cop_curve"}
    runtime={"state_entity","manual_input_rate","active_states","inactive_states"}
    if kind=="resistance":
        return common|runtime
    if kind=="fuel":
        return common|runtime|{"fuel_price","fuel_quantity","fuel_energy_kwh","energy_is_useful_heat","fuel_mass_unit","level_rates","fuel_mass_estimated","fuel_rate_entity","fuel_mass_entity","level_entity"}
    raise ValueError("Unknown generator type")

def mapping_preferences(old, submitted, automatic, visible):
    """Keep unchanged auto suggestions dynamic; blank resets to discovery."""
    data=dict(old)
    for field in ENTITY_FIELDS & visible:
        value=submitted.get(field)
        if not value or (not old.get(field) and value==automatic.get(field)):
            data.pop(field,None)
        else:
            data[field]=value
    return data

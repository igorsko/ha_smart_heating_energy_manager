"""Field visibility for technical generator options."""
def generator_fields(kind):
    common={"name","efficiency","capacity_kw","enabled","state_entity","energy_entity","power_entity","temperature_entity"}
    if kind=="heat_pump":
        return common|{"cop_curve"}
    runtime={"manual_input_rate","active_states","inactive_states"}
    if kind=="resistance":
        return common|runtime
    if kind=="fuel":
        return common|runtime|{"fuel_price","fuel_quantity","fuel_energy_kwh","energy_is_useful_heat","fuel_mass_unit","level_rates","fuel_mass_estimated","fuel_rate_entity","fuel_mass_entity","level_entity"}
    raise ValueError("Unknown generator type")

"""Read-only Recorder adapter for experimental building calibration."""
from dataclasses import asdict
from datetime import timedelta
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util import dt as dt_util
from .calibration import fit
from .history_input import Sample, Series, build_intervals
from .model import finite

def convert(value, unit, kind):
    """Normalize supported units without guessing missing units."""
    n = finite(value)
    if n is None:
        return None
    if kind == "temperature":
        return n if unit == "°C" else (n-32)*5/9 if unit == "°F" else None
    factors = {"Wh": .001, "kWh": 1, "MWh": 1000}
    return n*factors[unit] if unit in factors and n >= 0 else None

def _series(states, kind, multiplier=1):
    samples = []
    for state in states:
        value = convert(state.state, state.attributes.get("unit_of_measurement"), kind)
        samples.append(Sample(state.last_updated.timestamp(),
                              None if value is None else value*multiplier))
    return Series(samples)

async def async_calibrate(hass, config):
    """Return diagnostics only; never replace configured coefficients."""
    devices = list(config.get("generators", {}).values())
    if not devices:
        return {"status": "no_generators"}
    # Disabled for dispatch is not proof that a generator never delivered heat.
    if any(not g.get("energy_entity") for g in devices):
        return {"status": "missing_energy_mapping"}
    ids = [config["indoor"], config["outdoor"]] + [g["energy_entity"] for g in devices]
    if len(set(ids)) != len(ids):
        return {"status": "duplicate_mapping"}
    # Fuel input must explicitly declare that the counter measures useful heat.
    if any(g["kind"] == "fuel" and not g.get("energy_is_useful_heat",False) for g in devices):
        return {"status": "fuel_energy_semantics_unconfirmed"}
    end = dt_util.utcnow()
    start = end - timedelta(days=config.get("history_days",7))
    age = config.get("history_max_age_hours",2)*3600
    def calculate():
        states = get_significant_states(hass, start-timedelta(seconds=age), end,
            entity_ids=ids, include_start_time_state=False,
            significant_changes_only=False, minimal_response=False, no_attributes=False)
        indoor = _series(states.get(ids[0], []), "temperature")
        outdoor = _series(states.get(ids[1], []), "temperature")
        counters = [(g["kind"], _series(states.get(g["energy_entity"], []),
                     "energy", g["efficiency"] if g["kind"] == "resistance" else 1))
                    for g in devices]
        intervals = build_intervals(indoor,outdoor,counters,start.timestamp(),end.timestamp(),
                      config.get("history_interval_minutes",60)*60,age)
        result = fit(intervals)
        return {"status": "estimated" if result else "insufficient_or_unidentifiable",
                "intervals": len(intervals), "fit": asdict(result) if result else None,
                "calculated_at": end.isoformat()}
    return await get_instance(hass).async_add_executor_job(calculate)

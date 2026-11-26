"""Advisory sensors; no appliance commands."""
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util
from .model import finite, electricity_price, estimate

SCAN_INTERVAL = timedelta(seconds=60)
SENSORS = {
    "heat_demand": ("Estimated heat demand", "kW"),
    "heat_pump_cost": ("Heat pump thermal cost", "EUR/kWh"),
    "pellet_cost": ("Pellet thermal cost", "EUR/kWh"),
    "resistance_cost": ("Resistance thermal cost", "EUR/kWh"),
    "electricity_price": ("Marginal electricity price", "EUR/kWh"),
    "recommended_source": ("Recommended heat source", None),
    "break_even_cop": ("Break-even COP", None),
}

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HeatingSensor(entry, key, name, unit) for key, (name, unit) in SENSORS.items()], True)

class HeatingSensor(SensorEntity):
    _attr_should_poll = True

    def __init__(self, entry, key, name, unit):
        self._data = entry.data
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit

    def _temperature(self, entity_id):
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        value = finite(state.state)
        unit = state.attributes.get("unit_of_measurement")
        if value is not None and unit == "°F":
            value = (value - 32) * 5 / 9
        elif unit != "°C":
            return None
        return value if value is not None and -60 <= value <= 70 else None

    async def async_update(self):
        d = self._data
        index = self.hass.states.get(d.get("pun", "")) if d.get("use_index") else None
        # Reject index observations older than 36 hours, including restored stale values.
        if index and dt_util.utcnow() - index.last_updated > timedelta(hours=36):
            index = None
        price, source = electricity_price(index.state if index else None,
            index.attributes.get("unit_of_measurement") if index else None,
            d["fixed"], d["spread"], d["losses"], d["variable"], d["tax"], d["vat"])
        result = estimate(self._temperature(d["indoor"]), self._temperature(d["outdoor"]),
            d["h"], price, d["cop"], d["pellet_price"], d["pellet_mass"], d["lhv"], d["efficiency"])
        result["electricity_price"] = price
        self._attr_native_value = result[self._key]
        self._attr_available = self._attr_native_value is not None
        self._attr_extra_state_attributes = {"mode": "advisory", "price_source": source,
            "thermal_model": "configured_not_calibrated"}

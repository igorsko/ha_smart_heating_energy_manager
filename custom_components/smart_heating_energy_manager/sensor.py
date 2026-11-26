"""Advisory sensors; no appliance commands."""
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util
from .model import finite, electricity_price, estimate
from .generators import Generator, rank_generators

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
    specs = SENSORS if "cop" in entry.data and "generators" not in entry.options else {
        k:v for k,v in SENSORS.items() if k in ("heat_demand","electricity_price","recommended_source")
    }
    async_add_entities([HeatingSensor(entry, key, name, unit) for key, (name, unit) in specs.items()], True)
    if entry.options.get("history_enabled",False):
        async_add_entities([CalibrationDiagnostic(entry)], False)

class HeatingSensor(SensorEntity):
    _attr_should_poll = True

    def __init__(self, entry, key, name, unit):
        self._data = {**entry.data, **entry.options}
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
        if index and dt_util.utcnow() - index.last_updated > timedelta(hours=d.get('index_max_age_hours',36)):
            index = None
        price, source = electricity_price(index.state if index else None,
            index.attributes.get("unit_of_measurement") if index else None,
            d["fixed"], d["spread"], d["losses"], d["variable"], d["tax"], d["vat"])
        indoor, outdoor = self._temperature(d["indoor"]), self._temperature(d["outdoor"])
        if "generators" not in d and "cop" in d:
            result = estimate(indoor, outdoor, d["h"], price, d["cop"], d["pellet_price"],
                              d["pellet_mass"], d["lhv"], d["efficiency"])
            candidates = []
        else:
            demand = max(0, indoor-outdoor)*d["h"]/1000 if indoor is not None and outdoor is not None else None
            devices = d.get("generators", {})
            generators = [Generator(k,v["kind"],v["efficiency"],v["capacity_kw"],v["fuel_price"],
                          v["fuel_quantity"],v["fuel_energy_kwh"],v["enabled"]) for k,v in devices.items()]
            candidates = rank_generators(generators, price, demand)
            recommendation = ("unknown" if demand is None else "none" if demand == 0 else
                              devices[candidates[0][0]]["name"] if candidates else "no_suitable_generator")
            result = {"heat_demand": demand, "recommended_source": recommendation}
        result["electricity_price"] = price
        self._attr_native_value = result[self._key]
        self._attr_available = self._attr_native_value is not None
        self._attr_extra_state_attributes = {"mode": "advisory", "price_source": source,
            "thermal_model": "configured_not_calibrated",
            "candidates": [{"id": key, "cost": cost} for key,cost in candidates]}

class CalibrationDiagnostic(SensorEntity):
    """Opt-in read-only daily calibration diagnostic."""
    _attr_should_poll = False
    _attr_name = "Thermal calibration status"

    def __init__(self, entry):
        self._config = {**entry.data, **entry.options}
        self._attr_unique_id = f"{entry.entry_id}_calibration"
        self._attr_native_value = "pending"
        self._lock = None

    async def async_added_to_hass(self):
        import asyncio
        from homeassistant.helpers.event import async_track_time_interval
        self._lock = asyncio.Lock()
        self.async_on_remove(async_track_time_interval(self.hass, self._refresh, timedelta(days=1)))
        self.async_on_remove(self.hass.async_create_task(self._refresh()).cancel)

    async def _refresh(self, now=None):
        if self._lock.locked():
            return
        async with self._lock:
            try:
                from .recorder_adapter import async_calibrate
                if "recorder" not in self.hass.config.components:
                    result = {"status": "recorder_unavailable"}
                else:
                    result = await async_calibrate(self.hass, self._config)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Historical calibration failed")
                result = {"status": "error"}
            self._attr_native_value = result["status"]
            self._attr_extra_state_attributes = result
            self.async_write_ha_state()

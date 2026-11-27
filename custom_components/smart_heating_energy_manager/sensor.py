"""Advisory sensors; no appliance commands."""
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util
from .learned import accepted, effective_loss
from .model import finite, electricity_price, estimate
from .onboarding import ready
from .temperature_zones import resolve, average_temperature
from .areas import discover_areas, zone_view
from .thermal_zones import parse_curve, cop_at, zone_status
from .generators import Generator, rank_generators

SCAN_INTERVAL = timedelta(seconds=60)
SENSORS = {
    "indoor_average": ("Average indoor temperature", "°C"),
    "outdoor_temperature": ("Outdoor temperature", "°C"),
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
        k:v for k,v in SENSORS.items() if k in ("heat_demand","electricity_price","recommended_source","indoor_average","outdoor_temperature")
    }
    async_add_entities([HeatingSensor(entry, key, name, unit) for key, (name, unit) in specs.items()], True)
    config = {**entry.data, **entry.options}
    if config.get("history_enabled",False) or config.get("apply_learned",False):
        async_add_entities([CalibrationDiagnostic(entry)], False)

class HeatingSensor(SensorEntity):
    _attr_should_poll = True

    def __init__(self, entry, key, name, unit):
        self._data = {**entry.data, **entry.options}
        self._entry_id = entry.entry_id
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit

    def _temperature(self, entity_id):
        if not entity_id:
            return None
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
        learned = self.hass.data['smart_heating_energy_manager'][self._entry_id]['learned']
        loss, model_source = effective_loss(d, learned)
        index = self.hass.states.get(d.get("pun", "")) if d.get("use_index") else None
        # Reject index observations older than 36 hours, including restored stale values.
        if index and dt_util.utcnow() - index.last_updated > timedelta(hours=d.get('index_max_age_hours',36)):
            index = None
        price, source = electricity_price(index.state if index else None,
            index.attributes.get("unit_of_measurement") if index else None,
            d.get("fixed"), d.get("spread",0), d.get("losses",0), d.get("variable",0), d.get("tax",0), d.get("vat",0))
        zones=zone_view(discover_areas(self.hass),d.get("zones",{}),d.get("outdoor"))
        indoor_ids,outdoor_id=resolve(zones,d.get("indoor"),d.get("outdoor"))
        indoor,count=average_temperature(indoor_ids,self._temperature)
        outdoor=self._temperature(outdoor_id)
        zone_models={k:zone_status(z,self._temperature(z.get("temperature")),outdoor) for k,z in zones.items() if z.get("confirmed") and not z.get("outdoor")}
        efficiencies={}
        if "generators" not in d and "cop" in d and loss is not None and price is not None:
            result = estimate(indoor, outdoor, loss, price, d["cop"], d["pellet_price"],
                              d["pellet_mass"], d["lhv"], d["efficiency"])
            candidates = []
        else:
            h = finite(loss)
            demand = max(0, indoor-outdoor)*h/1000 if indoor is not None and outdoor is not None and h is not None and h>0 else None
            devices = d.get("generators", {})
            generators=[]
            for k,v in devices.items():
                if not ready(v):
                    continue
                efficiency=v["efficiency"]
                origin="manual"
                if v["kind"]=="heat_pump":
                    efficiency,origin=cop_at(parse_curve(v.get("cop_curve","")),outdoor,efficiency)
                efficiencies[k]={"value":efficiency,"source":origin}
                generators.append(Generator(k,v["kind"],efficiency,v["capacity_kw"],v["fuel_price"],
                    v["fuel_quantity"],v["fuel_energy_kwh"],v["enabled"]))
            candidates = rank_generators(generators, price, demand)
            recommendation = ("unknown" if demand is None else "none" if demand == 0 else
                              devices[candidates[0][0]]["name"] if candidates else "no_suitable_generator")
            result = {"heat_demand": demand, "recommended_source": recommendation}
        result["indoor_average"] = round(indoor,2) if indoor is not None else None
        result["outdoor_temperature"] = outdoor
        result["electricity_price"] = price
        self._attr_native_value = result.get(self._key)
        self._attr_available = self._attr_native_value is not None
        self._attr_extra_state_attributes = {"mode": "advisory", "price_source": source,
            "thermal_model": model_source, "loss_w_k": loss,
            "indoor_sensor_count":count, "indoor_sensor_total":len(indoor_ids), "indoor_sensors":indoor_ids,
            "zones": zone_models, "efficiencies": efficiencies,
            "pending_generators": [k for k,v in d.get("generators",{}).items() if not ready(v)],
            "candidates": [{"id": key, "cost": cost} for key,cost in candidates]}

class CalibrationDiagnostic(SensorEntity):
    """Opt-in read-only daily calibration diagnostic."""
    _attr_should_poll = False
    _attr_name = "Thermal calibration status"

    def __init__(self, entry):
        self._config = {**entry.data, **entry.options}
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_calibration"
        self._attr_native_value = "pending"
        self._lock = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
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
                runtime = self.hass.data["smart_heating_energy_manager"][self._entry_id]
                if self._config.get("calibration_locked",False):
                    result = {"status":"locked"}
                elif not self._config.get("history_enabled",False):
                    result = {"status":"disabled"}
                elif not self._config.get("indoor") or not self._config.get("outdoor"):
                    result = {"status":"configure_temperature_sources"}
                elif "recorder" not in self.hass.config.components:
                    result = {"status": "recorder_unavailable"}
                else:
                    result = await async_calibrate(self.hass, self._config)
                    record = accepted(result,self._config)
                    if record:
                        await runtime['store'].async_save(record)
                        runtime['learned'] = record
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Historical calibration failed")
                result = {"status": "error"}
            self._attr_native_value = result["status"]
            self._attr_extra_state_attributes = {**result, 'last_valid': self.hass.data['smart_heating_energy_manager'][self._entry_id]['learned']}
            self.async_write_ha_state()

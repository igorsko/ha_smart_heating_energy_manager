"""Advisory sensors; no appliance commands."""
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util
from .learned import accepted, effective_loss
from .tariff_discovery import index_value, candidates as tariff_candidates
from .model import finite, electricity_price, estimate
from .onboarding import ready
from .temperature_zones import resolve, average_temperature, reference_config
from .areas import discover_areas, zone_view
from .thermal_zones import parse_curve, cop_at, zone_status
from .generators import Generator, rank_generators, capacity_status

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
    from .energy_forecast import EnergyForecast
    async_add_entities([EnergyForecast(entry)], False)
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
        from homeassistant.helpers import entity_registry as er
        found=tariff_candidates(er.async_get(self.hass).entities.values(),self.hass.states.get)
        index_id=d.get("pun") or (found[0] if len(found)==1 else None)
        raw_index=self.hass.states.get(index_id) if index_id else None
        if raw_index and dt_util.utcnow()-raw_index.last_updated>timedelta(hours=d.get("index_max_age_hours",36)):
            raw_index=None
        index=raw_index if d.get("use_index") else None
        # Reject index observations older than 36 hours, including restored stale values.
        if index and dt_util.utcnow() - index.last_updated > timedelta(hours=d.get('index_max_age_hours',36)):
            index = None
        price, source = electricity_price(index.state if index else None,
            index.attributes.get("unit_of_measurement") if index else None,
            d.get("fixed"), d.get("spread",0), d.get("losses",0), d.get("variable",0), d.get("tax",0), d.get("vat",0))
        zones=zone_view(discover_areas(self.hass),d.get("zones",{}),d.get("outdoor"))
        ref=reference_config(d,zones)
        loss,model_source=effective_loss(ref,learned)
        indoor_ids,outdoor_id=ref["indoor_reference"],ref["outdoor_reference"]
        indoor,count=average_temperature(indoor_ids,self._temperature)
        outdoor=self._temperature(outdoor_id)
        if model_source=="learned" and count!=len(indoor_ids):
            loss=d.get("h")
            model_source="manual" if loss else "learning_pending"
        zone_models={k:zone_status(z,self._temperature(z.get("temperature")),outdoor) for k,z in zones.items() if z.get("confirmed") and not z.get("outdoor")}
        from .thermal_groups import groups
        thermal_groups=groups(zones,self._temperature)
        from .bootstrap import economic_costs, building_estimate, winnet_parameters, declared_capacity, advisory_generator
        entries=list(er.async_get(self.hass).entities.values())
        devices={k:declared_capacity(winnet_parameters(v,entries,self.hass.states.get),entries,self.hass.states.get) for k,v in d.get("generators",{}).items()}
        from .learned import cop_context
        cop_info=cop_context(ref,learned)
        if cop_info["scope"]=="single_generator" and cop_info["cop"] is not None:
            for v in devices.values():
                if v["kind"]=="heat_pump":
                    v["_learned_cop"]=cop_info["cop"]
        from .calibration_inputs import calibration_inputs
        from .bootstrap import heat_pump_live, fuel_live
        resolved,_=calibration_inputs(devices,entries,self.hass.states.get)
        now=dt_util.utcnow()
        live={k:heat_pump_live(v,self.hass.states.get,outdoor,now,electricity=price) for k,v in resolved.items() if v.get("kind")=="heat_pump"}
        missing={k:resolved[k] for k,row in live.items() if row["power_w"] is None}
        runtime=self.hass.data['smart_heating_energy_manager'][self._entry_id]
        if missing:
            from .recorder_adapter import recent_heat_pump_power
            # Share the bounded query across the five polling sensors.
            import asyncio
            lock=runtime.setdefault("telemetry_lock",asyncio.Lock())
            async with lock:
                cached=runtime.get("telemetry_cache")
                signature=tuple(sorted((k,tuple([v.get("energy_entity") or "",*v.get("energy_alternatives",[])])) for k,v in resolved.items() if v.get("kind")=="heat_pump"))
                if not cached or len(cached)<3 or cached[2]!=signature or (now-cached[0]).total_seconds()>=300:
                    try:
                        averages=await recent_heat_pump_power(self.hass,resolved,now)
                    except Exception:
                        import logging
                        logging.getLogger(__name__).exception("Recent energy counter history unavailable")
                        averages={}
                    runtime["telemetry_cache"]=(now,averages,signature)
                else:
                    averages=cached[1]
            for k,v in missing.items():
                live[k]=heat_pump_live(v,self.hass.states.get,outdoor,now,averages.get(k),price)
        fuel={k:fuel_live(v,self.hass.states.get,now) for k,v in resolved.items() if v.get("kind")=="fuel"}
        efficiencies={}
        if "generators" not in d and "cop" in d and loss is not None and price is not None:
            result = estimate(indoor, outdoor, loss, price, d["cop"], d["pellet_price"],
                              d["pellet_mass"], d["lhv"], d["efficiency"])
            candidates = []
        else:
            h = finite(loss)
            demand = max(0, indoor-outdoor)*h/1000 if indoor is not None and outdoor is not None and h is not None and h>0 else None
            generators=[]
            for k,v in devices.items():
                generator=advisory_generator(v,k,outdoor)
                if generator is None:
                    continue
                efficiencies[k]={"value":generator.efficiency,"source":"configured" if ready(v) else "estimated"}
                generators.append(generator)
            candidates = rank_generators(generators, price, demand)
            recommendation = ("unknown" if demand is None else "none" if demand == 0 else
                              devices[candidates[0][0]]["name"] if candidates else "generator_parameters_pending" if any(capacity_status(v,demand) in ("parameters_pending","capacity_unknown") for v in devices.values()) else "no_suitable_generator")
            result = {"heat_demand": demand, "recommended_source": recommendation}
        result["indoor_average"] = round(indoor,2) if indoor is not None else None
        result["outdoor_temperature"] = outdoor
        result["electricity_price"] = price
        self._attr_native_value = result.get(self._key)
        self._attr_available = self._attr_native_value is not None
        economic=economic_costs(devices,price,outdoor)
        _,initial_capacity=building_estimate(d)
        from .history_quality import readiness
        from .learned import current
        valid=current(learned,ref) if model_source=="learned" else None
        capacity=valid["fit"]["capacity_kwh_k"] if valid else d.get("thermal_capacity") or initial_capacity
        quality=readiness(count,len(indoor_ids),outdoor,finite(loss),finite(capacity),price)
        self._attr_extra_state_attributes = {"snapshot_at":now.isoformat(),"model_readiness":quality,"economic_comparison":economic,"initial_capacity_kwh_k":initial_capacity,"effective_capacity_kwh_k":capacity,"capacity_origin":"learned" if valid else "manual" if d.get("thermal_capacity") else "estimated" if initial_capacity is not None else "unknown","mode": "advisory", "price_source": source,
            "index_price":index_value(raw_index.state,raw_index.attributes.get("unit_of_measurement")) if raw_index else None,
            "index_entity":index_id,"index_candidates":found,
            "thermal_model": model_source, "loss_w_k": loss,
            "indoor_sensor_count":count, "indoor_sensor_total":len(indoor_ids), "indoor_sensors":indoor_ids,"outdoor_sensor":outdoor_id,
            "zones": zone_models, "thermal_groups":thermal_groups, "efficiencies": efficiencies,
            "learned_cop":cop_info,"heat_pump_live":live,"fuel_live":fuel,
            "generator_inventory":{k:{"entities":v.get("_inventory",[]),"energy_entity":v.get("energy_entity"),"power_entity":v.get("power_entity"),"energy_alternatives":v.get("energy_alternatives",[]),"state_entity":v.get("state_entity")} for k,v in resolved.items()},
            "generator_capacity_status": {k:capacity_status(v,result.get("heat_demand")) for k,v in devices.items()},
            "generator_capacity": {k:{"kw":v.get("capacity_kw") if v.get("_capacity_origin") else None,"source":v.get("_capacity_origin"),"entities":v.get("_capacity_entities",[])} for k,v in devices.items()},
            "pending_generators": [k for k,v in d.get("generators",{}).items() if not ready(v)],
            "diagnostic": {"indoor": "ok" if indoor is not None else "missing_temperature", "outdoor": "ok" if outdoor is not None else "missing_temperature", "tariff": "ok" if price is not None else "configure_tariff", "loss": "ok" if finite(loss) is not None and finite(loss)>0 else "configure_model", "index_enabled": bool(d.get("use_index")), "index_available": raw_index is not None},
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
        runtime=self.hass.data["smart_heating_energy_manager"][self._entry_id]
        runtime["calibrate_now"]=self.request_calibration
        self.async_on_remove(lambda:runtime.pop("calibrate_now",None))
        self.async_on_remove(async_track_time_interval(self.hass, self._refresh, timedelta(days=1)))
        self.async_on_remove(self.hass.async_create_task(self._refresh()).cancel)

    async def request_calibration(self):
        if self._config.get("calibration_locked",False):
            return "locked"
        if not self._config.get("history_enabled",False):
            return "disabled"
        if self._lock.locked():
            return "busy"
        await self._refresh()
        return self._attr_native_value

    async def _refresh(self, now=None):
        if self._lock.locked():
            return
        async with self._lock:
            self._attr_native_value="running"
            self.async_write_ha_state()
            try:
                from .recorder_adapter import async_calibrate
                runtime = self.hass.data["smart_heating_energy_manager"][self._entry_id]
                if self._config.get("calibration_locked",False):
                    result = {"status":"locked"}
                elif not self._config.get("history_enabled",False):
                    result = {"status":"disabled"}
                elif "recorder" not in self.hass.config.components:
                    result = {"status": "recorder_unavailable"}
                else:
                    config=reference_config(self._config,zone_view(discover_areas(self.hass),self._config.get("zones",{}),self._config.get("outdoor")))
                    result = await async_calibrate(self.hass, config)
                    record = accepted(result,config)
                    if result.get("status")=="estimated" and not record:
                        result={**result,"status":"rejected_fit"}
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

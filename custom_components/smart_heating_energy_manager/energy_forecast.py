"""Read-only energy and forecast sensors; no device service calls."""
from datetime import timedelta
import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from .prediction import kw, number, plan
from .generators import Generator
from .onboarding import ready
from .thermal_zones import parse_curve, cop_at
from .learned import effective_loss
from .model import electricity_price
from .areas import discover_areas, zone_view
from .temperature_zones import reference_config

_LOGGER=logging.getLogger(__name__)
DOMAIN="smart_heating_energy_manager"

class EnergyForecast(SensorEntity):
    _attr_name="Energy and forecast"
    _attr_should_poll=False
    def __init__(self,entry):
        self.config={**entry.data,**entry.options}
        self.entry_id=entry.entry_id
        self._attr_unique_id=f"{entry.entry_id}_energy_forecast"
        self._attr_native_value="pending"
        self._task=None
        self._forecast_attrs={}
        self._live_attrs={}
        self._refreshing=False
        self._base_profile={}
        self._profile_date=None
        self._validation_rows=[]
        self._validation_store=None
        self._validation_lock=None
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        import asyncio
        from homeassistant.helpers.storage import Store
        self._validation_lock=asyncio.Lock()
        self._validation_store=Store(self.hass,1,f"{DOMAIN}.{self.entry_id}.forecasts")
        saved=await self._validation_store.async_load()
        self._validation_rows=saved if isinstance(saved,list) else []
        self.async_on_remove(async_track_time_interval(self.hass,self._observe_forecasts,timedelta(minutes=2)))
        self.async_on_remove(async_track_time_interval(self.hass,self.refresh,timedelta(minutes=15)))
        self.async_on_remove(async_track_time_interval(self.hass,self.refresh_live,timedelta(seconds=30)))
        self._task=self.hass.async_create_task(self.refresh())
        self.async_on_remove(self._task.cancel)
    def _validation_reference(self):
        from .learned import fingerprint
        ref=reference_config(self.config,zone_view(discover_areas(self.hass),self.config.get("zones",{}),self.config.get("outdoor")))
        def read(entity):
            s=self.hass.states.get(entity) if entity else None
            if s is None or dt_util.utcnow()-s.last_updated>timedelta(minutes=30):
                return None
            v=number(s.state)
            unit=s.attributes.get("unit_of_measurement")
            return v if unit=="°C" else (v-32)*5/9 if unit=="°F" and v is not None else None
        from .temperature_zones import average_temperature
        ids=ref["indoor_reference"]
        indoor,n=average_temperature(ids,read)
        return fingerprint(ref),indoor if ids and n==len(ids) else None,read(ref["outdoor_reference"])

    async def _observe_forecasts(self,now=None):
        from .forecast_validation import observe,summarize
        if not self._validation_store:
            return
        async with self._validation_lock:
            reference,indoor,outdoor=self._validation_reference()
            self._validation_rows=observe(self._validation_rows,dt_util.utcnow(),reference,indoor,outdoor)
            await self._validation_store.async_save(self._validation_rows)
            self._forecast_attrs["forecast_validation"]=summarize(self._validation_rows,reference)
            self._attr_extra_state_attributes={**self._forecast_attrs,**self._live_attrs}
            self.async_write_ha_state()

    def read(self,key,power=False):
        entity=self.config.get(key)
        s=self.hass.states.get(entity) if entity else None
        if not s:
            return None
        unit=s.attributes.get("unit_of_measurement")
        return kw(s.state,unit) if power else number(s.state) if unit=="%" else None
    async def refresh_live(self,now=None):
        d=self.config
        pv=self.read("pv_power",True)
        export=self.read("grid_export",True)
        soc=self.read("battery_soc")
        attrs={"pv_kw":pv if pv is not None and pv>=0 else None,
               "export_kw":max(0,export) if export is not None else None,
               "battery_soc":soc if soc is not None and 0<=soc<=100 else None,
               "mode":"advisory"}
        from .energy_import import async_snapshot
        try:
            imported=await async_snapshot(self.hass)
        except Exception:
            _LOGGER.exception("Energy dashboard import unavailable")
            imported={}
        attrs["energy_dashboard_sources"]=imported.get("energy_dashboard_sources",{})
        attrs["energy_origins"]={}
        for field,manual in (("pv_kw","pv_power"),("export_kw","grid_export"),("battery_soc","battery_soc")):
            if imported.get(field) is not None:
                attrs[field]=imported[field]
                attrs["energy_origins"][field]="energy_dashboard"
            else:
                attrs["energy_origins"][field]="manual" if attrs[field] is not None else "unavailable"
        attrs["energy_manual_entities"]={k:d.get(k) for k in ("pv_power","grid_export","battery_soc")}
        attrs["energy_manual_updated"]={k:s.last_updated.isoformat() for k in attrs["energy_manual_entities"] if (s:=self.hass.states.get(d[k]) if d.get(k) else None) is not None}
        attrs["energy_power_entities"]=imported.get("energy_power_entities",{})
        manual_pv=d.get("pv_power") or ""
        if attrs["energy_origins"]["pv_kw"]=="manual" and (
            manual_pv in attrs["energy_power_entities"].get("home",[])
            or manual_pv.endswith(("_consumption_ct_power","_consumption_power","_home_power"))):
            attrs["pv_kw"]=None
            attrs["energy_origins"]["pv_kw"]="conflicting_source"
        attrs["energy_flow_origins"]=imported.get("energy_flow_origins",{})
        attrs["grid_net_kw"]=imported.get("grid_net_kw")
        attrs["battery_net_kw"]=imported.get("battery_net_kw")
        attrs["home_kw"]=imported.get("home_kw")
        attrs["battery_capacity_kwh"]=imported.get("battery_capacity_kwh")
        from .dhw import snapshot, solar_window
        dhw=snapshot(d.get("dhw",{}),self.hass.states.get)
        if dhw:
            dhw["solar_window"]=solar_window(self._forecast_attrs.get("solar_forecast",[]),dhw.get("ideal_heat_kwh"),dhw.get("rated_kw"),dt_util.utcnow()) if dhw.get("below_minimum") is False else None
        attrs["dhw"]=dhw
        self._live_attrs=attrs
        self._attr_extra_state_attributes={**self._forecast_attrs,**self._live_attrs}
        self.async_write_ha_state()

    async def refresh(self,now=None):
        if self._refreshing:
            return
        self._refreshing=True
        try:
            await self._refresh_forecast()
        finally:
            self._refreshing=False

    async def _refresh_forecast(self):
        from datetime import timezone
        from .solar_prediction import async_solar
        d=self.config
        await self.refresh_live()
        attrs={"plan":[],"forecast":[],"price_assumption":"current_price_constant","solar_assumption":"future_surplus_unknown","model":"steady_state"}
        try:
            solar=await async_solar(self.hass,self._live_attrs.get("energy_dashboard_sources",{}))
        except Exception:
            _LOGGER.exception("Solar forecast unavailable")
            solar={}
        now=dt_util.utcnow()
        attrs["solar_forecast"]=[{"datetime":t,"pv_kwh":v} for t,v in solar.items() if now<=dt_util.parse_datetime(t)<now+timedelta(hours=24)]
        price=None
        status="configure_weather"
        weather=d.get("weather")
        if weather:
            try:
                response=await self.hass.services.async_call("weather","get_forecasts",
                    {"entity_id":weather,"type":"hourly"},blocking=True,return_response=True)
                state=self.hass.states.get(weather)
                unit=state.attributes.get("temperature_unit") if state else None
                hours=[]
                for h in response.get(weather,{}).get("forecast",[]):
                    t=number(h.get("temperature"))
                    stamp=dt_util.parse_datetime(h.get("datetime",""))
                    if t is None or stamp is None or stamp.tzinfo is None or stamp<dt_util.utcnow()-timedelta(hours=1):
                        continue
                    if unit=="°F":
                        t=(t-32)*5/9
                    elif unit!="°C":
                        continue
                    hours.append({"datetime":stamp.isoformat(),"temperature_c":t})
                hours=sorted(hours,key=lambda x:x["datetime"])[:24]
                attrs["forecast"]=hours
                ref=reference_config(d,zone_view(discover_areas(self.hass),d.get("zones",{}),d.get("outdoor")))
                loss,source=effective_loss(ref,self.hass.data[DOMAIN][self.entry_id]["learned"])
                from homeassistant.helpers import entity_registry as er
                from .tariff_discovery import candidates
                found=candidates(er.async_get(self.hass).entities.values(),self.hass.states.get)
                index_id=d.get("pun") or (found[0] if len(found)==1 else None)
                index=self.hass.states.get(index_id) if d.get("use_index") and index_id else None
                if index and dt_util.utcnow()-index.last_updated>timedelta(hours=d.get("index_max_age_hours",36)):
                    index=None
                price,price_source=electricity_price(index.state if index else None,index.attributes.get("unit_of_measurement") if index else None,d.get("fixed"),d.get("spread",0),d.get("losses",0),d.get("variable",0),d.get("tax",0),d.get("vat",0))
                from .hourly_tariff import marginal_forecast, price_at
                future=marginal_forecast(index.attributes,d) if index else {}
                attrs["price_assumption"]="hourly_with_explicit_fallback" if future else "current_price_constant"
                from .bootstrap import declared_capacity, winnet_parameters, advisory_generator
                entries=list(er.async_get(self.hass).entities.values())
                devices={k:declared_capacity(winnet_parameters(v,entries,self.hass.states.get),entries,self.hass.states.get) for k,v in d.get("generators",{}).items()}
                from .learned import cop_context
                cop_info=cop_context(ref,self.hass.data[DOMAIN][self.entry_id]["learned"])
                if cop_info["scope"]=="single_generator" and cop_info["cop"] is not None:
                    for v in devices.values():
                        if v["kind"]=="heat_pump":
                            v["_learned_cop"]=cop_info["cop"]
                thermal_hours=[]
                for h in hours:
                    gs=[]
                    for k,v in devices.items():
                        generator=advisory_generator(v,k,h["temperature_c"])
                        if generator is not None:
                            gs.append(generator)
                    stamp=dt_util.parse_datetime(h["datetime"]).astimezone(timezone.utc).replace(minute=0,second=0,microsecond=0).isoformat()
                    pv=solar.get(stamp)
                    hourly_price,origin=price_at(h["datetime"],future,price,price_source)
                    thermal_hours.append({**h,"generators":gs,"pv_kwh":pv,"price":hourly_price})
                    for row in plan([h],loss,d.get("forecast_target"),gs,hourly_price):
                        row["electricity_price"]=hourly_price
                        row["price_source"]=origin
                        row["pv_forecast_kwh"]=pv
                        # Gross production is not free surplus; report potential overlap only.
                        chosen=next((g for g in gs if g.identifier==row["generator"]),None)
                        electric=row["heat_kw"]/chosen.efficiency if chosen and chosen.kind!="fuel" else None
                        row["electricity_kwh"]=round(electric,3) if electric is not None else 0 if chosen or row["heat_kw"]==0 else None
                        row["fuel_cost"]=row["cost_per_hour"] if chosen and chosen.kind=="fuel" else 0 if chosen or row["heat_kw"]==0 else None
                        row["potential_solar_overlap_kwh"]=round(min(electric,pv),3) if electric is not None and pv is not None else None
                        row["generator_name"]=devices.get(row["generator"],{}).get("name")
                        attrs["plan"].append(row)
                from .learned import current
                from .thermal_prediction import simulate
                from .temperature_zones import average_temperature
                record=current(self.hass.data[DOMAIN][self.entry_id]["learned"],ref)
                capacity=record["fit"]["capacity_kwh_k"] if source=="learned" and record else d.get("thermal_capacity")
                if capacity is None:
                    from .bootstrap import building_estimate
                    _,capacity=building_estimate(d)
                def read_temperature(entity):
                    state=self.hass.states.get(entity)
                    if not state:
                        return None
                    value=number(state.state)
                    unit=state.attributes.get("unit_of_measurement")
                    return value if unit=="°C" else (value-32)*5/9 if unit=="°F" and value is not None else None
                ids=ref["indoor_reference"]
                indoor,count=average_temperature(ids,read_temperature)
                attrs["thermal_prediction"]=simulate(thermal_hours,indoor if count==len(ids) else None,loss,capacity,d.get("forecast_target"),d.get("preheat_margin") or 0,now,d.get("solar_gain_factor") or 0)
                attrs["thermal_prediction"]["parameter_source"]=source
                status="estimated" if attrs["plan"] else "configure_model" if hours else "forecast_unavailable"
            except Exception:
                _LOGGER.exception("Hourly weather forecast unavailable")
                status="forecast_unavailable"
        settings=d.get("joint_plan",{})
        if settings.get("enabled"):
            from .joint_plan import optimize
            battery={}
            if settings.get("use_battery"):
                battery={**settings,"soc":self._live_attrs.get("battery_soc")}
                if battery.get("capacity") is None:
                    battery["capacity"]=self._live_attrs.get("battery_capacity_kwh")
            elif self._live_attrs.get("energy_dashboard_sources",{}).get("battery"):
                attrs["joint_plan"]={"status":"battery_not_modeled"}
            base=settings.get("base_kw")
            if settings.get("base_home_power"):
                excluded=set(settings.get("base_excluded_power",[]))
                electric=[g for g in d.get("generators",{}).values() if g.get("enabled",True) and g.get("kind") in ("heat_pump","resistance")]
                required=[g.get("power_entity") for g in electric]
                if d.get("dhw",{}).get("entity"):
                    required.append(d["dhw"].get("power"))
                if any(not e or e not in excluded for e in required):
                    attrs["joint_plan"]={"status":"configure_excluded_loads"}
                if "joint_plan" not in attrs and self._profile_date!=now.date():
                    try:
                        from .load_profile import async_profile
                        self._base_profile=await async_profile(self.hass,settings)
                        self._profile_date=now.date()
                    except Exception:
                        _LOGGER.exception("Household load history unavailable")
                        self._base_profile={}
                attrs["base_load_profile"]=self._base_profile
                base={}
                for row in attrs["plan"]:
                    stamp=dt_util.parse_datetime(row["datetime"])
                    if stamp and stamp.tzinfo:
                        value=self._base_profile.get(str(dt_util.as_local(stamp).hour),{}).get("kw")
                        if value is not None:
                            base[stamp.astimezone(timezone.utc).isoformat()]=value
            if "joint_plan" not in attrs:
                attrs["joint_plan"]=optimize(attrs["plan"],attrs["solar_forecast"],base,price,self._live_attrs.get("dhw"),battery,now,settings.get("export_price"))
        from .forecast_validation import issue,observe,summarize
        if self._validation_store:
            async with self._validation_lock:
                reference,indoor,outdoor=self._validation_reference()
                issued=dt_util.utcnow()
                self._validation_rows=observe(self._validation_rows,issued,reference,indoor,outdoor)
                if d.get("history_enabled",False):
                    issue(self._validation_rows,issued,reference,attrs["forecast"],attrs.get("thermal_prediction",{}),indoor)
                await self._validation_store.async_save(self._validation_rows)
                attrs["forecast_validation"]=summarize(self._validation_rows,reference)
        self._attr_native_value=status
        self._forecast_attrs=attrs
        self._attr_extra_state_attributes={**self._forecast_attrs,**self._live_attrs}
        self.async_write_ha_state()

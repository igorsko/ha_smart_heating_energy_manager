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
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(async_track_time_interval(self.hass,self.refresh,timedelta(minutes=15)))
        self.async_on_remove(async_track_time_interval(self.hass,self.refresh_live,timedelta(seconds=30)))
        self._task=self.hass.async_create_task(self.refresh())
        self.async_on_remove(self._task.cancel)
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
            if not d.get(manual):
                attrs[field]=imported.get(field)
            attrs["energy_origins"][field]="manual" if d.get(manual) else "energy_dashboard" if attrs[field] is not None else "unavailable"
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
                price,_=electricity_price(index.state if index else None,index.attributes.get("unit_of_measurement") if index else None,d.get("fixed"),d.get("spread",0),d.get("losses",0),d.get("variable",0),d.get("tax",0),d.get("vat",0))
                devices=d.get("generators",{})
                for h in hours:
                    gs=[]
                    for k,v in devices.items():
                        if not ready(v):
                            continue
                        eff=v["efficiency"]
                        if v["kind"]=="heat_pump":
                            eff,_=cop_at(parse_curve(v.get("cop_curve","")),h["temperature_c"],eff)
                        gs.append(Generator(k,v["kind"],eff,v["capacity_kw"],v["fuel_price"],v["fuel_quantity"],v["fuel_energy_kwh"],v["enabled"]))
                    stamp=dt_util.parse_datetime(h["datetime"]).astimezone(timezone.utc).replace(minute=0,second=0,microsecond=0).isoformat()
                    pv=solar.get(stamp)
                    for row in plan([h],loss,d.get("forecast_target"),gs,price):
                        row["pv_forecast_kwh"]=pv
                        # Gross production is not free surplus; report potential overlap only.
                        chosen=next((g for g in gs if g.identifier==row["generator"]),None)
                        electric=row["heat_kw"]/chosen.efficiency if chosen and chosen.kind!="fuel" else None
                        row["electricity_kwh"]=round(electric,3) if electric is not None else 0 if chosen or row["heat_kw"]==0 else None
                        row["fuel_cost"]=row["cost_per_hour"] if chosen and chosen.kind=="fuel" else 0 if chosen or row["heat_kw"]==0 else None
                        row["potential_solar_overlap_kwh"]=round(min(electric,pv),3) if electric is not None and pv is not None else None
                        row["generator_name"]=devices.get(row["generator"],{}).get("name")
                        attrs["plan"].append(row)
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
            if "joint_plan" not in attrs:
                attrs["joint_plan"]=optimize(attrs["plan"],attrs["solar_forecast"],settings.get("base_kw"),price,self._live_attrs.get("dhw"),battery,now,settings.get("export_price"))
        self._attr_native_value=status
        self._forecast_attrs=attrs
        self._attr_extra_state_attributes={**self._forecast_attrs,**self._live_attrs}
        self.async_write_ha_state()

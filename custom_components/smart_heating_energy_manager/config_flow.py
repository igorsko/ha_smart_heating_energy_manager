"""Configure the advisory integration."""
import voluptuous as vol
from uuid import uuid4
from homeassistant.core import callback
from homeassistant import config_entries
from homeassistant.helpers import selector

DOMAIN = "smart_heating_energy_manager"

class SmartHeatingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DeviceOptionsFlow()

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Smart Heating Energy Manager",data={"history_enabled":True})
        return self.async_show_form(step_id="user",data_schema=vol.Schema({}))

class DeviceOptionsFlow(config_entries.OptionsFlow):
    """Manage optional devices without changing the installation's entity IDs."""

    async def async_step_init(self, user_input=None):
        self.devices = dict(self.config_entry.options.get("generators", self.config_entry.data.get("generators", {})))
        self.options = dict(self.config_entry.options)
        return self.async_show_menu(step_id="init", menu_options=[
            "zones", "zone_thermal", "add_generator", "discover_winnet", "edit_generator", "advanced_generator", "remove_generator", "building", "tariff", "advanced_tariff", "energy_forecast", "joint_plan", "dhw", "advanced_settings", "display", "finish"])

    async def async_step_zones(self,user_input=None):
        from .areas import discover_areas
        areas=discover_areas(self.hass)
        if user_input is not None:
            self._area=user_input["area"]
            return await self.async_step_zone_details()
        return self.async_show_form(step_id="zones",data_schema=vol.Schema({
            vol.Required("area"):vol.In({k:v["name"] for k,v in areas.items()})
        }),errors={"base":"no_areas"} if not areas else {})

    async def async_step_zone_details(self,user_input=None):
        from .areas import discover_areas
        area=discover_areas(self.hass).get(self._area)
        if area is None:
            return await self.async_step_zones()
        zones=dict(self.options.get("zones",self.config_entry.data.get("zones",{})))
        from .temperature_zones import is_outdoor
        old=zones.get(self._area,{})
        outdoor=is_outdoor(self._area,{**area,**old},self.options.get("outdoor",self.config_entry.data.get("outdoor")))
        if user_input is not None:
            from .heat_sources import zone_candidates
            if not set(user_input.get("sources",[])).issubset(zone_candidates(self.hass,self.devices)):
                return await self.async_step_zone_details()
            zones[self._area]={**zones.get(self._area,{}),"temperature":user_input.get("temperature"),
                "sources":[] if outdoor else user_input.get("sources",[]),"confirmed":True}
            self.options["zones"]=zones
            return self._save()
        old=zones.get(self._area,{})
        candidates=area["temperature_candidates"]
        temperature=old.get("temperature") if old.get("confirmed") else candidates[0] if len(candidates)==1 else None
        from .heat_sources import zone_candidates
        allowed=zone_candidates(self.hass,self.devices)
        sources=[s for s in (old.get("sources",[]) if old.get("confirmed") else area["source_candidates"]) if s in allowed]
        fields={
            vol.Optional("temperature",description={"suggested_value":temperature} if temperature else {}):
                selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature")),
            vol.Optional("sources",description={"suggested_value":sources}):
                selector.SelectSelector(selector.SelectSelectorConfig(options=[{"value":s,"label":self.hass.states.get(s).name} for s in allowed],multiple=True,mode=selector.SelectSelectorMode.DROPDOWN))
        }
        if outdoor:
            fields={k:v for k,v in fields.items() if k.schema!="sources"}
        return self.async_show_form(step_id="zone_details",description_placeholders={"area":area["name"]},data_schema=vol.Schema(fields))

    async def async_step_zone_thermal(self,user_input=None):
        from .areas import discover_areas
        from .areas import zone_view
        current={**self.config_entry.data,**self.options}
        areas={k:v for k,v in zone_view(discover_areas(self.hass),current.get("zones",{}),current.get("outdoor")).items() if not v.get("outdoor")}
        if user_input is not None:
            if user_input["area"] not in areas:
                return await self.async_step_zone_thermal()
            self._thermal_area=user_input["area"]
            return await self.async_step_zone_thermal_details()
        return self.async_show_form(step_id="zone_thermal",data_schema=vol.Schema({
            vol.Required("area"):vol.In({k:v["name"] for k,v in areas.items()})
        }),errors={"base":"no_areas"} if not areas else {})

    async def async_step_zone_thermal_details(self,user_input=None):
        zones=dict(self.options.get("zones",self.config_entry.data.get("zones",{})))
        old=zones.get(self._thermal_area,{})
        if user_input is not None:
            zones[self._thermal_area]={**old,"target_c":user_input.get("target_c"),"loss_w_k":user_input.get("loss_w_k")}
            self.options["zones"]=zones
            return self._save()
        def optional(key):
            return vol.Optional(key,description={"suggested_value":old[key]} if old.get(key) is not None else {})
        return self.async_show_form(step_id="zone_thermal_details",data_schema=vol.Schema({
            optional("target_c"):vol.All(vol.Coerce(float),vol.Range(min=5,max=35)),
            optional("loss_w_k"):vol.All(vol.Coerce(float),vol.Range(min=1,max=10000))
        }))

    async def async_step_discover_winnet(self, user_input=None):
        from homeassistant.helpers import entity_registry as er
        from .discovery import suggest
        if user_input is not None:
            mapping = suggest(er.async_get(self.hass).entities.values(), user_input["device"])
            if mapping:
                self._discovered_defaults = {"kind":"fuel","fuel_mass_estimated":True,"fuel_mass_unit":"kg",**mapping}
                return await self.async_step_confirm_discovery()
        return self.async_show_form(step_id="discover_winnet",data_schema=vol.Schema({
            vol.Required("device"): selector.DeviceSelector(selector.DeviceSelectorConfig(integration="winnet_stove"))
        }),errors={"base":"no_discovered_entities"} if user_input is not None else {})

    async def async_step_confirm_discovery(self,user_input=None):
        return await self._simple_generator("confirm_discovery",user_input,str(uuid4()),self._discovered_defaults)

    def _price_suggestion(self,current):
        from homeassistant.helpers import entity_registry as er
        from .tariff_discovery import candidates
        found=candidates(er.async_get(self.hass).entities.values(),self.hass.states.get)
        return current.get("pun") or (found[0] if len(found)==1 else None)

    async def async_step_tariff(self,user_input=None):
        if user_input is not None:
            self.options.update({"fixed":user_input.get("fixed"),"use_index":user_input.get("use_index",False),"pun":user_input.get("pun","")})
            return self._save()
        current={**self.config_entry.data,**self.options}
        return self.async_show_form(step_id="tariff",data_schema=vol.Schema({
            vol.Optional("fixed",description={"suggested_value":current["fixed"]} if current.get("fixed") is not None else {}):vol.All(vol.Coerce(float),vol.Range(min=0,max=10)),
            vol.Required("use_index",default=current.get("use_index",False)):bool,
            vol.Optional("pun",description={"suggested_value":self._price_suggestion(current)} if self._price_suggestion(current) else {}):selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        }))

    async def async_step_advanced_tariff(self,user_input=None):
        if user_input is not None:
            self.options.update(user_input)
            return self._save()
        current = {**self.config_entry.data, **self.options}
        fields = {"spread":0.,"losses":0.,"variable":0.,"tax":0.,"vat":0.}
        schema = {vol.Required(k,default=current.get(k,v)):vol.All(vol.Coerce(float),vol.Range(min=0,max=1 if k in ("vat","losses") else 10)) for k,v in fields.items()}
        return self.async_show_form(step_id="advanced_tariff",data_schema=vol.Schema(schema))

    async def async_step_add_generator(self, user_input=None):
        return await self._simple_generator("add_generator", user_input, str(uuid4()), {})

    async def async_step_edit_generator(self, user_input=None):
        if not self.devices:
            return await self.async_step_init()
        if user_input is not None:
            self.selected = user_input["generator"]
            return await self.async_step_edit_details()
        return self.async_show_form(step_id="edit_generator", data_schema=vol.Schema({
            vol.Required("generator"): vol.In({k:v["name"] for k,v in self.devices.items()})}))

    async def async_step_edit_details(self, user_input=None):
        return await self._simple_generator("edit_details", user_input, self.selected, self.devices[self.selected])

    async def async_step_remove_generator(self, user_input=None):
        if not self.devices:
            return await self.async_step_init()
        if user_input is not None:
            self.devices.pop(user_input["generator"], None)
            return self._save()
        return self.async_show_form(step_id="remove_generator", data_schema=vol.Schema({
            vol.Required("generator"): vol.In({k:v["name"] for k,v in self.devices.items()})}))

    async def async_step_advanced_generator(self,user_input=None):
        if not self.devices:
            return await self.async_step_init()
        if user_input is not None:
            self.selected=user_input["generator"]
            return await self.async_step_advanced_details()
        return self.async_show_form(step_id="advanced_generator",data_schema=vol.Schema({
            vol.Required("generator"):vol.In({k:v["name"] for k,v in self.devices.items()})}))

    async def async_step_advanced_details(self,user_input=None):
        return await self._generator_form("advanced_details",user_input,self.selected,self.devices[self.selected])

    async def _simple_generator(self,step,user_input,key,old):
        from .onboarding import merge_basic
        from homeassistant.helpers import entity_registry as er
        errors={}
        if user_input is not None:
            try:
                entity=user_input.get("control_entity")
                registry=er.async_get(self.hass)
                record=registry.async_get(entity) if entity else None
                state=self.hass.states.get(entity) if entity else None
                name=user_input.get("name","").strip() or (state.name if state else entity)
                if not name:
                    raise ValueError("name")
                data=merge_basic(old,user_input,name)
                if record and record.device_id and (not old.get("control_entity") or old.get("control_entity")==entity):
                    from .onboarding import suggest_sensors
                    siblings=[e for e in registry.entities.values() if e.device_id==record.device_id and not e.disabled_by]
                    found=suggest_sensors(siblings,self.hass.states.get,data["kind"])
                    for field,value in found.items():
                        if not data.get(field):
                            data[field]=value
                self.devices[key]=data
                return self._save()
            except ValueError:
                errors["base"]="invalid_generator"
        defaults={**old,**(user_input or {})}
        schema=vol.Schema({
            vol.Optional("control_entity",description={"suggested_value":defaults["control_entity"]} if defaults.get("control_entity") else {}):selector.EntitySelector(selector.EntitySelectorConfig(domain=["climate","switch","script"])),
            vol.Required("kind",default=defaults.get("kind","heat_pump")):selector.SelectSelector(selector.SelectSelectorConfig(options=["heat_pump","resistance","fuel"],translation_key="generator_kind",mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional("name",description={"suggested_value":defaults["name"]} if defaults.get("name") else {}):str,
        })
        return self.async_show_form(step_id=step,data_schema=schema,errors=errors)

    async def _generator_form(self, step, user_input, key, old):
        errors = {}
        if user_input is not None:
            from .generators import Generator
            try:
                Generator(key, user_input["kind"], user_input["efficiency"],
                          user_input["capacity_kw"], user_input["fuel_price"],
                          user_input["fuel_quantity"], user_input["fuel_energy_kwh"])
                from .fuel import parse_rates
                rates=parse_rates(user_input.get("level_rates",""))
                from .thermal_zones import parse_curve
                curve=parse_curve(user_input.get("cop_curve",""))
                if curve and user_input["kind"]!="heat_pump":
                    raise ValueError("COP curve requires heat pump")
                if rates and (user_input["kind"]!="fuel" or not user_input.get("level_entity") or not user_input.get("state_entity") or user_input["level_entity"]==user_input["state_entity"]):
                    raise ValueError("Level rates require distinct state and level sensors")
                if not user_input["name"].strip():
                    raise ValueError("Empty name")
            except ValueError:
                errors["base"] = "invalid_generator"
            else:
                self.devices[key] = {**old, **user_input, "technical_configured": True}
                return self._save()
        defaults = {**old, **(user_input or {})}
        def required(key, default):
            return vol.Required(key, default=defaults.get(key, default))
        def optional(key):
            return vol.Optional(key, description={"suggested_value": defaults[key]} if key in defaults else {})
        positive = vol.All(vol.Coerce(float), vol.Range(min=.001))
        schema = vol.Schema({
            required("name", ""): str,
            required("kind", "heat_pump"): vol.In(["heat_pump","resistance","fuel"]),
            required("efficiency", 1.0): positive,
            required("cop_curve", ""): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            required("capacity_kw", 1.0): positive,
            required("fuel_price", 0.0): vol.All(vol.Coerce(float),vol.Range(min=0)),
            required("fuel_quantity", 1.0): positive,
            required("fuel_energy_kwh", 1.0): positive,
            required("enabled", True): bool,
            required("energy_is_useful_heat", False): bool,
            required("manual_input_rate", 0.0): vol.All(vol.Coerce(float),vol.Range(min=0,max=10000)),
            required("fuel_mass_unit", "kg"): vol.In(["g","kg","t","lb"]),
            required("level_rates", ""): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            required("fuel_mass_estimated", False): bool,
            optional("fuel_rate_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            optional("fuel_mass_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            optional("level_entity"): selector.EntitySelector(),
            required("active_states", ""): str,
            required("inactive_states", ""): str,
            optional("control_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain=["climate","switch","script"])),
            optional("state_entity"): selector.EntitySelector(),
            optional("energy_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="energy")),
            optional("power_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="power")),
            optional("temperature_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature")),
        })
        return self.async_show_form(step_id=step,data_schema=schema,errors=errors)

    async def async_step_building(self,user_input=None):
        if user_input is not None:
            self.options["outdoor"]=user_input.get("outdoor")
            return self._save()
        current={**self.config_entry.data,**self.options}
        return self.async_show_form(step_id="building",data_schema=vol.Schema({
            vol.Optional(k,description={"suggested_value":current[k]} if current.get(k) else {}):selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature"))
            for k in ("outdoor",)}))

    async def async_step_advanced_settings(self, user_input=None):
        if user_input is not None:
            if user_input.pop("reset_calibration",False):
                self.options["calibration_generation"] = self.options.get("calibration_generation",0)+1
            self.options.update(user_input)
            for field in ("h","building_area","building_profile"):
                self.options[field] = user_input.get(field)
            return self._save()
        current = {**self.config_entry.data, **self.options}
        schema = vol.Schema({
            vol.Optional("building_area",description={"suggested_value":current["building_area"]} if current.get("building_area") else {}):vol.All(vol.Coerce(float),vol.Range(min=5,max=10000)),
            vol.Optional("building_profile",default=current.get("building_profile") or "medium"):vol.In(["low_loss","medium","high_loss"]),
            vol.Optional("h",description={"suggested_value":current["h"]} if current.get("h") else {}): vol.All(vol.Coerce(float),vol.Range(min=1,max=10000)),
            vol.Required("index_max_age_hours",default=current.get("index_max_age_hours",36)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=744)),
            vol.Required("apply_learned",default=current.get("apply_learned",False)): bool,
            vol.Required("calibration_locked",default=current.get("calibration_locked",False)): bool,
            vol.Required("reset_calibration",default=False): bool,
            vol.Required("history_enabled",default=current.get("history_enabled",False)): bool,
            vol.Required("history_min_coverage",default=current.get("history_min_coverage",.7)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=1)),
            vol.Required("history_days",default=current.get("history_days",7)): vol.All(vol.Coerce(int),vol.Range(min=1,max=30)),
            vol.Required("history_interval_minutes",default=current.get("history_interval_minutes",60)): vol.All(vol.Coerce(int),vol.Range(min=15,max=360)),
            vol.Required("history_max_age_hours",default=current.get("history_max_age_hours",2)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=24)),
        })
        return self.async_show_form(step_id="advanced_settings",data_schema=schema)

    async def async_step_energy_forecast(self,user_input=None):
        current={**self.config_entry.data,**self.options}
        if user_input is not None:
            for field in ("pv_power","grid_export","battery_soc","weather","forecast_target","thermal_capacity","preheat_margin","solar_gain_factor"):
                self.options[field]=user_input.get(field)
            return self._save()
        def optional(k):
            return vol.Optional(k,description={"suggested_value":current[k]} if current.get(k) is not None else {})
        power=selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="power"))
        return self.async_show_form(step_id="energy_forecast",data_schema=vol.Schema({
            optional("pv_power"):power,
            optional("grid_export"):power,
            optional("battery_soc"):selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="battery")),
            optional("weather"):selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            optional("forecast_target"):vol.All(vol.Coerce(float),vol.Range(min=5,max=35)),
            optional("thermal_capacity"):vol.All(vol.Coerce(float),vol.Range(min=.1,max=200)),
            optional("preheat_margin"):vol.All(vol.Coerce(float),vol.Range(min=0,max=3)),
            optional("solar_gain_factor"):vol.All(vol.Coerce(float),vol.Range(min=0,max=10))
        }))

    async def async_step_joint_plan(self,user_input=None):
        current=self.options.get("joint_plan",{})
        if user_input is not None:
            self.options["joint_plan"]=dict(user_input)
            return self._save()
        def opt(k):
            return vol.Optional(k,description={"suggested_value":current[k]} if current.get(k) is not None else {})
        def numeric(lo,hi):
            return vol.All(vol.Coerce(float),vol.Range(min=lo,max=hi))
        return self.async_show_form(step_id="joint_plan",data_schema=vol.Schema({
            vol.Required("enabled",default=current.get("enabled",False)):bool,
            opt("base_kw"):numeric(0,50),
            opt("base_home_power"):selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="power")),
            opt("base_excluded_power"):selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="power",multiple=True)),
            opt("export_price"):numeric(0,10),
            vol.Required("use_battery",default=current.get("use_battery",False)):bool,
            opt("capacity"):numeric(.1,1000),
            opt("reserve"):numeric(0,100),
            opt("charge_kw"):numeric(.01,100),
            opt("discharge_kw"):numeric(.01,100),
            opt("efficiency"):numeric(.1,1),
        }))

    async def async_step_dhw(self,user_input=None):
        current=self.options.get("dhw",self.config_entry.data.get("dhw",{}))
        if user_input is not None:
            if user_input.get("minimum_c") is not None and user_input.get("target_c") is not None and user_input["minimum_c"]>user_input["target_c"]:
                return self.async_show_form(step_id="dhw",data_schema=self._dhw_schema(user_input),errors={"base":"invalid_dhw_temperatures"})
            self.options["dhw"]=dict(user_input) if user_input.get("entity") else {}
            return self._save()
        return self.async_show_form(step_id="dhw",data_schema=self._dhw_schema(current))

    def _dhw_schema(self,current):
        def opt(k):
            return vol.Optional(k,description={"suggested_value":current[k]} if current.get(k) is not None else {})
        def numeric(lo,hi):
            return vol.All(vol.Coerce(float),vol.Range(min=lo,max=hi))
        return vol.Schema({
            opt("entity"):selector.EntitySelector(selector.EntitySelectorConfig(domain=["water_heater","switch","climate"])),
            opt("temperature"):selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature")),
            opt("power"):selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="power")),
            opt("energy"):selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="energy")),
            opt("litres"):numeric(1,5000),
            opt("rated_kw"):numeric(.05,50),
            opt("minimum_c"):numeric(0,100),
            opt("target_c"):numeric(0,100),
        })

    async def async_step_display(self, user_input=None):
        if user_input is not None:
            self.options.update(user_input)
            return self._save()
        return self.async_show_form(step_id="display",data_schema=vol.Schema({
            vol.Required("show_panel",default=self.options.get("show_panel",True)):bool
        }))

    async def async_step_finish(self, user_input=None):
        return self._save()

    def _save(self):
        self.options["generators"] = self.devices
        return self.async_create_entry(title="", data=self.options)

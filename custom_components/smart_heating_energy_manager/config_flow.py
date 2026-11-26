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
        self.devices = dict(self.config_entry.options.get("generators", {}))
        self.options = dict(self.config_entry.options)
        return self.async_show_menu(step_id="init", menu_options=[
            "zones", "add_generator", "discover_winnet", "edit_generator", "remove_generator", "building", "tariff", "display", "finish"])

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
        if user_input is not None:
            zones[self._area]={"temperature":user_input.get("temperature"),
                "sources":user_input.get("sources",[]),"confirmed":True}
            self.options["zones"]=zones
            return self._save()
        old=zones.get(self._area,{})
        candidates=area["temperature_candidates"]
        temperature=old.get("temperature") if old.get("confirmed") else candidates[0] if len(candidates)==1 else None
        sources=old.get("sources",[]) if old.get("confirmed") else area["source_candidates"]
        return self.async_show_form(step_id="zone_details",description_placeholders={"area":area["name"]},data_schema=vol.Schema({
            vol.Optional("temperature",description={"suggested_value":temperature} if temperature else {}):
                selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature")),
            vol.Optional("sources",description={"suggested_value":sources}):
                selector.EntitySelector(selector.EntitySelectorConfig(domain=["climate","switch","script"],multiple=True))
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
        return await self._generator_form("confirm_discovery",user_input,str(uuid4()),self._discovered_defaults)

    async def async_step_tariff(self,user_input=None):
        if user_input is not None:
            self.options.update(user_input)
            self.options["fixed"] = user_input.get("fixed")
            self.options["pun"] = user_input.get("pun","")
            return self._save()
        current = {**self.config_entry.data, **self.options}
        fields = {"spread":0.,"losses":0.,"variable":0.,"tax":0.,"vat":0.}
        schema = {vol.Required(k,default=current.get(k,v)):vol.All(vol.Coerce(float),vol.Range(min=0,max=1 if k in ("vat","losses") else 10)) for k,v in fields.items()}
        schema[vol.Optional("fixed",description={"suggested_value":current["fixed"]} if current.get("fixed") is not None else {})]=vol.All(vol.Coerce(float),vol.Range(min=0,max=10))
        schema[vol.Required("use_index",default=current.get("use_index",False))]=bool
        schema[vol.Optional("pun",description={"suggested_value":current["pun"]} if current.get("pun") else {})]=selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        return self.async_show_form(step_id="tariff",data_schema=vol.Schema(schema))

    async def async_step_add_generator(self, user_input=None):
        return await self._generator_form("add_generator", user_input, str(uuid4()), {})

    async def async_step_edit_generator(self, user_input=None):
        if not self.devices:
            return await self.async_step_init()
        if user_input is not None:
            self.selected = user_input["generator"]
            return await self.async_step_edit_details()
        return self.async_show_form(step_id="edit_generator", data_schema=vol.Schema({
            vol.Required("generator"): vol.In({k:v["name"] for k,v in self.devices.items()})}))

    async def async_step_edit_details(self, user_input=None):
        return await self._generator_form("edit_details", user_input, self.selected, self.devices[self.selected])

    async def async_step_remove_generator(self, user_input=None):
        if not self.devices:
            return await self.async_step_init()
        if user_input is not None:
            self.devices.pop(user_input["generator"], None)
            return self._save()
        return self.async_show_form(step_id="remove_generator", data_schema=vol.Schema({
            vol.Required("generator"): vol.In({k:v["name"] for k,v in self.devices.items()})}))

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
                if rates and (user_input["kind"]!="fuel" or not user_input.get("level_entity") or not user_input.get("state_entity") or user_input["level_entity"]==user_input["state_entity"]):
                    raise ValueError("Level rates require distinct state and level sensors")
                if not user_input["name"].strip():
                    raise ValueError("Empty name")
            except ValueError:
                errors["base"] = "invalid_generator"
            else:
                self.devices[key] = user_input
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

    async def async_step_building(self, user_input=None):
        if user_input is not None:
            self.options.update(user_input)
            for field in ("indoor","outdoor","h"):
                self.options[field] = user_input.get(field)
            return self._save()
        current = {**self.config_entry.data, **self.options}
        schema = vol.Schema({
            vol.Optional("indoor",description={"suggested_value":current["indoor"]} if current.get("indoor") else {}): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature")),
            vol.Optional("outdoor",description={"suggested_value":current["outdoor"]} if current.get("outdoor") else {}): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature")),
            vol.Optional("h",description={"suggested_value":current["h"]} if current.get("h") else {}): vol.All(vol.Coerce(float),vol.Range(min=1,max=10000)),
            vol.Required("index_max_age_hours",default=current.get("index_max_age_hours",36)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=744)),
            vol.Required("history_enabled",default=current.get("history_enabled",False)): bool,
            vol.Required("history_min_coverage",default=current.get("history_min_coverage",.7)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=1)),
            vol.Required("history_days",default=current.get("history_days",7)): vol.All(vol.Coerce(int),vol.Range(min=1,max=30)),
            vol.Required("history_interval_minutes",default=current.get("history_interval_minutes",60)): vol.All(vol.Coerce(int),vol.Range(min=15,max=360)),
            vol.Required("history_max_age_hours",default=current.get("history_max_age_hours",2)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=24)),
        })
        return self.async_show_form(step_id="building",data_schema=schema)

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

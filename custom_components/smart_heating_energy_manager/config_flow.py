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
            return self.async_create_entry(title="Smart Heating Energy Manager", data=user_input)
        number = lambda low, high: vol.All(vol.Coerce(float), vol.Range(min=low, max=high))
        schema = vol.Schema({
            vol.Required("indoor"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            vol.Required("outdoor"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            vol.Optional("pun"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required("use_index", default=False): bool,
            vol.Required("fixed", default=0.30): number(0, 10),
            vol.Required("spread", default=0.0): number(0, 10),
            vol.Required("losses", default=0.0): number(0, 1),
            vol.Required("variable", default=0.0): number(0, 10),
            vol.Required("tax", default=0.0): number(0, 10),
            vol.Required("vat", default=0.0): number(0, 1),
            vol.Required("h"): number(1, 10000),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

class DeviceOptionsFlow(config_entries.OptionsFlow):
    """Manage optional devices without changing the installation's entity IDs."""

    async def async_step_init(self, user_input=None):
        self.devices = dict(self.config_entry.options.get("generators", {}))
        self.options = dict(self.config_entry.options)
        return self.async_show_menu(step_id="init", menu_options=[
            "add_generator", "edit_generator", "remove_generator", "building", "finish"])

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
            return self._save()
        current = {**self.config_entry.data, **self.options}
        schema = vol.Schema({
            vol.Required("indoor",default=current["indoor"]): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature")),
            vol.Required("outdoor",default=current["outdoor"]): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor",device_class="temperature")),
            vol.Required("h",default=current["h"]): vol.All(vol.Coerce(float),vol.Range(min=1,max=10000)),
            vol.Required("index_max_age_hours",default=current.get("index_max_age_hours",36)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=744)),
            vol.Required("history_enabled",default=current.get("history_enabled",False)): bool,
            vol.Required("history_min_coverage",default=current.get("history_min_coverage",.7)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=1)),
            vol.Required("history_days",default=current.get("history_days",7)): vol.All(vol.Coerce(int),vol.Range(min=1,max=30)),
            vol.Required("history_interval_minutes",default=current.get("history_interval_minutes",60)): vol.All(vol.Coerce(int),vol.Range(min=15,max=360)),
            vol.Required("history_max_age_hours",default=current.get("history_max_age_hours",2)): vol.All(vol.Coerce(float),vol.Range(min=.1,max=24)),
        })
        return self.async_show_form(step_id="building",data_schema=schema)

    async def async_step_finish(self, user_input=None):
        return self._save()

    def _save(self):
        self.options["generators"] = self.devices
        return self.async_create_entry(title="", data=self.options)

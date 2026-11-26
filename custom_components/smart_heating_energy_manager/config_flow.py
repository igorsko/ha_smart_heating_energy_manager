"""Configure the advisory integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

DOMAIN = "smart_heating_energy_manager"

class SmartHeatingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
            vol.Required("cop"): number(1, 10),
            vol.Required("pellet_price"): number(0.01, 1000),
            vol.Required("pellet_mass", default=15): number(0.1, 1000),
            vol.Required("lhv", default=4.8): number(1, 10),
            vol.Required("efficiency", default=0.9): number(0.1, 1),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

"""Smart Heating Energy Manager."""
from homeassistant.const import Platform
from homeassistant.helpers.storage import Store
from .learned import current

DOMAIN = 'smart_heating_energy_manager'

async def async_setup_entry(hass, entry):
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.calibration")
    config = {**entry.data, **entry.options}
    saved = current(await store.async_load(), config)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"store":store,"learned":saved}
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True

async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id,None)
    return unloaded

async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_remove_entry(hass, entry):
    await Store(hass,1,f"{DOMAIN}.{entry.entry_id}.calibration").async_remove()

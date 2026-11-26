"""Smart Heating Energy Manager."""
import asyncio
import logging
from homeassistant.const import Platform

DOMAIN = "smart_heating_energy_manager"
_LOGGER = logging.getLogger(__name__)

async def _update_ui(hass, entry, loaded):
    state = hass.data.setdefault(DOMAIN+"_ui", {})
    lock = state.setdefault("lock", asyncio.Lock())
    async with lock:
        entries = state.setdefault("loaded", set())
        if loaded:
            entries.add(entry.entry_id)
        else:
            entries.discard(entry.entry_id)
        try:
            from .ui import async_update_ui
            await async_update_ui(hass)
        except Exception:
            _LOGGER.exception("Unable to register Smart Heating panel; sensors remain operational")

async def async_setup_entry(hass, entry):
    state = hass.data.setdefault(DOMAIN+"_ui", {})
    if not state.get("zone_api_registered"):
        from .zone_api import register
        register(hass)
        state["zone_api_registered"] = True
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    entry.async_on_unload(entry.add_update_listener(_reload))
    await _update_ui(hass, entry, True)
    return True

async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
    if unloaded:
        await _update_ui(hass, entry, False)
    return unloaded

async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

"""Authenticated admin-only zone configuration over Home Assistant WebSocket."""
import voluptuous as vol
from homeassistant.components import websocket_api
from .areas import discover_areas, zone_view

DOMAIN = "smart_heating_energy_manager"

def _entry(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    return entry if entry and entry.domain == DOMAIN else None

@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN+"/zones",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def zones(hass, connection, msg):
    connection.require_admin()
    entry = _entry(hass,msg["entry_id"])
    if entry is None:
        connection.send_error(msg["id"],"not_found","Integration not found")
        return
    data={**entry.data,**entry.options}
    connection.send_result(msg["id"],zone_view(discover_areas(hass),data.get("zones",{})))

@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN+"/save_zone",
    vol.Required("entry_id"): str,
    vol.Required("area_id"): str,
    vol.Required("temperature"): vol.Any(None,str),
    vol.Required("sources"): [str],
})
@websocket_api.async_response
async def save_zone(hass, connection, msg):
    connection.require_admin()
    entry=_entry(hass,msg["entry_id"])
    areas=discover_areas(hass)
    if entry is None or msg["area_id"] not in areas:
        connection.send_error(msg["id"],"not_found","Integration or area not found")
        return
    options=dict(entry.options)
    saved=dict(options.get("zones",entry.data.get("zones",{})))
    previous=saved.get(msg["area_id"],{})
    temperature=msg["temperature"]
    if temperature and temperature != previous.get("temperature"):
        state=hass.states.get(temperature)
        if not temperature.startswith("sensor.") or state is None or (
            state.attributes.get("device_class")!="temperature" and
            state.attributes.get("unit_of_measurement") not in ("°C","°F")):
            connection.send_error(msg["id"],"invalid_format","Select a temperature sensor")
            return
    sources=list(dict.fromkeys(msg["sources"]))
    if any(not s.startswith(("climate.","switch.","script.")) or (hass.states.get(s) is None and s not in previous.get("sources",[])) for s in sources):
        connection.send_error(msg["id"],"invalid_format","Invalid heating source")
        return
    saved[msg["area_id"]]={**previous,"temperature":temperature,"sources":sources,"confirmed":True}
    options["zones"]=saved
    hass.config_entries.async_update_entry(entry,options=options)
    connection.send_result(msg["id"],zone_view(areas,saved))

def register(hass):
    websocket_api.async_register_command(hass,zones)
    websocket_api.async_register_command(hass,save_zone)

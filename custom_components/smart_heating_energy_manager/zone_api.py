"""Authenticated admin-only zone configuration over Home Assistant WebSocket."""
import voluptuous as vol
from homeassistant.components import websocket_api
from .areas import discover_areas, zone_view
from .temperature_zones import is_outdoor
from .thermal_groups import group_name
from .heat_sources import eligible, configured_sources

DOMAIN = "smart_heating_energy_manager"

def _entry(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    return entry if entry and entry.domain == DOMAIN else None

@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN+"/zones",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def zones(hass, connection, msg):
    entry = _entry(hass,msg["entry_id"])
    if entry is None:
        connection.send_error(msg["id"],"not_found","Integration not found")
        return
    data={**entry.data,**entry.options}
    connection.send_result(msg["id"],zone_view(discover_areas(hass),data.get("zones",{}),data.get("outdoor")))

@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN+"/save_zone",
    vol.Required("entry_id"): str,
    vol.Required("area_id"): str,
    vol.Required("temperature"): vol.Any(None,str),
    vol.Required("sources"): [str],
    vol.Optional("thermal_group"): str,
})
@websocket_api.async_response
async def save_zone(hass, connection, msg):
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
    outdoor=is_outdoor(msg["area_id"],{**areas[msg["area_id"]],**previous,"temperature":temperature},options.get("outdoor",entry.data.get("outdoor")))
    sources=[] if outdoor else list(dict.fromkeys(msg["sources"]))
    configured=configured_sources(options.get("generators",entry.data.get("generators",{})))
    def allowed(entity):
        state=hass.states.get(entity)
        return state is not None and eligible(entity,state.attributes,entity in configured)
    if any(not allowed(s) for s in sources):
        connection.send_error(msg["id"],"invalid_format","Invalid heating source")
        return
    saved[msg["area_id"]]={**previous,"temperature":temperature,"sources":sources,"confirmed":True,"thermal_group":"" if outdoor else group_name(msg.get("thermal_group",previous.get("thermal_group")))}
    options["zones"]=saved
    try:
        hass.config_entries.async_update_entry(entry,options=options)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Zone configuration save failed")
        connection.send_error(msg["id"],"save_failed","Unable to save zone configuration; see Home Assistant logs")
        return
    connection.send_result(msg["id"],zone_view(areas,saved,options.get("outdoor",entry.data.get("outdoor"))))

@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN+"/calibrate",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def calibrate(hass,connection,msg):
    entry=_entry(hass,msg["entry_id"])
    runtime=hass.data.get(DOMAIN,{}).get(msg["entry_id"],{})
    callback=runtime.get("calibrate_now")
    if entry is None or callback is None:
        connection.send_error(msg["id"],"unavailable","Enable historical calibration first")
        return
    status=await callback()
    connection.send_result(msg["id"],{"status":status})

def register(hass):
    websocket_api.async_register_command(hass,calibrate)
    websocket_api.async_register_command(hass,zones)
    websocket_api.async_register_command(hass,save_zone)

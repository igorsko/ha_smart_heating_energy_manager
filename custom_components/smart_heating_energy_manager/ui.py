"""Register one optional, read-only Home Assistant sidebar panel."""
import logging
from pathlib import Path
from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers import entity_registry as er

DOMAIN = "smart_heating_energy_manager"
PATH = "smart-heating-energy-manager"
JS = "/api/smart_heating_energy_manager/panel.js"
_LOGGER = logging.getLogger(__name__)

async def async_update_ui(hass):
    state = hass.data.setdefault(DOMAIN+"_ui", {})
    entries = [e for e in hass.config_entries.async_entries(DOMAIN)
               if e.entry_id in state.get("loaded", set()) and e.options.get("show_panel", True)]
    if state.get("owned"):
        frontend.async_remove_panel(hass, PATH)
        state["owned"] = False
    if not entries:
        return
    if frontend.async_panel_exists(hass, PATH):
        _LOGGER.warning("Dashboard path already occupied; leaving existing panel unchanged")
        return
    if not state.get("static"):
        await hass.http.async_register_static_paths([StaticPathConfig(
            JS, str(Path(__file__).parent / "frontend" / "panel.js"), cache_headers=False)])
        state["static"] = True
    from .areas import discover_areas, zone_view
    areas = discover_areas(hass)
    registry = er.async_get(hass)
    config = []
    for entry in entries:
        data = {**entry.data, **entry.options}
        prefix = entry.entry_id+"_"
        entities = {e.unique_id[len(prefix):]:e.entity_id for e in registry.entities.values()
                    if e.platform == DOMAIN and e.config_entry_id == entry.entry_id
                    and not e.disabled_by and e.unique_id.startswith(prefix)}
        from .calibration_inputs import calibration_inputs
        resolved,_=calibration_inputs(data.get("generators",{}),registry.entities.values(),hass.states.get)
        config.append({"title": entry.title, "id": entry.entry_id, "entities": entities,
                       "indoor":data.get("indoor"),"outdoor":data.get("outdoor"),
                       "generators": [{"id":k,"name":g["name"],"kind":g["kind"],
                           "control_entity":g.get("control_entity"),"state_entity":g.get("state_entity") or g.get("control_entity"),"temperature_entity":g.get("temperature_entity")}
                           for k,g in resolved.items()],
                       "zones":zone_view(areas,data.get("zones",{}),data.get("outdoor"))})
    await panel_custom.async_register_panel(hass, frontend_url_path=PATH,
        webcomponent_name="smart-heating-panel",module_url=JS+"?v=0.3.19",
        sidebar_title="Smart Heating",sidebar_icon="mdi:home-thermometer",
        config={"installations":config},require_admin=False)
    state["owned"] = True

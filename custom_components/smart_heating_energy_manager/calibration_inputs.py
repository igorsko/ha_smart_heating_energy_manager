"""Resolve calibration inputs independently of dispatch ratings.

Never infer missing heat input as zero. Preserve configured meter mappings.
"""
from .model import finite
from .onboarding import ready
from .discovery import suggest, winnet_siblings

def calibration_inputs(devices, entries, read):
    entries=list(entries)
    result={}
    report={}
    for key, original in devices.items():
        g=dict(original)
        control=next((e for e in entries if e.entity_id==g.get("control_entity")),None)
        siblings=[e for e in entries if control and control.device_id and e.device_id==control.device_id and e.platform==control.platform and not e.disabled_by]
        # Onecta can register ClimateControl sensors on another device record.
        # Require the exact appliance prefix and same integration config entry.
        if control and control.platform in ("daikin_onecta","daikin") and control.entity_id.startswith("climate.") and control.entity_id.endswith("_room_temperature"):
            prefix=control.entity_id.split(".",1)[1].removesuffix("_room_temperature")+"_climatecontrol_"
            config_id=getattr(control,"config_entry_id",None)
            if config_id:
                siblings=list({e.entity_id:e for e in siblings+[
                    e for e in entries if e.platform==control.platform
                    and getattr(e,"config_entry_id",None)==config_id and not e.disabled_by
                    and (e.entity_id.split(".",1)[0] in ("sensor","binary_sensor") and e.entity_id.split(".",1)[1].startswith(prefix.removesuffix("climatecontrol_")))]}.values())
        def unique(suffixes, units, classes=()):
            matches=[]
            for e in siblings:
                if not e.entity_id.startswith(("sensor.","binary_sensor.")):
                    continue
                if not (e.entity_id.endswith(suffixes) or str(getattr(e,"unique_id","")).endswith(suffixes)):
                    continue
                s=read(e.entity_id)
                if s and s.attributes.get("unit_of_measurement") in units and (not classes or s.attributes.get("state_class") in classes):
                    matches.append(e.entity_id)
            return matches[0] if len(matches)==1 else None
        stove=winnet_siblings(entries,g) if g.get("kind")=="fuel" else []
        if stove:
            siblings=stove
            mapping=suggest(entries,stove[0].device_id)
            mass=unique(("_estimated_pellet_consumed","_pellet_pellet_used"),("kg",),("total","total_increasing"))
            if not g.get("fuel_mass_entity") and mass:
                g.update(fuel_mass_entity=mass,fuel_mass_unit="kg",fuel_mass_estimated=True)
            for field in ("state_entity","fuel_rate_entity","level_entity"):
                if not g.get(field) and mapping.get(field):
                    g[field]=mapping[field]
            if not g.get("state_entity"):
                burning=unique(("_stove_burning","_burning"),(None,))
                if burning:
                    g["state_entity"]=burning
            if g.get("state_entity") and (g["state_entity"]==mapping.get("state_entity") or g["state_entity"].endswith(("_stove_burning","_burning"))):
                if not g.get("active_states"):
                    g["active_states"]="on"
                if not g.get("inactive_states"):
                    g["inactive_states"]="off"
            if not g.get("fuel_rate_entity"):
                rate=unique(("_effective_pellet_consumption","_insights_effective_rate"),("kg/h",))
                if rate:
                    g["fuel_rate_entity"]=rate
            if not ready(original) and g.get("fuel_mass_unit","kg")=="kg":
                if not finite(g.get("fuel_energy_kwh")) or g["fuel_energy_kwh"]<=1:
                    g["fuel_energy_kwh"]=4.8
                if not finite(g.get("efficiency")) or not 0<g["efficiency"]<1:
                    g["efficiency"]=.9
        elif g.get("kind") in ("heat_pump","resistance"):
            if not g.get("energy_entity"):
                # Heating-only energy counters; prefer longest period, never sum
                # overlapping counters or use cooling/combined consumption.
                for period in ("yearly","annual","monthly","weekly","daily"):
                    candidate=unique(tuple("_"+x for x in (
                        "heating_"+period+"_electrical_consumption","heating_energy_"+period,period+"_heating_energy",
                        "heating_energy_consumption_"+period,period+"_heating_energy_consumption",
                        "heating_"+period+"_energy_consumption","energy_consumption_heating_"+period,
                        "energy_consumption_"+period+"_heating","heating_energy_"+period+"_consumption","heating_energy_consumption_"+period+"_total")),("Wh","kWh","MWh"),("total","total_increasing"))
                    if candidate:
                        g["energy_entity"]=candidate
                        break
            if not g.get("energy_entity") and g["kind"]=="heat_pump":
                # Localized entity names and integration translation keys.
                import re
                for period in (("yearly","annual","annuale","anno"),("monthly","mensile","mese"),("weekly","settimanale","settimana"),("daily","giornaliero","giorno")):
                    matches=[]
                    for e in siblings:
                        s=read(e.entity_id)
                        if not s or not e.entity_id.startswith("sensor.") or s.attributes.get("unit_of_measurement") not in ("Wh","kWh","MWh"):
                            continue
                        if s.attributes.get("state_class") not in ("total","total_increasing"):
                            continue
                        name=" ".join(str(x or "").lower() for x in (e.entity_id,getattr(e,"translation_key",None),getattr(e,"unique_id",None),s.attributes.get("friendly_name")))
                        words=set(re.split(r"[^a-z0-9]+",name))
                        if words.intersection(("heating","riscaldamento")) and words.intersection(period) and not words.intersection(("cooling","raffrescamento")):
                            matches.append(e.entity_id)
                    if len(matches)==1:
                        g["energy_entity"]=matches[0]
                        break
            if g["kind"]=="heat_pump" and not g.get("energy_entity") and control and control.platform in ("daikin_onecta","daikin"):
                for period in ("yearly","annual","monthly","weekly","daily"):
                    candidate=unique(("_heating_"+period+"_electrical_consumption","_heating_energy_consumption_"+period),("Wh","kWh","MWh"),("measurement",None))
                    if candidate:
                        g["energy_entity"]=candidate
                        break
            if g["kind"]=="heat_pump" and not original.get("energy_entity") and control and control.platform in ("daikin_onecta","daikin"):
                alternatives=[]
                for period in ("yearly","annual","monthly","weekly","daily"):
                    candidate=unique(("_heating_"+period+"_electrical_consumption","_heating_energy_consumption_"+period),("Wh","kWh","MWh"),("total","total_increasing","measurement",None))
                    if candidate and candidate!=g.get("energy_entity"):
                        alternatives.append(candidate)
                g["energy_alternatives"]=alternatives
            if g["kind"]=="heat_pump" and not g.get("state_entity"):
                # Only explicit compressor/heating activity signals, not operation mode or power switch.
                candidate=unique(("_heating_active","_heating_running","_compressor_running","_compressor_active","_hvac_action"),(None,))
                if candidate:
                    g["state_entity"]=candidate
            if g["kind"]=="heat_pump":
                g["_operating_candidates"]=[{"entity":e.entity_id,"state":str(s.state),"unit":s.attributes.get("unit_of_measurement")} for e in siblings if e.entity_id.startswith(("sensor.","binary_sensor.")) and (s:=read(e.entity_id)) and (s.attributes.get("unit_of_measurement") in ("W","kW","Wh","kWh") or any(t in e.entity_id.lower() for t in ("operation","compressor","heating","defrost","hvac_action","power")))]
            if g["kind"]=="heat_pump" and not g.get("power_entity"):
                # Require explicit electrical input semantics, never thermal output.
                candidate=unique(("_electrical_power","_electrical_input_power","_power_consumption","_input_power","_active_power","_power_absorption"),("W","kW","MW"))
                if candidate:
                    g["power_entity"]=candidate
            if g["kind"]=="heat_pump" and control and control.platform not in ("daikin_onecta","daikin"):
                from .onboarding import suggest_sensors
                electrical=[e for e in siblings if not any(t in e.entity_id.lower() for t in ("thermal","heat_output","heating_capacity","cooling","produced"))]
                for field,value in suggest_sensors(electrical,read,"heat_pump").items():
                    if not g.get(field):
                        g[field]=value
            if g["kind"]=="resistance":
                from .onboarding import suggest_sensors
                for field,value in suggest_sensors(siblings,read,"resistance").items():
                    if not g.get(field):
                        g[field]=value
            if not ready(original):
                g["efficiency"]=3.0 if g["kind"]=="heat_pump" else 1.0
        # A resistance heater may be calibrated from confirmed runtime and
        # a user-supplied electrical rating; never assume a nominal wattage.
        if g.get("kind")=="resistance" and control and control.platform=="olimpia_vertigo" and control.entity_id.startswith("switch.") and control.entity_id.endswith(("_riscaldamento","_heating")):
            if not g.get("state_entity"):
                g["state_entity"]=control.entity_id
            if g["state_entity"]==control.entity_id:
                g["active_states"]=g.get("active_states") or "on"
                g["inactive_states"]=g.get("inactive_states") or "off"
        # Vertigo heating enable is a thermostat request, not confirmed element runtime.
        # Never infer heat from its control state alone.
        vertigo_request=bool(control and control.platform=="olimpia_vertigo" and g.get("state_entity")==control.entity_id)
        if vertigo_request:
            g.pop("manual_input_rate",None)
        if control and control.entity_id.startswith("climate.") and g.get("kind") in ("heat_pump","resistance"):
            g["off_only_entity"]=control.entity_id
        elif vertigo_request and control.entity_id.startswith("switch.") and control.entity_id.endswith(("_riscaldamento","_heating")):
            g["off_only_entity"]=control.entity_id
        runtime=bool(g.get("state_entity") and finite(g.get("manual_input_rate")) and g["manual_input_rate"]>0 and g.get("active_states") and g.get("inactive_states"))
        meter=bool(g.get("energy_entity") or g.get("power_entity"))
        if g.get("kind")=="fuel":
            heat_parameters=finite(g.get("fuel_energy_kwh")) and g["fuel_energy_kwh"]>0 and finite(g.get("efficiency")) and 0<g["efficiency"]<=1
            source=bool(g.get("fuel_mass_entity") or (g.get("fuel_rate_entity") and g.get("state_entity") and g.get("active_states") and g.get("inactive_states")) or (meter and g.get("energy_is_useful_heat")))
            usable=bool(heat_parameters and source)
        else:
            usable=meter or (g.get("kind")=="resistance" and runtime)
        # Complete manual configurations retain their existing runtime fallback.
        if ready(original) and not vertigo_request:
            usable=True
        report[key]={"usable":usable,"provisional":not ready(original),"reason":None if usable else "missing_meter_or_confirmed_runtime" if g.get("kind")=="resistance" else "missing_energy_source","candidates":[{"entity":e.entity_id,"unit":s.attributes.get("unit_of_measurement"),"state_class":s.attributes.get("state_class")} for e in siblings if e.entity_id.startswith("sensor.") and (s:=read(e.entity_id)) and s.attributes.get("unit_of_measurement") in ("Wh","kWh","MWh","W","kW","MW")],"entities":{k:g[k] for k in ("energy_entity","power_entity","fuel_mass_entity","fuel_rate_entity","state_entity","off_only_entity") if g.get(k)}}
        result[key]=g
    return result,report

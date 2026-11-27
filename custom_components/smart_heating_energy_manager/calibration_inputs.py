"""Resolve calibration inputs independently of dispatch ratings.

Never infer missing heat input as zero. Preserve configured meter mappings.
"""
from .model import finite
from .onboarding import ready
from .discovery import suggest

def calibration_inputs(devices, entries, read):
    entries=list(entries)
    result={}
    report={}
    for key, original in devices.items():
        g=dict(original)
        control=next((e for e in entries if e.entity_id==g.get("control_entity")),None)
        siblings=[e for e in entries if control and control.device_id and e.device_id==control.device_id and e.platform==control.platform and not e.disabled_by]
        def unique(suffixes, units, classes=()):
            matches=[]
            for e in siblings:
                if not e.entity_id.startswith(("sensor.","binary_sensor.")):
                    continue
                if not (e.entity_id.endswith(suffixes) or e.unique_id.endswith(suffixes)):
                    continue
                s=read(e.entity_id)
                if s and s.attributes.get("unit_of_measurement") in units and (not classes or s.attributes.get("state_class") in classes):
                    matches.append(e.entity_id)
            return matches[0] if len(matches)==1 else None
        if g.get("kind")=="fuel" and control and control.platform=="winnet_stove":
            mapping=suggest(entries,control.device_id) if control.device_id else {}
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
            if g.get("state_entity") and g["state_entity"]==mapping.get("state_entity") or g.get("state_entity","").endswith(("_stove_burning","_burning")):
                g.setdefault("active_states","on")
                g.setdefault("inactive_states","off")
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
                        "heating_energy_"+period,period+"_heating_energy",
                        "heating_energy_consumption_"+period,period+"_heating_energy_consumption",
                        "heating_"+period+"_energy_consumption","energy_consumption_heating_"+period,
                        "energy_consumption_"+period+"_heating")),("Wh","kWh","MWh"),("total","total_increasing"))
                    if candidate:
                        g["energy_entity"]=candidate
                        break
            if not ready(original):
                g["efficiency"]=3.0 if g["kind"]=="heat_pump" else 1.0
        meter=bool(g.get("energy_entity") or g.get("power_entity"))
        if g.get("kind")=="fuel":
            heat_parameters=finite(g.get("fuel_energy_kwh")) and g["fuel_energy_kwh"]>0 and finite(g.get("efficiency")) and 0<g["efficiency"]<=1
            source=bool(g.get("fuel_mass_entity") or (g.get("fuel_rate_entity") and g.get("state_entity") and g.get("active_states") and g.get("inactive_states")) or (meter and g.get("energy_is_useful_heat")))
            usable=bool(heat_parameters and source)
        else:
            usable=meter
        # Complete manual configurations retain their existing runtime fallback.
        if ready(original):
            usable=True
        report[key]={"usable":usable,"provisional":not ready(original),"entities":{k:g[k] for k in ("energy_entity","power_entity","fuel_mass_entity","fuel_rate_entity","state_entity") if g.get(k)}}
        result[key]=g
    return result,report

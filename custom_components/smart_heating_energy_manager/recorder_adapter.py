"""Read-only Recorder adapter with explicit measured/manual source selection."""
from dataclasses import asdict
from datetime import timedelta
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util import dt as dt_util
from .calibration import fit, validate_holdout
from .history_input import Sample, Series, MeanSeries, RateSeries, ConfirmedOffSeries, AlternativeSeries, build_intervals
from .model import finite
from .fuel import parse_rates, fuel_rate_series, mass_to_units

def convert(value, unit, kind):
    n = finite(value)
    if n is None:
        return None
    if kind == "temperature":
        return n if unit == "°C" else (n-32)*5/9 if unit == "°F" else None
    factors = {"Wh": .001, "kWh": 1, "MWh": 1000} if kind == "energy" else {"W": .001,"kW":1,"MW":1000}
    return n*factors[unit] if unit in factors and n >= 0 else None

def _series(states, kind, multiplier=1):
    samples = []
    for state in states:
        value = convert(state.state, state.attributes.get("unit_of_measurement"), kind)
        samples.append(Sample(state.last_updated.timestamp(), None if value is None else value*multiplier))
    return (RateSeries if kind == "power" else Series)(samples)

def _runtime(states, g):
    rate = g.get("manual_input_rate",0)
    if g["kind"] == "fuel":
        rate *= g["fuel_energy_kwh"] * g["efficiency"]
    elif g["kind"] == "resistance":
        rate *= g["efficiency"]
    active = {s.strip() for s in g.get("active_states","").split(",") if s.strip()}
    inactive = {s.strip() for s in g.get("inactive_states","").split(",") if s.strip()}
    if not rate > 0 or not active or not inactive or active & inactive:
        return None
    return RateSeries([Sample(s.last_updated.timestamp(), rate if s.state in active else 0. if s.state in inactive else None) for s in states])

def _coverage(series,start,end,step,age):
    valid=total=0
    while start+step<=end:
        total+=1
        if series.counter_delta(start,start+step,age) is not None:
            valid+=1
        start+=step
    return valid/total if total else 0

async def async_calibrate(hass, config):
    indoor_ids=config.get("indoor_reference") or ([config["indoor"]] if config.get("indoor") else [])
    outdoor_id=config.get("outdoor_reference") or config.get("outdoor")
    if not indoor_ids or not outdoor_id:
        return {"status":"configure_temperature_sensors"}
    from homeassistant.helpers import entity_registry as er
    from .calibration_inputs import calibration_inputs
    resolved,input_report=calibration_inputs(config.get("generators",{}),er.async_get(hass).entities.values(),hass.states.get)
    devices=list(resolved.items())
    if not devices:
        return {"status":"no_generators"}
    pending=[key for key,g in devices if not input_report[key]["usable"]]
    temp_ids=set(indoor_ids+[outdoor_id])
    ids=list(dict.fromkeys(indoor_ids+[outdoor_id]+[g[k] for _,g in devices for k in ("energy_entity","power_entity","state_entity","fuel_mass_entity","level_entity","fuel_rate_entity","off_only_entity") if g.get(k)]))
    ids=list(dict.fromkeys(ids+[e for _,g in devices for e in g.get("energy_alternatives",[])]))
    end=dt_util.utcnow()
    start=end-timedelta(days=config.get("history_days",7))
    age=config.get("history_max_age_hours",2)*3600
    step=config.get("history_interval_minutes",60)*60
    # Coverage is diagnostic; the fit requires complete joint intervals.
    def calculate():
        states=get_significant_states(hass,start-timedelta(seconds=age),end,entity_ids=ids,
            include_start_time_state=True,significant_changes_only=False,minimal_response=False,no_attributes=False)
        indoor=MeanSeries([_series(states.get(e,[]),"temperature") for e in indoor_ids])
        outdoor=_series(states.get(outdoor_id,[]),"temperature")
        from .history_quality import temperature_coverage
        quality={"temperature":{e:temperature_coverage(_series(states.get(e,[]),"temperature"),start.timestamp(),end.timestamp(),step,age) for e in indoor_ids+[outdoor_id]},
                 "expected_intervals":int((end-start).total_seconds()//step)}
        counters,diagnostics,used=[],{},set()
        for key,g in devices:
            choices=[]
            factor=g.get("efficiency",1) if g["kind"]=="resistance" else 1
            if g["kind"]!="fuel" or g.get("energy_is_useful_heat",False):
                for field,kind in (("energy_entity","energy"),("power_entity","power")):
                    entity=g.get(field)
                    if entity:
                        choices.append((field,entity,_series(states.get(entity,[]),kind,factor)))
            for entity in g.get("energy_alternatives",[]):
                choices.append(("energy_entity",entity,_series(states.get(entity,[]),"energy",factor)))
            if g["kind"]=="fuel":
                entity=g.get("fuel_mass_entity")
                if entity:
                    factor=g["fuel_energy_kwh"]*g["efficiency"]
                    samples=[]
                    for s in states.get(entity,[]):
                        value=mass_to_units(finite(s.state),s.attributes.get("unit_of_measurement"),g.get("fuel_mass_unit","kg"))
                        samples.append(Sample(s.last_updated.timestamp(),None if value is None else value*factor))
                    choices.insert(0,("fuel_mass_estimated" if g.get("fuel_mass_estimated",False) else "fuel_mass",entity,Series(samples)))
            entity=g.get("state_entity")
            if entity:
                level=g.get("level_entity")
                rates=parse_rates(g.get("level_rates",""))
                active={s.strip() for s in g.get("active_states","").split(",") if s.strip()}
                inactive={s.strip() for s in g.get("inactive_states","").split(",") if s.strip()}
                if g["kind"]=="fuel" and level and rates and active and inactive and not active & inactive and level != entity:
                    raw=lambda e:[Sample(s.last_updated.timestamp(),s.state) for s in states.get(e,[])]
                    choices.append(("level_runtime",entity,fuel_rate_series(raw(entity),raw(level),rates,active,inactive,g["fuel_energy_kwh"]*g["efficiency"],age)))
                rate_entity=g.get("fuel_rate_entity")
                if g["kind"]=="fuel" and rate_entity and rate_entity != entity and active and inactive and not active & inactive:
                    from .fuel import recorded_rate_series
                    choices.append(("recorded_fuel_rate",entity,recorded_rate_series(
                        states.get(entity,[]),states.get(rate_entity,[]),active,inactive,
                        g.get("fuel_mass_unit","kg"),g["fuel_energy_kwh"]*g["efficiency"],age)))
                manual=_runtime(states.get(entity,[]),g)
                if manual and not g.get('level_rates','').strip():
                    choices.append(("manual_runtime",entity,manual))
            priority={"fuel_mass":0,"energy_entity":1,"power_entity":2,"fuel_mass_estimated":3,"recorded_fuel_rate":4,"level_runtime":5,"manual_runtime":6}
            choices.sort(key=lambda item:priority[item[0]])
            report={}
            selected=[]
            for method,entity,series in choices:
                coverage=_coverage(series,start.timestamp(),end.timestamp(),step,age)
                report[method+":"+entity]=round(coverage,3)
                if coverage>0 and entity not in used and entity not in temp_ids:
                    selected.append((method,entity,series))
            diagnostics[key]={"coverage":report,"source":None,"entity":None}
            if g.get("off_only_entity"):
                off=g["off_only_entity"]
                # Unknown or enabled states invalidate the interval, not zero heat.
                observations=[Sample(s.last_updated.timestamp(),0. if s.state=="off" else None) for s in states.get(off,[])]
                # Do not bridge a Recorder outage merely because the live state is OFF.
                # Live state is not independent historical evidence.
                series=ConfirmedOffSeries(observations)
                coverage=_coverage(series,start.timestamp(),end.timestamp(),step,age)
                if coverage>0 and off not in used and off not in temp_ids:
                    selected.append(("confirmed_off_only",off,series))
                    diagnostics[key]["coverage"]["confirmed_off_only"]=round(coverage,3)
            if selected:
                used.update(item[1] for item in selected)
                combined=AlternativeSeries(item[2] for item in selected)
                diagnostics[key].update(source=selected[0][0] if len(selected)==1 else "interval_fallback",entity=", ".join(dict.fromkeys(item[1] for item in selected)))
                diagnostics[key]["coverage"]["combined"] = round(_coverage(combined,start.timestamp(),end.timestamp(),step,age),3)
                counters.append((g["kind"],combined))
        if len(counters)!=len(devices):
            quality.update(complete_intervals=0,complete_fraction=0)
            return {"status":"configure_missing_energy_source","generators":diagnostics,"inputs":input_report,"quality":quality}
        intervals=build_intervals(indoor,outdoor,counters,start.timestamp(),end.timestamp(),step,age)
        quality["complete_intervals"]=len(intervals)
        quality["complete_fraction"]=len(intervals)/quality["expected_intervals"] if quality["expected_intervals"] else 0
        known_cop=None
        result=fit(intervals)
        if result is None:
            hp=[g for _,g in devices if g["kind"]=="heat_pump"]
            cops={g["efficiency"] for g in hp if not g.get("cop_curve")}
            if hp and len(cops)==1 and all(not g.get("cop_curve") for g in hp):
                known_cop=next(iter(cops))
                result=fit(intervals,known_cop=known_cop)
        return {"status":"estimated" if result else "insufficient_or_unidentifiable","generators":diagnostics,"inputs":input_report,"quality":quality,
                "indoor_reference":indoor_ids,"outdoor_reference":outdoor_id,"intervals":len(intervals),"validation":validate_holdout(intervals,known_cop=known_cop),"fit":asdict(result) if result else None,"calculated_at":end.isoformat()}
    return await get_instance(hass).async_add_executor_job(calculate)


async def recent_heat_pump_power(hass, devices, now):
    """Read a bounded history once for all missing instantaneous meters."""
    from .history_input import recent_counter_power
    meters={k:list(dict.fromkeys([e for e in [g.get("energy_entity"),*g.get("energy_alternatives",[])] if e])) for k,g in devices.items() if g.get("kind")=="heat_pump"}
    ids=list(dict.fromkeys(e for values in meters.values() for e in values))
    if not ids or "recorder" not in hass.config.components:
        return {}
    def calculate():
        states=get_significant_states(hass,now-timedelta(hours=4),now,entity_ids=ids,
            include_start_time_state=False,significant_changes_only=False,minimal_response=False,no_attributes=False)
        result={}
        for key,entities in meters.items():
            for entity in entities:
                if sum(entity in v for v in meters.values())!=1:
                    continue
                series=_series(states.get(entity,[]),"energy")
                row=recent_counter_power(series.samples,now.timestamp())
                if row:
                    result[key]={**row,"power_entity":entity}
                    break
        return result
    return await get_instance(hass).async_add_executor_job(calculate)

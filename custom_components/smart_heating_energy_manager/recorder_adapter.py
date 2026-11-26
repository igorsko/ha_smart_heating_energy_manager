"""Read-only Recorder adapter with explicit measured/manual source selection."""
from dataclasses import asdict
from datetime import timedelta
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util import dt as dt_util
from .calibration import fit
from .history_input import Sample, Series, RateSeries, build_intervals
from .model import finite

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
    devices=list(config.get("generators",{}).items())
    if not devices:
        return {"status":"no_generators"}
    ids=list(dict.fromkeys([config["indoor"],config["outdoor"]]+[g[k] for _,g in devices for k in ("energy_entity","power_entity","state_entity") if g.get(k)]))
    end=dt_util.utcnow()
    start=end-timedelta(days=config.get("history_days",7))
    age=config.get("history_max_age_hours",2)*3600
    step=config.get("history_interval_minutes",60)*60
    threshold=config.get("history_min_coverage",.7)
    def calculate():
        states=get_significant_states(hass,start-timedelta(seconds=age),end,entity_ids=ids,
            include_start_time_state=False,significant_changes_only=False,minimal_response=False,no_attributes=False)
        indoor=_series(states.get(ids[0],[]),"temperature")
        outdoor=_series(states.get(ids[1],[]),"temperature")
        counters,diagnostics,used=[],{},set()
        for key,g in devices:
            choices=[]
            factor=g["efficiency"] if g["kind"]=="resistance" else 1
            if g["kind"]!="fuel" or g.get("energy_is_useful_heat",False):
                for field,kind in (("energy_entity","energy"),("power_entity","power")):
                    entity=g.get(field)
                    if entity:
                        choices.append((field,entity,_series(states.get(entity,[]),kind,factor)))
            entity=g.get("state_entity")
            if entity:
                manual=_runtime(states.get(entity,[]),g)
                if manual:
                    choices.append(("manual_runtime",entity,manual))
            report={}
            selected=None
            for method,entity,series in choices:
                coverage=_coverage(series,start.timestamp(),end.timestamp(),step,age)
                report[method]=round(coverage,3)
                if coverage>=threshold and entity not in used and entity not in ids[:2] and selected is None:
                    selected=(method,entity,series)
            diagnostics[key]={"coverage":report,"source":selected[0] if selected else None}
            if selected:
                used.add(selected[1])
                counters.append((g["kind"],selected[2]))
        if len(counters)!=len(devices):
            return {"status":"configure_missing_energy_source","generators":diagnostics}
        intervals=build_intervals(indoor,outdoor,counters,start.timestamp(),end.timestamp(),step,age)
        result=fit(intervals)
        return {"status":"estimated" if result else "insufficient_or_unidentifiable","generators":diagnostics,
                "intervals":len(intervals),"fit":asdict(result) if result else None,"calculated_at":end.isoformat()}
    return await get_instance(hass).async_add_executor_job(calculate)

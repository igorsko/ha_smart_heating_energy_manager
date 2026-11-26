"""Fuel measurement helpers. Rates are in configured fuel units per hour."""
import math
from .history_input import Sample, RateSeries

def parse_rates(text):
    """Parse explicit state=rate pairs, rejecting ambiguous or invalid input."""
    rates={}
    for item in text.splitlines():
        if not item.strip():
            continue
        state, sep, raw=item.partition("=")
        state=state.strip()
        if not sep or not state or state in rates or state in ("unknown","unavailable"):
            raise ValueError("Invalid or duplicate operating state")
        rate=float(raw)
        if not math.isfinite(rate) or rate<0:
            raise ValueError("Invalid fuel rate")
        rates[state]=rate
    return rates

def fuel_rate_series(states, levels, rates, active, inactive, factor, max_age):
    """Join operating state and level histories without assuming missing levels."""
    from .history_input import Series
    state_series=sorted(states,key=lambda x:x.timestamp)
    level_series=sorted(levels,key=lambda x:x.timestamp)
    times=sorted({x.timestamp for x in state_series+level_series})
    i=j=-1
    result=[]
    for t in times:
        while i+1<len(state_series) and state_series[i+1].timestamp<=t:
            i+=1
        while j+1<len(level_series) and level_series[j+1].timestamp<=t:
            j+=1
        state=state_series[i].value if i>=0 and t-state_series[i].timestamp<=max_age else None
        level=level_series[j].value if j>=0 and t-level_series[j].timestamp<=max_age else None
        value=0. if state in inactive else rates[level]*factor if state in active and level in rates else None
        result.append(Sample(t,value))
    return RateSeries(result)

def mass_to_units(value, unit, configured_unit):
    """Convert mass to the user's explicit fuel unit; no volume conversion."""
    factors={"g":.001,"kg":1.,"t":1000.,"lb":.45359237}
    if value is None or not math.isfinite(value) or value<0 or unit not in factors or configured_unit not in factors:
        return None
    return value*factors[unit]/factors[configured_unit]


def recorded_rate_series(states, rate_states, active, inactive, unit, factor, max_age):
    """Gate reported consumption rates by actual combustion, never by setpoint."""
    from .history_input import Series
    from .model import finite
    ordered=sorted(states,key=lambda s:s.last_updated)
    rates=Series([Sample(s.last_updated.timestamp(),
        mass_to_units(finite(s.state),s.attributes.get("unit_of_measurement","").removesuffix("/h"),unit)
        if s.attributes.get("unit_of_measurement","").endswith("/h") else None)
        for s in rate_states])
    times=sorted({s.last_updated.timestamp() for s in ordered}|set(rates.times))
    i=-1
    samples=[]
    for t in times:
        while i+1<len(ordered) and ordered[i+1].last_updated.timestamp()<=t:
            i+=1
        state=ordered[i].state if i>=0 and t-ordered[i].last_updated.timestamp()<=max_age else None
        rate=rates.value_at(t,max_age)
        value=0. if state in inactive else rate*factor if state in active and rate is not None and rate>0 else None
        samples.append(Sample(t,value))
    return RateSeries(samples)

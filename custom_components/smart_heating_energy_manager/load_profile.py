"""Learn hourly base-load profile from explicitly mapped power measurements."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from .history_input import Sample, Series
from .prediction import kw

def profile(home,loads,start,end,tz,max_age=900,min_days=3):
    """Subtract measured heating/DHW only; reject missing and negative balance."""
    buckets=defaultdict(list)
    while start+timedelta(hours=1)<=end:
        stop=start+timedelta(hours=1)
        a,b=start.timestamp(),stop.timestamp()
        values=[s.average(a,b,max_age) for s in (home,*loads)]
        if all(v is not None and v>=0 for v in values):
            base=values[0]-sum(values[1:])
            if base>=0:
                buckets[start.astimezone(tz).hour].append(base)
        start=stop
    return {str(h):{"kw":round(median(v),3),"samples":len(v)} for h,v in buckets.items() if len(v)>=min_days}

async def async_profile(hass,config):
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import get_significant_states
    from homeassistant.util import dt as dt_util
    home=config.get("base_home_power")
    loads=config.get("base_excluded_power",[])
    if not home or home in loads or len(set(loads))!=len(loads):
        return {}
    end=dt_util.utcnow().replace(minute=0,second=0,microsecond=0)
    start=end-timedelta(days=7)
    tz=dt_util.get_time_zone(hass.config.time_zone) or timezone.utc
    ids=[home,*loads]
    def calculate():
        states=get_significant_states(hass,start-timedelta(minutes=15),end,entity_ids=ids,include_start_time_state=False,significant_changes_only=False,minimal_response=False,no_attributes=False)
        series=[Series([Sample(s.last_updated.timestamp(),kw(s.state,s.attributes.get("unit_of_measurement"))) for s in states.get(e,[])]) for e in ids]
        return profile(series[0],series[1:],start,end,tz)
    return await get_instance(hass).async_add_executor_job(calculate)

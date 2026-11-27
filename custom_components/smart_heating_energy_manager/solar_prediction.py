"""Import hourly solar forecasts through the Energy integration's providers."""
from datetime import datetime, timezone
from .prediction import number

def hourly(forecasts):
    """Aggregate only complete provider hours; deduplicate IDs upstream."""
    if not forecasts:
        return {}
    series=[]
    for forecast in forecasts:
        parsed={}
        for stamp,value in (forecast.get("wh_hours") or {}).items():
            try:
                t=datetime.fromisoformat(stamp)
                if t.tzinfo is None or t.minute or t.second or t.microsecond:
                    continue
                n=number(value)
                if n is not None and n>=0:
                    parsed[t.astimezone(timezone.utc).isoformat()]=n/1000
            except (ValueError,TypeError):
                continue
        series.append(parsed)
    common=set.intersection(*(set(s) for s in series))
    return {k:sum(s[k] for s in series) for k in sorted(common)}

async def async_solar(hass,sources):
    ids={i for s in sources.get("solar",[]) for i in (s.get("config_entry_solar_forecast") or [])}
    if not ids:
        return {}
    from homeassistant.components.energy.websocket_api import async_get_energy_platforms
    platforms=await async_get_energy_platforms(hass)
    forecasts=[]
    for identifier in sorted(ids):
        entry=hass.config_entries.async_get_entry(identifier)
        if entry is None or entry.domain not in platforms:
            return {}
        forecast=await platforms[entry.domain](hass,identifier)
        if not forecast:
            return {}
        forecasts.append(forecast)
    return hourly(forecasts)

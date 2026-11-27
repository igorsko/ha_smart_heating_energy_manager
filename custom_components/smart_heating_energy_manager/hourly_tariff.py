"""Conservative adapter for timestamped price forecasts from HA sensors."""
from datetime import datetime, timezone, timedelta
from collections.abc import Mapping
from .tariff_discovery import index_value
from .model import electricity_price

def hour_stamp(value):
    try:
        stamp=datetime.fromisoformat(value)
    except (ValueError,TypeError):
        return None
    if stamp.tzinfo is None or stamp.minute or stamp.second or stamp.microsecond:
        return None
    return stamp.astimezone(timezone.utc).isoformat()

def parse_prices(attrs):
    """Only explicit hourly timestamps and currency/energy units are accepted.

    Supports timestamp maps and lists containing start/datetime/time and
    price/value. No positional today/tomorrow arrays: DST is ambiguous.
    Conflicting duplicate intervals are excluded.
    """
    prices={}
    conflicts=set()
    default_unit=attrs.get("unit_of_measurement")
    for key in ("prices","forecast","hourly_prices","raw_today","raw_tomorrow"):
        data=attrs.get(key)
        if isinstance(data,Mapping):
            items=[{"start":k,"price":v} for k,v in data.items()]
        elif isinstance(data,list):
            items=data
        else:
            continue
        for item in items:
            if not isinstance(item,Mapping):
                continue
            stamp=hour_stamp(item.get("start") or item.get("datetime") or item.get("time"))
            if stamp is None:
                continue
            if item.get("end") is not None:
                end=hour_stamp(item["end"])
                if end is None or datetime.fromisoformat(end)-datetime.fromisoformat(stamp)!=timedelta(hours=1):
                    continue
            price=index_value(item.get("price",item.get("value")),item.get("unit",default_unit))
            if price is None:
                continue
            if stamp in prices and abs(prices[stamp]-price)>1e-9:
                conflicts.add(stamp)
            prices[stamp]=price
    return {k:v for k,v in prices.items() if k not in conflicts}

def marginal_forecast(attrs,config):
    if not config.get("use_index"):
        return {}
    return {t:electricity_price(v,"EUR/kWh",None,config.get("spread",0),config.get("losses",0),config.get("variable",0),config.get("tax",0),config.get("vat",0))[0] for t,v in parse_prices(attrs).items()}

def price_at(stamp,forecast,current,current_source):
    key=hour_stamp(stamp)
    if key in forecast:
        return forecast[key],"hourly_index"
    return current,"fixed" if current_source=="fixed" else "current_index_assumed" if current is not None else "unavailable"

"""Read-only domestic hot water advice; never alter appliance controls."""
from datetime import datetime, timedelta
from .prediction import number, kw

def thermal_energy(litres,current,target):
    l,c,t=map(number,(litres,current,target))
    if l is None or l<=0 or c is None or t is None or not 0<=c<=100 or not 0<=t<=100:
        return None
    return round(l*max(0,t-c)*4.186/3600,3)

def snapshot(config,read):
    if not config.get("entity"):
        return {}
    device=read(config["entity"])
    sensor=read(config["temperature"]) if config.get("temperature") else None
    attrs=device.attributes if device else {}
    value=number(sensor.state if sensor else attrs.get("current_temperature"))
    unit=sensor.attributes.get("unit_of_measurement") if sensor else attrs.get("temperature_unit")
    temp=value if unit=="°C" else (value-32)*5/9 if value is not None and unit=="°F" else None
    if temp is not None and not 0<=temp<=100:
        temp=None
    power=read(config["power"]) if config.get("power") else None
    measured=kw(power.state,power.attributes.get("unit_of_measurement")) if power else None
    energy=read(config["energy"]) if config.get("energy") else None
    cumulative=number(energy.state) if energy else None
    factor={"Wh":.001,"kWh":1,"MWh":1000}.get(energy.attributes.get("unit_of_measurement")) if energy else None
    return {"entity":config["entity"],"state":device.state if device else "unavailable","temperature_c":temp,"power_kw":measured if measured is not None and measured>=0 else None,"energy_total_kwh":cumulative*factor if cumulative is not None and cumulative>=0 and factor else None,"litres":config.get("litres"),"rated_kw":config.get("rated_kw"),"target_c":config.get("target_c"),"minimum_c":config.get("minimum_c"),"below_minimum":temp<config["minimum_c"] if temp is not None and config.get("minimum_c") is not None else None,"ideal_heat_kwh":thermal_energy(config.get("litres"),temp,config.get("target_c"))}

def solar_window(hours,heat_kwh,rated_kw,now):
    """Rank complete future contiguous hourly windows by gross PV overlap."""
    heat,power=number(heat_kwh),number(rated_kw)
    if heat is None or heat<=0 or power is None or power<=0:
        return None
    import math
    count=math.ceil(heat/power)
    if count>24:
        return None
    points={}
    for row in hours:
        try:
            t=datetime.fromisoformat(row["datetime"])
            v=number(row.get("pv_kwh"))
            if t.tzinfo and t>=now and v is not None and v>=0:
                points[t]=v
        except (ValueError,TypeError,KeyError):
            continue
    candidates=[]
    for start in sorted(points):
        slots=[start+timedelta(hours=i) for i in range(count)]
        if not all(t in points for t in slots):
            continue
        overlap=sum(min(points[t],max(0,min(power,heat-i*power))) for i,t in enumerate(slots))
        candidates.append((overlap,start))
    if not candidates:
        return None
    overlap,start=max(candidates,key=lambda p:(p[0],-p[1].timestamp()))
    return {"start":start.isoformat(),"end":(start+timedelta(hours=heat/power)).isoformat(),"potential_pv_kwh":round(overlap,3),"assumption":"gross_pv_not_surplus"}

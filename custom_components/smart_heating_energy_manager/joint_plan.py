"""Hourly advisory energy balance, with explicit assumptions and no device control."""
from datetime import datetime, timedelta, timezone
from math import ceil
from .prediction import number

def _timestamp(value):
    try:
        t=datetime.fromisoformat(value)
        return t.astimezone(timezone.utc) if t.tzinfo and not (t.minute or t.second or t.microsecond) else None
    except (TypeError,ValueError):
        return None

def optimize(heating,solar,base_kw,price,dhw=None,battery=None,now=None,export_price=None):
    """Compare contiguous ACS windows for fixed space-heating dispatch.

    PV first serves load, then charges battery; deficits discharge battery then
    draw from grid. No grid charging, no control, no claim of global optimum.
    Hourly energy accounting does not establish instantaneous power feasibility.
    """
    base,price,export=map(number,(base_kw,price,export_price))
    if base is None or base<0 or price is None or price<0 or export is None or export<0:
        return {"status":"configure_assumptions"}
    pv={}
    for row in solar:
        t=_timestamp(row.get("datetime"))
        v=number(row.get("pv_kwh"))
        if t is not None and v is not None and v>=0:
            pv[t]=v
    rows=[]
    for row in heating:
        t=_timestamp(row.get("datetime"))
        h=number(row.get("heat_kw"))
        electric=number(row.get("electricity_kwh"))
        fuel=number(row.get("fuel_cost"))
        if t is None or (now is not None and t<now):
            continue
        if h is None or h<0 or (h>0 and not row.get("generator")):
            continue
        if electric is None or electric<0 or fuel is None or fuel<0 or t not in pv:
            continue
        rows.append((t,pv[t],electric,fuel,row.get("generator_name")))
    rows.sort()
    if not rows:
        return {"status":"missing_forecast"}
    if any(b[0]-a[0]!=timedelta(hours=1) for a,b in zip(rows,rows[1:])):
        return {"status":"incomplete_forecast"}
    battery=battery or {}
    cap,soc,reserve,charge,discharge,eff=map(number,(battery.get("capacity"),battery.get("soc"),battery.get("reserve"),battery.get("charge_kw"),battery.get("discharge_kw"),battery.get("efficiency")))
    use_battery=all(v is not None for v in (cap,soc,reserve,charge,discharge,eff)) and cap>0 and 0<=reserve<=soc<=100 and charge>0 and discharge>0 and 0<eff<=1
    if battery and not use_battery:
        return {"status":"configure_battery"}
    initial=cap*soc/100 if use_battery else 0
    floor=cap*reserve/100 if use_battery else 0
    dhw=dhw or {}
    heat=number(dhw.get("ideal_heat_kwh"))
    rated=number(dhw.get("rated_kw"))
    starts=[None]
    if dhw.get("entity"):
        if dhw.get("below_minimum") is not False or heat is None or heat<0 or rated is None or rated<=0:
            return {"status":"dhw_needs_attention"}
        if heat>0:
            count=ceil(heat/rated)
            if count>len(rows):
                return {"status":"insufficient_dhw_window"}
            starts=list(range(len(rows)-count+1))
    def simulate(start):
        stored=initial
        output=[]
        total=0.
        for i,(t,solar_energy,electric,fuel,name) in enumerate(rows):
            hot=0 if start is None or i<start else min(rated,max(0,heat-(i-start)*rated))
            load=base+electric+hot
            direct=min(solar_energy,load)
            surplus=solar_energy-direct
            deficit=load-direct
            into=min(surplus,charge,(cap-stored)/eff) if use_battery else 0
            stored+=into*eff if use_battery else 0
            out=min(deficit,discharge,max(0,stored-floor)*eff) if use_battery else 0
            stored-=out/eff if use_battery else 0
            grid=deficit-out
            exported=surplus-into
            cost=grid*price-exported*export+fuel
            total+=cost
            output.append({"datetime":t.isoformat(),"pv_kwh":round(solar_energy,3),"base_kwh":base,"heating_kwh":electric,"dhw_kwh":round(hot,3),"grid_kwh":round(grid,3),"export_kwh":round(exported,3),"battery_charge_kwh":round(into,3),"battery_discharge_kwh":round(out,3),"battery_soc":round(stored/cap*100,1) if use_battery else None,"cost":round(cost,4),"generator_name":name})
        # Value terminal stored energy at import price (recoverable AC energy).
        objective=total-(stored-initial)*eff*price if use_battery else total
        return objective,total,output
    best=min(((*simulate(start),start) for start in starts),key=lambda x:(x[0],x[3] if x[3] is not None else -1))
    return {"status":"estimated","rows":best[2],"net_cost":round(best[1],4),"objective":round(best[0],4),"dhw_start":rows[best[3]][0].isoformat() if best[3] is not None else None,"battery_mode":"solar_only" if use_battery else "none","assumptions":"constant_base_and_tariffs_fixed_heating_dispatch_hourly_balance"}

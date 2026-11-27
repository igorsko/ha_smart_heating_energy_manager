"""Exact hourly solution of a lumped first-order building thermal model."""
from math import exp, expm1
from datetime import datetime, timedelta
from .prediction import number

def step(indoor,outdoor,loss,capacity,heat=0,duration=1):
    h=loss/1000
    decay=exp(-h*duration/capacity)
    return outdoor+(indoor-outdoor)*decay+heat*(-expm1(-h*duration/capacity))/h

def required_heat(indoor,outdoor,loss,capacity,target,duration=1):
    free=step(indoor,outdoor,loss,capacity,0,duration)
    return max(0,(target-free)*(loss/1000)/(-expm1(-loss/1000*duration/capacity)))

def simulate(hours,indoor,loss,capacity,target,margin=0,now=None):
    """Compare maintain and solar preheat scenarios, excluding PV discounts.

    Each hour is a constant outdoor temperature and constant useful heat input.
    Preheat is only a bounded scenario, not an actuator schedule or net savings claim.
    """
    indoor,loss,capacity,target,margin=map(number,(indoor,loss,capacity,target,margin))
    if any(v is None for v in (indoor,loss,capacity,target,margin)) or loss<=0 or capacity<=0 or not 0<=margin<=3:
        return {"status":"configure_model"}
    entries=[]
    for row in hours:
        try:
            t=datetime.fromisoformat(row["datetime"])
        except (KeyError,ValueError,TypeError):
            continue
        if not t.tzinfo:
            continue
        if now and t+timedelta(hours=1)<=now:
            continue
        entries.append((t,row))
    entries.sort(key=lambda p:p[0])
    if not entries or any(b[0]-a[0]!=timedelta(hours=1) for a,b in zip(entries,entries[1:])):
        return {"status":"incomplete_weather"}
    if now and entries[0][0]>now:
        return {"status":"missing_current_weather"}
    def scenario(preheat):
        temp=indoor
        output=[]
        total=0.
        complete=True
        for stamp,row in entries[:24]:
            outside=number(row.get("temperature_c"))
            if outside is None:
                return [],None
            duration=min(1,(stamp+timedelta(hours=1)-now).total_seconds()/3600) if now else 1
            pv=number(row.get("pv_kwh"))
            aim=target+margin if preheat and pv is not None and pv>0 else target
            need=required_heat(temp,outside,loss,capacity,aim,duration)
            free=step(temp,outside,loss,capacity,0,duration)
            choices=[]
            for g in row.get("generators",[]):
                if not g.enabled:
                    continue
                cost=g.thermal_cost(row.get("price"))
                if cost is not None and need<=g.capacity_kw+1e-8:
                    choices.append((cost,g.identifier,g))
            chosen=min(choices,key=lambda x:(x[0],x[1])) if choices and need>1e-8 else None
            heat=need if chosen else 0.
            if need>1e-8 and chosen is None:
                complete=False
            end=step(temp,outside,loss,capacity,heat,duration)
            cost=chosen[0]*heat*duration if chosen else 0 if need<=1e-8 else None
            total+=cost or 0
            output.append({"datetime":stamp.isoformat(),"start_c":round(temp,3),"end_c":round(end,3),"unheated_end_c":round(free,3),"outdoor_c":outside,"target_c":aim,"heat_kwh":round(heat*duration,3),"generator":chosen[1] if chosen else None,"cost":round(cost,4) if cost is not None else None,"comfort_met":min(temp,end)>=target-0.05,"pv_kwh":pv,"duration_hours":round(duration,4)})
            temp=end
        return output,round(total,4) if complete else None
    baseline,cost=scenario(False)
    alternative,alt_cost=scenario(True) if margin>0 else ([],None)
    if not baseline:
        return {"status":"incomplete_weather"}
    return {"status":"estimated","baseline":baseline,"preheat":alternative,"baseline_gross_cost":cost,"preheat_gross_cost":alt_cost,"loss_w_k":loss,"capacity_kwh_k":capacity,"assumptions":"single_zone_no_solar_gains_no_pv_discount_constant_hourly_heat"}

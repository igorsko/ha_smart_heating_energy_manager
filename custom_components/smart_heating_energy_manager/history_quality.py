"""Coverage diagnostics; not a statistical confidence estimate."""
def temperature_coverage(series,start,end,step,age):
    if step<=0:
        return 0.0
    valid=total=0
    while start+step<=end:
        total+=1
        stop=start+step
        if all(v is not None for v in (series.value_at(start,age),series.value_at(stop,age),series.average(start,stop,age))):
            valid+=1
        start=stop
    return round(valid/total,3) if total else 0.0

def readiness(indoor_count,indoor_total,outdoor,loss,capacity,tariff):
    checks={"indoor":indoor_total>0 and indoor_count==indoor_total,
            "outdoor":outdoor is not None,"loss":loss is not None and loss>0,
            "capacity":capacity is not None and capacity>0,"tariff":tariff is not None}
    return {"checks":checks,"complete":sum(checks.values()),"total":len(checks)}

"""Validate and isolate persisted model estimates from manual configuration."""
from math import isfinite
import hashlib
import json

def fingerprint(config):
    fields={k:config.get(k) for k in ("indoor","outdoor","generators","indoor_reference","outdoor_reference")}
    return hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()

def accepted(result,config):
    fit=result.get("fit")
    if result.get("status")!="estimated" or not isinstance(fit,dict):
        return None
    bounds={"loss_w_k":(10,5000),"capacity_kwh_k":(.1,200),"cop":(1,8),"rmse_kw":(0,2),"samples":(24,1e9)}
    for key,(lo,hi) in bounds.items():
        value=fit.get(key)
        if key=="cop" and value is None and fit.get("cop_source")=="not_applicable":
            continue
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value) or not lo<=value<=hi:
            return None
    return {"fit":dict(fit),"calculated_at":result.get("calculated_at"),"fingerprint":fingerprint(config),"generation":config.get("calibration_generation",0)}

def current(record,config):
    if not isinstance(record,dict) or record.get("fingerprint")!=fingerprint(config) or record.get("generation")!=config.get("calibration_generation",0):
        return None
    return accepted({"status":"estimated","fit":record.get("fit"),"calculated_at":record.get("calculated_at")},config)

def effective_loss(config,record):
    valid=current(record,config)
    if config.get("apply_learned",False) and valid:
        return valid["fit"]["loss_w_k"],"learned"
    return config.get("h"),"manual" if config.get("h") else "learning_pending"

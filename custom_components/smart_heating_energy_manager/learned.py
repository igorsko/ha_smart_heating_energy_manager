"""Validate and isolate persisted model estimates from manual configuration."""
from math import isfinite
import hashlib
import json

def fingerprint(config):
    fields={k:config.get(k) for k in ("indoor","outdoor","generators","indoor_reference","outdoor_reference")}
    return hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()

def validation_status(validation):
    """Conservative provisional quality gate, not live forecast validation."""
    if not isinstance(validation,dict) or validation.get("status")!="evaluated":
        return "unvalidated"
    keys=("mae_c","rmse_c","bias_c","baseline_mae_c","samples","training_samples")
    if any(not isinstance(validation.get(k),(int,float)) or isinstance(validation[k],bool) or not isfinite(validation[k]) for k in keys):
        return "unvalidated"
    mae,rmse,bias,baseline,n,training=(validation[k] for k in keys)
    if n<12 or training<24 or min(mae,rmse,baseline)<0 or rmse+1e-9<mae or abs(bias)>mae+1e-9:
        return "unvalidated"
    if mae<=.5 and rmse<=.75 and abs(bias)<=.3 and mae<baseline:
        return "historically_validated"
    return "poor_validation"

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
    return {"fit":dict(fit),"validation":dict(result["validation"]) if isinstance(result.get("validation"),dict) else {}, "calculated_at":result.get("calculated_at"),"fingerprint":fingerprint(config),"generation":config.get("calibration_generation",0)}

def current(record,config):
    if not isinstance(record,dict) or record.get("fingerprint")!=fingerprint(config) or record.get("generation")!=config.get("calibration_generation",0):
        return None
    return accepted({"status":"estimated","fit":record.get("fit"),"validation":record.get("validation"),"calculated_at":record.get("calculated_at")},config)

def effective_loss(config,record):
    valid=current(record,config)
    if config.get("apply_learned",False) and valid and validation_status(valid.get("validation"))=="historically_validated":
        return valid["fit"]["loss_w_k"],"learned"
    if config.get("h"):
        return config["h"],"manual"
    from .bootstrap import building_estimate
    h,_=building_estimate(config)
    return h,"estimated" if h is not None else "learning_pending"


def validated_cop(config, record):
    """Return only an independently checked aggregate COP, never a per-head fit."""
    if not config.get("apply_learned",False):
        return None
    valid=current(record,config)
    if not valid or validation_status(valid["validation"])!="historically_validated":
        return None
    fit,check=valid["fit"],valid["validation"]
    if fit.get("cop_source")!="estimated" or check.get("training_cop_source")!="estimated":
        return None
    n,mae,baseline,training=(check.get(k) for k in ("hp_samples","hp_mae_c","hp_baseline_mae_c","training_cop"))
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not isfinite(v) for v in (n,mae,baseline,training)):
        return None
    cop=fit["cop"]
    if cop is None or n<8 or not 0<=mae<=.5 or mae>=baseline or not 1<=training<=8 or abs(cop-training)>max(.3,.15*training):
        return None
    return cop


def cop_context(config,record):
    """Expose aggregate estimate without attributing it to individual splits."""
    cop=validated_cop(config,record)
    count=sum(g.get("kind")=="heat_pump" for g in config.get("generators",{}).values())
    return {"cop":cop,"scope":"single_generator" if count==1 else "aggregate","generator_count":count}

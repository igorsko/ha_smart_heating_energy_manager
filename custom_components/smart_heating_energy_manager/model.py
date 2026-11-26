"""Pure, advisory thermal and marginal cost calculations."""
import math

def finite(value):
    """Return a finite float or None for invalid sensor data."""
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None

def electricity_price(pun, unit, fixed, spread, losses, variable, tax, vat):
    """Use a valid index in EUR/kWh or EUR/MWh; fixed price is all-inclusive."""
    index = finite(pun)
    if index is None or unit not in ("EUR/kWh", "€/kWh", "EUR/MWh", "€/MWh"):
        return fixed, "fixed"
    if unit.endswith("MWh"):
        index /= 1000
    return ((index + spread) * (1 + losses) + variable + tax) * (1 + vat), "index"

def estimate(indoor, outdoor, h, electricity, cop, pellet_price, pellet_mass, lhv, efficiency):
    """Return thermal demand and costs; missing temperatures never become zero."""
    heat = max(0, indoor - outdoor) * h / 1000 if indoor is not None and outdoor is not None else None
    hp_cost = electricity / cop
    pellet_cost = pellet_price / (pellet_mass * lhv * efficiency)
    recommended = "unknown" if heat is None else "none" if heat == 0 else "heat_pump" if hp_cost <= pellet_cost else "pellet"
    return {"heat_demand": heat, "heat_pump_cost": hp_cost, "pellet_cost": pellet_cost,
            "resistance_cost": electricity, "recommended_source": recommended,
            "break_even_cop": electricity / pellet_cost if pellet_cost > 0 else None}

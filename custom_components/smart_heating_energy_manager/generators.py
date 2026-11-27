"""Vendor-independent economic comparison of configured heat sources."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Generator:
    identifier: str
    kind: str
    efficiency: float
    capacity_kw: float
    fuel_price: float = 0
    fuel_quantity: float = 1
    fuel_energy_kwh: float = 1
    enabled: bool = True

    def __post_init__(self):
        if not self.identifier.strip() or self.kind not in ("heat_pump", "resistance", "fuel"):
            raise ValueError("Invalid generator")
        values = (self.efficiency, self.capacity_kw, self.fuel_quantity, self.fuel_energy_kwh)
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("Invalid generator parameters")
        if self.kind != "heat_pump" and self.efficiency > 1:
            raise ValueError("Efficiency must be <= 1")
        if not math.isfinite(self.fuel_price) or self.fuel_price < 0:
            raise ValueError("Invalid fuel price")

    def thermal_cost(self, electricity):
        if self.kind == "fuel":
            return self.fuel_price / (self.fuel_quantity * self.fuel_energy_kwh * self.efficiency)
        return None if electricity is None else electricity / self.efficiency

def rank_generators(generators, electricity, demand):
    """Return viable single-source choices; never issue actuator commands."""
    if demand is None or not math.isfinite(demand) or demand <= 0:
        return []
    if electricity is not None and not math.isfinite(electricity):
        electricity = None
    ids = [g.identifier for g in generators]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate generator identifier")
    choices = []
    for g in generators:
        if not g.enabled or g.capacity_kw < demand:
            continue
        cost = g.thermal_cost(electricity)
        if cost is not None:
            choices.append((g.identifier, cost))
    return sorted(choices, key=lambda item: (item[1], item[0]))


def capacity_status(data, demand):
    """Do not treat onboarding placeholders as actual heating capacity."""
    from .onboarding import ready
    if not data.get("enabled",True):
        return "disabled"
    if not ready(data):
        return "parameters_pending"
    capacity=data.get("capacity_kw")
    if not isinstance(capacity,(int,float)) or isinstance(capacity,bool) or not math.isfinite(capacity) or capacity<=0:
        return "capacity_unknown"
    if demand is None:
        return "demand_unknown"
    return "capacity_sufficient" if capacity>=demand else "capacity_insufficient"

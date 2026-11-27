import importlib
import sys
import types
import unittest
from pathlib import Path
pkg=types.ModuleType("bootstrap_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".bootstrap")
learned=importlib.import_module(pkg.__name__+".learned")
class BootstrapTests(unittest.TestCase):
    def test_building(self):
        self.assertEqual(m.building_estimate({}), (None,None))
        self.assertEqual(m.building_estimate({"building_area":100,"building_profile":"medium"}),(250,7.5))
        self.assertEqual(learned.effective_loss({"building_area":100,"h":123},None),(123,"manual"))
    def test_economic_independent(self):
        devices={"hp":{"kind":"heat_pump","technical_configured":False},"r":{"kind":"resistance","technical_configured":False},"f":{"kind":"fuel","technical_configured":False}}
        costs=m.economic_costs(devices,.3)
        self.assertEqual([c["id"] for c in costs],["hp","r"])
        self.assertAlmostEqual(costs[0]["cost"],.1)
        self.assertEqual(costs[0]["source"],"estimated")
        self.assertEqual(m.economic_costs(devices,None),[])

    def test_winnet_cost_without_technical_readiness(self):
        from types import SimpleNamespace as N
        d={"kind":"fuel","technical_configured":False,"control_entity":"climate.example","fuel_price":0,"fuel_quantity":1,"fuel_energy_kwh":1,"efficiency":1}
        values={"number.example_pellet_price_per_bag":(7.79,"€"),"number.example_pellet_bag_weight":(15,"kg"),"sensor.example_effective_pellet_consumption":(.8404,"kg/h")}
        entries=[N(entity_id=k,device_id="a",platform="winnet_stove",disabled_by=None) for k in ["climate.example",*values]]
        states={k:N(state=v,attributes={"unit_of_measurement":u}) for k,(v,u) in values.items()}
        g=m.winnet_parameters(d,entries,states.get)
        self.assertFalse(g["technical_configured"])
        self.assertEqual(d["fuel_price"],0)
        row=m.economic_costs({"stove":g},None)[0]
        self.assertAlmostEqual(row["cost"],7.79/(15*4.8*.9))
        self.assertAlmostEqual(row["estimated_burning_cost_per_hour"],.8404*7.79/15)
        self.assertEqual(row["source"],"winnet_estimated")
        self.assertEqual(m.winnet_parameters({**d,"technical_configured":True},entries,states.get)["fuel_price"],0)

    def test_declared_capacity_is_not_electrical_input(self):
        from types import SimpleNamespace as N
        d={"kind":"heat_pump","technical_configured":False,"control_entity":"climate.unit","capacity_kw":1}
        entries=[N(entity_id=e,device_id=device,platform="example",disabled_by=None) for e,device in [("climate.unit","a"),("sensor.unit_power","a"),("sensor.unit_rated_heat_output","a"),("sensor.other_rated_heat_output","b")]]
        states={"sensor.unit_power":N(state=900,attributes={"unit_of_measurement":"W"}),"sensor.unit_rated_heat_output":N(state=2500,attributes={"unit_of_measurement":"W"}),"sensor.other_rated_heat_output":N(state=9,attributes={"unit_of_measurement":"kW"})}
        g=m.declared_capacity(d,entries,states.get)
        self.assertEqual(g["capacity_kw"],2.5)
        self.assertEqual(g["_capacity_origin"],"declared")
        self.assertEqual(m.advisory_generator(g,"hp").efficiency,3)
        self.assertEqual(d["capacity_kw"],1)
        states.pop("sensor.unit_rated_heat_output")
        self.assertIsNone(m.advisory_generator(m.declared_capacity(d,entries,states.get),"hp"))
        self.assertEqual(m.declared_capacity({**d,"technical_configured":True},entries,states.get)["capacity_kw"],1)

    def test_live_heat_pump_power_and_cop(self):
        from datetime import datetime, timezone, timedelta
        from types import SimpleNamespace as N
        now=datetime.now(timezone.utc)
        d={"kind":"heat_pump","technical_configured":False,"power_entity":"sensor.input","control_entity":"climate.unit"}
        states={"sensor.input":N(state="0.58",attributes={"unit_of_measurement":"kW"},last_updated=now),"climate.unit":N(state="heat",attributes={"hvac_action":"heating"})}
        row=m.heat_pump_live(d,states.get,7,now)
        self.assertEqual(row["power_w"],580)
        self.assertEqual(row["cop"],3)
        self.assertEqual(row["cop_source"],"estimated")
        self.assertAlmostEqual(row["heat_kw"],1.74)
        states["climate.unit"].attributes={}
        self.assertIsNone(m.heat_pump_live(d,states.get,7,now)["heat_kw"])
        self.assertIsNone(m.heat_pump_live(d,states.get,7,now+timedelta(minutes=16))["power_w"])

    def test_hourly_telemetry(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace as N
        now=datetime.now(timezone.utc)
        hp={"kind":"heat_pump","technical_configured":False}
        row=m.heat_pump_live(hp,lambda _:None,7,now,{"power_w":600,"power_entity":"sensor.energy","interval_minutes":60},.3)
        self.assertEqual(row["power_source"],"counter_average")
        self.assertAlmostEqual(row["cost_per_hour"],.18)
        self.assertIsNone(row["heat_kw"])
        d={"kind":"fuel","fuel_rate_entity":"sensor.rate","state_entity":"binary_sensor.burning","active_states":"on","inactive_states":"off","fuel_price":7.79,"fuel_quantity":15,"fuel_energy_kwh":4.8,"efficiency":.9}
        states={"sensor.rate":N(state=".84",attributes={"unit_of_measurement":"kg/h"},last_updated=now),"binary_sensor.burning":N(state="on")}
        row=m.fuel_live(d,states.get,now)
        self.assertAlmostEqual(row["cost_per_hour"],.84*7.79/15)
        self.assertAlmostEqual(row["heat_kw"],.84*4.8*.9)
        states["binary_sensor.burning"].state="off"
        self.assertEqual(m.fuel_live(d,states.get,now)["rate_kg_h"],0)
        states["binary_sensor.burning"].state="unknown"
        self.assertIsNone(m.fuel_live(d,states.get,now)["rate_kg_h"])

    def test_cop_consistency(self):
        d={"kind":"heat_pump","technical_configured":False,"_learned_cop":4,"_capacity_origin":"declared","capacity_kw":3}
        self.assertEqual(m.effective_cop(d,7),(4,"learned"))
        self.assertAlmostEqual(m.economic_costs({"hp":d},.3,7)[0]["cost"],.075)
        self.assertEqual(m.advisory_generator(d,"hp",7).efficiency,4)
        self.assertEqual(m.effective_cop({**d,"technical_configured":True,"efficiency":2.5},7),(2.5,"manual"))
        self.assertEqual(m.effective_cop({**d,"cop_curve":"0=2\n10=4"},5),(3,"configured_curve"))

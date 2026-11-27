import importlib
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

pkg=types.ModuleType("joint_plan_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".joint_plan")

class JointPlanTests(unittest.TestCase):
    def data(self):
        heating=[]
        solar=[]
        for hour,pv in [(9,0),(10,2),(11,0)]:
            t=f"2026-11-27T{hour:02}:00:00+00:00"
            heating.append({"datetime":t,"heat_kw":1,"electricity_kwh":.5,"fuel_cost":0,"generator":"hp"})
            solar.append({"datetime":t,"pv_kwh":pv})
        return heating,solar
    def test_dhw_solar(self):
        h,s=self.data()
        dhw={"entity":"switch.boiler","below_minimum":False,"ideal_heat_kwh":1,"rated_kw":1}
        result=m.optimize(h,s,.2,.3,dhw,export_price=.05)
        self.assertEqual(result["status"],"estimated")
        self.assertEqual(result["dhw_start"],"2026-11-27T10:00:00+00:00")
        for row in result["rows"]:
            self.assertAlmostEqual(row["pv_kwh"]+row["grid_kwh"]+row["battery_discharge_kwh"],row["base_kwh"]+row["heating_kwh"]+row["dhw_kwh"]+row["export_kwh"]+row["battery_charge_kwh"],places=3)
    def test_battery(self):
        h,s=self.data()
        battery={"capacity":2,"soc":50,"reserve":25,"charge_kw":1,"discharge_kw":1,"efficiency":1}
        result=m.optimize(h,s,.2,.3,battery=battery,export_price=.05)
        self.assertEqual(result["status"],"estimated")
        self.assertGreaterEqual(min(r["battery_soc"] for r in result["rows"]),25)
        self.assertLessEqual(max(r["battery_soc"] for r in result["rows"]),100)
    def test_missing(self):
        h,s=self.data()
        self.assertEqual(m.optimize(h,s,None,.3,export_price=0)["status"],"configure_assumptions")
        self.assertEqual(m.optimize(h,s,.2,.3,{"entity":"switch.b","below_minimum":True},export_price=0)["status"],"dhw_needs_attention")
        self.assertEqual(m.optimize(h,s,.2,.3,battery={"capacity":2},export_price=0)["status"],"configure_battery")

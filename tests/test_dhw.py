import importlib
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
pkg=types.ModuleType("dhw_test_package")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".dhw")

class DHWTests(unittest.TestCase):
    def test_energy(self):
        self.assertAlmostEqual(m.thermal_energy(80,45,60),1.395,places=3)
        self.assertIsNone(m.thermal_energy(80,None,60))
        self.assertEqual(m.thermal_energy(80,65,60),0)
    def test_solar_window(self):
        rows=[{"datetime":f"2026-11-27T{h:02}:00:00+00:00","pv_kwh":v} for h,v in [(9,.1),(10,1),(11,2),(12,.1)]]
        now=datetime(2026,11,27,8,tzinfo=timezone.utc)
        result=m.solar_window(rows,2,1,now)
        self.assertEqual(result["start"],"2026-11-27T10:00:00+00:00")
        self.assertEqual(result["potential_pv_kwh"],2)
        self.assertIsNone(m.solar_window(rows[:1],2,1,now))
    def test_optional(self):
        self.assertEqual(m.snapshot({},lambda _:None),{})
        self.assertIsNone(m.snapshot({"entity":"switch.boiler"},lambda _:None)["temperature_c"])

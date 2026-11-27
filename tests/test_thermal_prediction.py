import importlib
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
pkg=types.ModuleType("thermal_prediction_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".thermal_prediction")
g=importlib.import_module(pkg.__name__+".generators")

class ThermalPredictionTests(unittest.TestCase):
    def test_equilibrium_and_inverse(self):
        self.assertAlmostEqual(m.step(20,0,200,4,4),20)
        self.assertLess(m.step(20,0,200,4),20)
        need=m.required_heat(19,0,200,4,20,.5)
        self.assertAlmostEqual(m.step(19,0,200,4,need,.5),20)
    def test_scenario(self):
        hp=g.Generator("hp","heat_pump",3,20)
        hours=[{"datetime":f"2026-11-27T{h:02}:00:00+00:00","temperature_c":5,"generators":[hp],"price":.3,"pv_kwh":2 if h==10 else 0} for h in (9,10,11)]
        result=m.simulate(hours,20,100,4,20,1,datetime(2026,11,27,9,30,tzinfo=timezone.utc))
        self.assertEqual(result["status"],"estimated")
        self.assertEqual(result["baseline"][0]["duration_hours"],.5)
        self.assertEqual(result["baseline"][1]["end_c"],20)
        self.assertEqual(result["preheat"][1]["end_c"],21)
        self.assertGreater(result["preheat"][2]["end_c"],20)
    def test_missing(self):
        self.assertEqual(m.simulate([],20,100,None,20)["status"],"configure_model")
        self.assertEqual(m.simulate([],20,100,4,20)["status"],"incomplete_weather")

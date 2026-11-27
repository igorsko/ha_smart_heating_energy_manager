import ast
import importlib
import sys
import types
import unittest
from pathlib import Path
root=Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager"
pkg=types.ModuleType("passive_solar_tests")
pkg.__path__=[str(root)]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".thermal_prediction")
g=importlib.import_module(pkg.__name__+".generators")
class PassiveSolarTests(unittest.TestCase):
    def test_solar_reduces_heat(self):
        hp=g.Generator("hp","heat_pump",3,10)
        hours=[{"datetime":"2026-11-27T12:00:00+00:00","temperature_c":0,"generators":[hp],"price":.3,"pv_kwh":1}]
        result=m.simulate(hours,20,200,4,20,solar_gain_factor=2)
        self.assertEqual(result["baseline"][0]["solar_gain_kwh"],2)
        self.assertAlmostEqual(result["baseline"][0]["heat_kwh"],2)
        self.assertAlmostEqual(result["without_solar"][0]["heat_kwh"],4)
    def test_missing_solar(self):
        h=[{"datetime":"2026-11-27T12:00:00+00:00","temperature_c":20,"pv_kwh":None}]
        result=m.simulate(h,20,200,4,20,solar_gain_factor=1)
        self.assertEqual(result["solar_gain_coverage"],0)
        self.assertIsNone(result["baseline"][0]["solar_gain_kwh"])
    def test_discovery_not_shadowed(self):
        tree=ast.parse((root/"sensor.py").read_text())
        update=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="async_update")
        calls={n.func.id for n in ast.walk(update) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        self.assertIn("tariff_candidates",calls)
        self.assertNotIn("candidates",calls)

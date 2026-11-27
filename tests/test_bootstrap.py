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

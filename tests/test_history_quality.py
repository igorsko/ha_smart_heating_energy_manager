import importlib
import sys
import types
import unittest
from pathlib import Path
pkg=types.ModuleType("quality_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".history_quality")
h=importlib.import_module(pkg.__name__+".history_input")
class QualityTests(unittest.TestCase):
    def test_coverage_missing_samples(self):
        series=h.Series([h.Sample(0,20),h.Sample(3600,20),h.Sample(7200,None)])
        self.assertEqual(m.temperature_coverage(series,0,7200,3600,7200),.5)
    def test_readiness_zero_temperature_and_price(self):
        self.assertEqual(m.readiness(2,2,0,150,5,0)["complete"],5)
        self.assertEqual(m.readiness(1,2,None,None,None,0)["complete"],1)
        self.assertFalse(m.readiness(0,0,0,150,5,0)["checks"]["indoor"])

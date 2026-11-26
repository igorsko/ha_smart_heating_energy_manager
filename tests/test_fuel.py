import unittest
import importlib
import sys
import types
from pathlib import Path
pkg=types.ModuleType("fuel_test_package")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
f=importlib.import_module(pkg.__name__+".fuel")

class FuelTests(unittest.TestCase):
    def test_rates(self):
        self.assertEqual(f.parse_rates("1=0.8\n2=1.2"),{"1":.8,"2":1.2})
        for value in ("1=-1","1=nan","1=1\n1=2"):
            with self.assertRaises(ValueError):
                f.parse_rates(value)
    def test_mass(self):
        self.assertAlmostEqual(f.mass_to_units(800,"g","kg"),.8)
        self.assertIsNone(f.mass_to_units(1,"L","kg"))
    def test_levels(self):
        states=[f.Sample(0,"heat"),f.Sample(3600,"off")]
        levels=[f.Sample(0,"1"),f.Sample(1800,"2")]
        series=f.fuel_rate_series(states,levels,{"1":.8,"2":1.2},{"heat"},{"off"},4.32,7200)
        self.assertAlmostEqual(series.counter_delta(0,3600,7200),4.32)
    def test_unknown_level(self):
        series=f.fuel_rate_series([f.Sample(0,"heat")],[f.Sample(0,"3")],{"1":.8},{"heat"},{"off"},4.32,7200)
        self.assertIsNone(series.counter_delta(0,3600,7200))

import unittest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("model", Path(__file__).parents[1] / "custom_components/smart_heating_energy_manager/model.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

class ModelTests(unittest.TestCase):
    def test_index_conversion(self):
        self.assertEqual(model.electricity_price(120, "EUR/MWh", .3, 0, 0, 0, 0, 0), (.12, "index"))
    def test_missing_index(self):
        self.assertEqual(model.electricity_price("unavailable", "EUR/kWh", .3, 0, 0, 0, 0, 0), (.3, "fixed"))
    def test_heat(self):
        r = model.estimate(20, 0, 158.5, .31, 3.75, 7.79, 15, 4.8, .9)
        self.assertAlmostEqual(r["heat_demand"], 3.17)
        self.assertEqual(r["recommended_source"], "heat_pump")
    def test_missing_temperature(self):
        r = model.estimate(None, 0, 158.5, .31, 3.75, 7.79, 15, 4.8, .9)
        self.assertIsNone(r["heat_demand"])
        self.assertEqual(r["recommended_source"], "unknown")
    def test_real_zero(self):
        self.assertEqual(model.finite(0), 0)

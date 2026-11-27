import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location("prediction",Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager/prediction.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PredictionTests(unittest.TestCase):
    def test_power_units(self):
        self.assertEqual(m.kw("2000","W"),2)
        self.assertIsNone(m.kw("2000","kWh"))
        self.assertIsNone(m.kw("unavailable","W"))
    def test_plan(self):
        g=SimpleNamespace(enabled=True,capacity_kw=4,identifier="hp",thermal_cost=lambda price:price/4)
        rows=m.plan([{"datetime":"2026-01-01T10:00:00+00:00","temperature_c":0}],150,20,[g],.32)
        self.assertEqual(rows[0]["heat_kw"],3)
        self.assertEqual(rows[0]["generator"],"hp")
        self.assertEqual(rows[0]["cost_per_hour"],.24)
    def test_missing_model(self):
        self.assertEqual(m.plan([],None,20,[],.3),[])
    def test_insufficient_capacity(self):
        g=SimpleNamespace(enabled=True,capacity_kw=1,identifier="hp",thermal_cost=lambda price:.1)
        rows=m.plan([{"datetime":"t","temperature_c":0}],150,20,[g],.3)
        self.assertIsNone(rows[0]["generator"])
        self.assertIsNone(rows[0]["cost_per_hour"])

import unittest
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("calibration", Path(__file__).parents[1] / "custom_components/smart_heating_energy_manager/calibration.py")
cal = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cal
spec.loader.exec_module(cal)

class CalibrationTests(unittest.TestCase):
    def test_synthetic_balance(self):
        samples = []
        for i in range(36):
            outdoor = float(i % 12)
            start = 20.
            hp = .3 if i % 3 == 0 else 0.
            stove = 3.456 if i % 3 == 1 else 0.
            resistance = .4 if i % 5 == 0 else 0.
            # Exact solution of the interval-average discrete balance.
            rate = (stove + resistance + 3.75*hp - .1585*(start-outdoor))/(4 + .1585/2)
            samples.append(cal.Interval(1,start,start+rate,outdoor,stove,hp,resistance))
        fit = cal.fit(samples)
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit.loss_w_k,158.5)
        self.assertAlmostEqual(fit.capacity_kwh_k,4)
        self.assertAlmostEqual(fit.cop,3.75)
    def test_insufficient_data(self):
        self.assertIsNone(cal.fit([]))
    def test_unidentifiable(self):
        self.assertIsNone(cal.fit([cal.Interval(1,20,20,0,3,0,0)]*30))

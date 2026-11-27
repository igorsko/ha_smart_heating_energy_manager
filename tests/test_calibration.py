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

    def test_fuel_only_and_known_cop(self):
        for hp_only in (False,True):
            samples=[]
            for i in range(36):
                outdoor=float(i%12)
                heat=3.0 if i%3==0 else 0.
                rate=(heat-.15*(20-outdoor))/(4+.15/2)
                samples.append(cal.Interval(1,20,20+rate,outdoor,0 if hp_only else heat,heat/3 if hp_only else 0,0))
            result=cal.fit(samples,known_cop=3 if hp_only else None)
            self.assertIsNotNone(result)
            self.assertAlmostEqual(result.loss_w_k,150)
            self.assertAlmostEqual(result.capacity_kwh_k,4)
            self.assertEqual(result.cop,3 if hp_only else None)
            self.assertEqual(result.cop_source,"configured" if hp_only else "not_applicable")
            if hp_only:
                self.assertIsNone(cal.fit(samples))

    def test_holdout_validation(self):
        samples=[]
        for i in range(60):
            outdoor=float(i%12)
            heat=3.0 if i%3==0 else 0.
            rate=(heat-.15*(20-outdoor))/(4+.15/2)
            samples.append(cal.Interval(1,20,20+rate,outdoor,heat,0,0))
        result=cal.validate_holdout(samples)
        self.assertEqual(result["status"],"evaluated")
        self.assertEqual(result["samples"],15)
        self.assertEqual(result["training_samples"],45)
        self.assertLess(result["mae_c"],.01)
        self.assertLess(result["mae_c"],result["baseline_mae_c"])
        self.assertEqual(cal.validate_holdout(samples[:25])["status"],"insufficient_data")
        shifted=[cal.Interval(s.hours,s.indoor_start,s.indoor_end+1,s.outdoor,s.stove_kwh,s.hp_kwh,s.resistance_kwh) for s in samples[-15:]]
        self.assertGreater(cal.validate_holdout(samples[:45]+shifted)["mae_c"],.9)

import importlib
import sys
import types
import unittest
from pathlib import Path
from math import exp
from unittest.mock import patch

pkg=types.ModuleType("solar_gain_learning_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".passive_solar")
cal=importlib.import_module(pkg.__name__+".calibration")

class SolarGainTests(unittest.TestCase):
    def test_missing_data(self):
        self.assertEqual(m.estimate([],[])["status"],"insufficient_data")

    def test_requires_independent_model(self):
        rows=[(i,cal.Interval(1,20,20,5,0,0,0),1) for i in range(48)]
        self.assertEqual(m.estimate([],rows)["status"],"independent_model_unavailable")

    def test_solar_factor_validation(self):
        rows=[]
        for i in range(64):
            pv=.2+(i%5)*.2
            end=5+15*exp(-.2/5)+1.5*pv*(1-exp(-.2/5))/.2
            rows.append((i,cal.Interval(1,20,end,5,0,0,0),pv))
        with patch.object(m,"fit",return_value=cal.Fit(200,5,None,0,24)):
            result=m.estimate([],rows)
        self.assertEqual(result["status"],"validated")
        self.assertAlmostEqual(result["factor"],1.5)
        self.assertLess(result["mae_c"],result["baseline_mae_c"])

    def test_future_night_excluded(self):
        s=cal.Interval(1,20,20,5,0,0,0)
        rows=[(i,s,1) for i in range(48)]
        with patch.object(m,"fit",return_value=None) as fit:
            m.estimate([(1,s),(100,s)],rows)
            self.assertEqual(fit.call_args.args[0],[s])

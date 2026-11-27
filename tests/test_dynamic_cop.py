import importlib
import sys
import types
import unittest
from pathlib import Path
from math import exp
from unittest.mock import patch

pkg=types.ModuleType("dynamic_cop_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".dynamic_cop")
cal=importlib.import_module(pkg.__name__+".calibration")

class DynamicCopTests(unittest.TestCase):
    def test_insufficient_data(self):
        self.assertEqual(m.estimate([])["status"],"insufficient_data")

    def test_independent_fit_required(self):
        rows=[cal.Interval(1,20,20,5,0,1,0)]*60
        self.assertEqual(m.estimate(rows)["status"],"independent_model_unavailable")

    def test_temperature_curve_validation(self):
        # Isolate the curve estimator from the separately tested building fit.
        rows=[]
        for i in range(80):
            t=2.5 if i%2 else 7.5
            cop=2 if i%2 else 4
            end=t+(20-t)*exp(-.2/5)+cop*(1-exp(-.2/5))/.2
            rows.append(cal.Interval(1,20,end,t,0,1,0))
        with patch.object(m,"fit",return_value=cal.Fit(200,5,None,0,24)):
            result=m.estimate(rows)
        self.assertEqual(result["status"],"validated")
        self.assertAlmostEqual(result["points"][0][1],2)
        self.assertAlmostEqual(result["points"][1][1],4)
        self.assertLess(result["mae_c"],result["constant_baseline_mae_c"])

    def test_shared_meters(self):
        devices={"a":{"kind":"heat_pump","energy_entity":"sensor.common","energy_alternatives":["sensor.common"]},"b":{"kind":"heat_pump","energy_entity":"sensor.common"},"c":{"kind":"fuel","energy_entity":"sensor.common"}}
        self.assertEqual(m.shared_sources(devices),{"sensor.common":["a","b"]})

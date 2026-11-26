import unittest
import importlib
import sys
import types
from pathlib import Path

pkg=types.ModuleType("history_test_package")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
h=importlib.import_module(pkg.__name__+".history_input")

class HistoryTests(unittest.TestCase):
    def series(self,*values):
        return h.Series([h.Sample(i*3600,v) for i,v in enumerate(values)])
    def test_zero_outdoor_valid(self):
        result=h.build_intervals(self.series(20,21),self.series(0,0),
            [("fuel",self.series(5,8)),("resistance",self.series(0,.5))],0,3600)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].outdoor,0)
        self.assertEqual(result[0].stove_kwh,3)
        self.assertEqual(result[0].resistance_kwh,.5)
    def test_reset(self):
        self.assertIsNone(self.series(10,1,12).counter_delta(0,7200,7200))
    def test_missing(self):
        self.assertEqual(h.build_intervals(self.series(20,None),self.series(0,0),
            [("heat_pump",self.series(0,1))],0,3600),[])
    def test_stale(self):
        self.assertIsNone(self.series(20).value_at(7201,7200))

    def test_runtime_energy(self):
        rate=h.RateSeries([h.Sample(0,3.456),h.Sample(1800,0),h.Sample(3600,0)])
        self.assertAlmostEqual(rate.counter_delta(0,3600,7200),1.728)
    def test_runtime_unknown(self):
        rate=h.RateSeries([h.Sample(0,3.456),h.Sample(1800,None),h.Sample(3600,0)])
        self.assertIsNone(rate.counter_delta(0,3600,7200))

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

    def test_fixed_mean(self):
        mean=h.MeanSeries([self.series(20,22),self.series(18,20)])
        self.assertEqual(mean.value_at(0,7200),19)
        self.assertEqual(mean.value_at(3600,7200),21)
        incomplete=h.MeanSeries([self.series(20,22),self.series(18,None)])
        self.assertIsNone(incomplete.value_at(3600,7200))

    def test_partial_calibration_only_complete_off_intervals(self):
        off=h.RateSeries([h.Sample(0,0),h.Sample(3600,0),h.Sample(5400,None),h.Sample(7200,0),h.Sample(10800,0)])
        intervals=h.build_intervals(self.series(20,20,20,20),self.series(5,5,5,5),
            [("fuel",self.series(0,1,2,3)),("resistance",off)],0,10800)
        self.assertEqual(len(intervals),2)
        self.assertTrue(all(s.resistance_kwh==0 for s in intervals))

    def test_alternatives_use_one_source_and_preserve_unknown(self):
        primary=self.series(0,2,None,5,6)
        secondary=self.series(0,9,10,11,None)
        combined=h.AlternativeSeries([primary,secondary])
        self.assertEqual(combined.counter_delta(0,3600,7200),2)
        self.assertEqual(combined.counter_delta(3600,7200,7200),1)
        self.assertEqual(combined.counter_delta(10800,14400,7200),1)
        self.assertIsNone(h.AlternativeSeries([self.series(0,None)]).counter_delta(0,3600,7200))

    def test_stable_off_requires_bounded_evidence(self):
        series=h.ConfirmedOffSeries([h.Sample(0,0),h.Sample(36000,0)])
        self.assertEqual(series.counter_delta(10800,14400,7200),0)
        self.assertIsNone(series.counter_delta(45000,48600,7200))
        broken=h.ConfirmedOffSeries([h.Sample(0,0),h.Sample(18000,None),h.Sample(36000,0)])
        self.assertIsNone(broken.counter_delta(10800,21600,7200))
        self.assertIsNone(broken.counter_delta(10800,14400,7200))
        self.assertIsNone(broken.counter_delta(21600,25200,7200))

    def test_recent_counter_power(self):
        samples=[h.Sample(0,10),h.Sample(3600,10.6)]
        row=h.recent_counter_power(samples,3600)
        self.assertAlmostEqual(row["power_w"],600)
        self.assertEqual(row["interval_minutes"],60)
        self.assertIsNone(h.recent_counter_power(samples,11000))
        self.assertIsNone(h.recent_counter_power([h.Sample(0,10),h.Sample(3600,10)],3600))
        self.assertIsNone(h.recent_counter_power([h.Sample(0,10),h.Sample(1800,None),h.Sample(3600,11)],3600))
        self.assertIsNone(h.recent_counter_power([h.Sample(0,10),h.Sample(3600,1)],3600))

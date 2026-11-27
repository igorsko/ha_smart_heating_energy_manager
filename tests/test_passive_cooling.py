import importlib
import sys
import types
import unittest
from math import exp
from pathlib import Path

pkg=types.ModuleType("passive_cooling_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".passive_cooling")
h=importlib.import_module(pkg.__name__+".history_input")

class CoolingTests(unittest.TestCase):
    def test_known_tau(self):
        rows=[m.CoolingSample(i*3600,1,20,5+15*exp(-1/30),5) for i in range(60)]
        result=m.analyze(rows)
        self.assertEqual(result["status"],"validated")
        self.assertAlmostEqual(result["tau_hours"],30)
        self.assertLess(result["mae_c"],result["baseline_mae_c"])

    def test_holdout_rejects_warming(self):
        rows=[m.CoolingSample(i*3600,1,20,5+15*exp(-1/30) if i<40 else 21,5) for i in range(60)]
        self.assertEqual(m.analyze(rows)["status"],"poor_validation")

    def test_insufficient_data(self):
        self.assertEqual(m.analyze([])["status"],"insufficient_data")

    def test_night_and_settling_evidence(self):
        indoor=h.Series([h.Sample(i*3600,20-i*.1) for i in range(8)])
        outdoor=h.Series([h.Sample(i*3600,5) for i in range(8)])
        off=h.ConfirmedOffSeries([h.Sample(0,0),h.Sample(25200,1)])
        night=h.ConfirmedOffSeries([h.Sample(0,0),h.Sample(18000,1)])
        rows=m.collect(indoor,outdoor,[off],night,0,25200,3600,7200)
        self.assertEqual([s.timestamp for s in rows],[7200,10800])
        self.assertEqual(m.collect(indoor,outdoor,[],night,0,25200,3600,7200),[])
        unknown=h.ConfirmedOffSeries([h.Sample(0,0),h.Sample(3600,None),h.Sample(25200,1)])
        self.assertEqual(m.collect(indoor,outdoor,[unknown],night,0,25200,3600,7200),[])

    def test_exclusion_counts_identify_generator(self):
        indoor=h.Series([h.Sample(i*3600,20) for i in range(8)])
        outdoor=h.Series([h.Sample(i*3600,5) for i in range(8)])
        night=h.ConfirmedOffSeries([h.Sample(0,0),h.Sample(25200,1)])
        active=h.ConfirmedOffSeries([h.Sample(0,1),h.Sample(25200,1)])
        counts={}
        self.assertEqual(m.collect(indoor,outdoor,{"heater":active},night,0,25200,3600,7200,counts),[])
        self.assertEqual(counts["examined"],7)
        self.assertGreater(counts["off_not_confirmed:heater"],0)

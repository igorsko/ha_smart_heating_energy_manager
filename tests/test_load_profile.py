import importlib
import sys
import types
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
pkg=types.ModuleType("load_profile_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".load_profile")
class LoadProfileTests(unittest.TestCase):
    def test_subtract_and_median(self):
        start=datetime(2026,11,20,tzinfo=timezone.utc)
        end=start+timedelta(days=4)
        stamps=[start.timestamp()+i*900 for i in range(385)]
        home=m.Series([m.Sample(t,2) for t in stamps])
        loads=m.Series([m.Sample(t,1.5) for t in stamps])
        p=m.profile(home,[loads],start,end,timezone.utc)
        self.assertEqual(p["12"]["kw"],.5)
        self.assertEqual(p["12"]["samples"],4)
        self.assertEqual(m.profile(loads,[home],start,end,timezone.utc),{})

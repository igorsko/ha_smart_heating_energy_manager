import importlib
import sys
import types
import unittest
from pathlib import Path
pkg=types.ModuleType("area_test_package")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
areas=importlib.import_module(pkg.__name__+".areas")

class AreaTests(unittest.TestCase):
    def test_suggestions_not_confirmed(self):
        result=areas.zone_view({"a":{"name":"Room","temperature_candidates":["sensor.t"],"source_candidates":["climate.h"]}}, {})
        self.assertFalse(result["a"].get("confirmed",False))
        self.assertNotIn("temperature",result["a"])

    def test_shared_source_and_saved_mapping(self):
        discovered={k:{"name":k,"temperature_candidates":[]} for k in ("a","b")}
        saved={k:{"confirmed":True,"temperature":"sensor."+k,"sources":["climate.shared"]} for k in discovered}
        result=areas.zone_view(discovered,saved)
        self.assertEqual(result["a"]["sources"],result["b"]["sources"])
        self.assertTrue(result["a"]["confirmed"])

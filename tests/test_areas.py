import importlib.util
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("areas",Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager/areas.py")
areas=importlib.util.module_from_spec(spec)
spec.loader.exec_module(areas)

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

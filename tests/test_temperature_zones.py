import importlib.util
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("temperature_zones",Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager/temperature_zones.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class TemperatureTests(unittest.TestCase):
    def test_exterior_and_duplicate(self):
        zones={"a":{"name":"Soggiorno","temperature":"sensor.a"},"b":{"name":"Camera","temperature":"sensor.b"},"c":{"name":"Bagno","temperature":"sensor.a"},"d":{"name":"Esterno","temperature":"sensor.out"}}
        self.assertEqual(m.resolve(zones),(["sensor.a","sensor.b"],"sensor.out"))
        self.assertEqual(m.average_temperature(["sensor.a","sensor.b"],{"sensor.a":20,"sensor.b":22}.get),(21,2))
    def test_missing(self):
        self.assertEqual(m.average_temperature(["a","b"],{"a":0,"b":None}.get),(0,1))
        self.assertEqual(m.resolve({}, "sensor.in","sensor.out"),(["sensor.in"],"sensor.out"))

    def test_cooling_references_deduplicate_groups_and_exclude_outside(self):
        zones={"a":{"name":"A","temperature":"sensor.a","thermal_group":"Open space"},"b":{"name":"B","temperature":"sensor.a","thermal_group":"open SPACE"},"c":{"name":"C","temperature_candidates":["sensor.c"],"thermal_group":"Open space"},"d":{"name":"Esterno","temperature":"sensor.out","thermal_group":"Open space"}}
        refs=m.reference_config({},zones)["cooling_references"]
        self.assertEqual(refs["zone:c"]["entities"],["sensor.c"])
        self.assertEqual(refs["group:open space"]["entities"],["sensor.a","sensor.c"])
        self.assertNotIn("zone:d",refs)

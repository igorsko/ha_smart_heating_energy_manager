import importlib
import sys
import types
import unittest
from pathlib import Path
pkg=types.ModuleType("groups_solar_test")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
groups=importlib.import_module(pkg.__name__+".thermal_groups")
solar=importlib.import_module(pkg.__name__+".solar_prediction")

class GroupsSolarTests(unittest.TestCase):
    def test_shared_sources(self):
        z={"a":{"thermal_group":"Open space","temperature":"sensor.a","sources":["climate.a"],"confirmed":True},"b":{"thermal_group":"open SPACE","temperature":"sensor.b","sources":["climate.a"],"confirmed":True}}
        g=groups.groups(z,{"sensor.a":20,"sensor.b":22}.get)["open space"]
        self.assertEqual(g["temperature_c"],21)
        self.assertEqual(g["sources"],["climate.a"])
    def test_solar_aggregate(self):
        a={"wh_hours":{"2026-11-27T12:00:00+01:00":600}}
        b={"wh_hours":{"2026-11-27T11:00:00+00:00":400}}
        self.assertEqual(solar.hourly([a,b]),{"2026-11-27T11:00:00+00:00":1})
        self.assertEqual(solar.hourly([a,{"wh_hours":{}}]),{})

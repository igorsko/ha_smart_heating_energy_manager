import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

pkg=types.ModuleType("energy_import_test_package")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".energy_import")

class EnergyImportTests(unittest.TestCase):
    def test_multiple_sources_and_grid_sign(self):
        prefs={"energy_sources":[{"type":"solar","stat_rate":"sensor.a"},{"type":"solar","stat_rate":"sensor.b"},{"type":"grid","power_config":{"stat_rate":"sensor.grid"}},{"type":"battery","stat_soc":"sensor.soc","stat_rate":"sensor.bat"}]}
        states={k:SimpleNamespace(state=v,attributes={"unit_of_measurement":u}) for k,v,u in [("sensor.a","600","W"),("sensor.b","0.8","kW"),("sensor.grid","-200","W"),("sensor.soc","60","%"),("sensor.bat","-300","W")]}
        data=m.snapshot(prefs,states.get)
        self.assertAlmostEqual(data["pv_kw"],1.4)
        self.assertAlmostEqual(data["export_kw"],.2)
        self.assertEqual(data["battery_soc"],60)
        self.assertAlmostEqual(data["battery_net_kw"],-.3)
    def test_energy_not_power(self):
        data=m.snapshot({"energy_sources":[{"type":"solar","stat_energy_from":"sensor.total"}]},lambda _:None)
        self.assertIsNone(data["pv_kw"])
        self.assertEqual(data["energy_dashboard_sources"]["solar"][0]["stat_energy_from"],"sensor.total")
    def test_weighted_battery(self):
        prefs={"energy_sources":[{"type":"battery","stat_soc":"a","capacity":2},{"type":"battery","stat_soc":"b","capacity":8}]}
        states={k:SimpleNamespace(state=v,attributes={"unit_of_measurement":"%"}) for k,v in [("a",100),("b",50)]}
        self.assertEqual(m.snapshot(prefs,states.get)["battery_soc"],60)
    def test_legacy_grid(self):
        prefs={"energy_sources":[{"type":"grid","power":[{"stat_rate":"sensor.grid"}]}]}
        data=m.snapshot(prefs,lambda _:SimpleNamespace(state="400",attributes={"unit_of_measurement":"W"}))
        self.assertEqual(data["grid_net_kw"],.4)
        self.assertEqual(data["export_kw"],0)

    def test_discovery_distinguishes_production_and_consumption(self):
        prefs={"energy_sources":[{"type":"solar","stat_energy_from":"sensor.example_total"}]}
        states={k:SimpleNamespace(state=v,attributes={"unit_of_measurement":"W","device_class":"power"}) for k,v in [("sensor.example_production_ct_power","100"),("sensor.example_consumption_ct_power","678")]}
        discovered=m.discover_power(prefs,states.get,lambda _:list(states))
        data=m.snapshot(discovered,states.get)
        self.assertAlmostEqual(data["pv_kw"],.1)
        self.assertAlmostEqual(data["home_kw"],.678)
        self.assertNotIn("stat_rate",prefs["energy_sources"][0])
        self.assertIsNone(data["grid_net_kw"])
    def test_ambiguous_and_overlapping_sources(self):
        prefs={"energy_sources":[{"type":"solar","stat_energy_from":"sensor.total"}]}
        states={k:SimpleNamespace(state="100",attributes={"unit_of_measurement":"W"}) for k in ["sensor.a_production_ct_power","sensor.b_pv_power"]}
        data=m.snapshot(m.discover_power(prefs,states.get,lambda _:list(states)),states.get)
        self.assertIsNone(data["pv_kw"])
        prefs={"energy_sources":[{"type":"solar","stat_rate":"sensor.a"},{"type":"home","stat_rate":"sensor.a"}]}
        self.assertIsNone(m.snapshot(prefs,lambda _:SimpleNamespace(state="100",attributes={"unit_of_measurement":"W"}))["pv_kw"])

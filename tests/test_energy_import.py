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

    def test_directional_and_capacity_discovery(self):
        prefs={"energy_sources":[{"type":"solar","stat_energy_from":"sensor.solar_total"},{"type":"grid","stat_energy_from":"sensor.grid_total"},{"type":"battery","stat_energy_from":"sensor.discharge_total"}]}
        states={k:SimpleNamespace(state=v,attributes={"unit_of_measurement":u,"device_class":c}) for k,v,u,c in [
            ("sensor.site_production_ct_power",100,"W","power"),
            ("sensor.site_consumption_ct_power",700,"W","power"),
            ("sensor.site_battery_capacity",5000,"Wh","energy_storage"),
            ("sensor.site_battery_soc",5,"%","battery"),
            ("sensor.site_grid_import_power",600,"W","power"),
            ("sensor.site_grid_export_power",0,"W","power")]}
        pools={"sensor.solar_total":[k for k in states if "grid_" not in k],"sensor.grid_total":[k for k in states if "grid_" in k]}
        data=m.snapshot(m.discover_power(prefs,states.get,lambda e:pools.get(e,[])),states.get)
        self.assertEqual(data["battery_capacity_kwh"],5)
        self.assertEqual(data["battery_soc"],5)
        self.assertAlmostEqual(data["grid_net_kw"],.6)
        self.assertAlmostEqual(data["battery_net_kw"],0)
        self.assertEqual(data["energy_flow_origins"]["battery_net_kw"],"balance")
    def test_missing_two_flows_not_guessed(self):
        prefs={"energy_sources":[{"type":"solar","stat_rate":"sensor.pv"},{"type":"home","stat_rate":"sensor.home"},{"type":"grid"},{"type":"battery"}]}
        states={k:SimpleNamespace(state=v,attributes={"unit_of_measurement":"W"}) for k,v in [("sensor.pv",100),("sensor.home",700)]}
        data=m.snapshot(prefs,states.get)
        self.assertIsNone(data["grid_net_kw"])
        self.assertIsNone(data["battery_net_kw"])
    def test_discharge_and_import_sign(self):
        prefs={"energy_sources":[{"type":"grid","stat_rate":"sensor.grid"},{"type":"battery","stat_rate":"sensor.bat"},{"type":"solar","stat_rate":"sensor.pv"}]}
        states={k:SimpleNamespace(state=v,attributes={"unit_of_measurement":"W"}) for k,v in [("sensor.grid",-100),("sensor.bat",300),("sensor.pv",500)]}
        data=m.snapshot(prefs,states.get)
        self.assertAlmostEqual(data["home_kw"],.7)
        self.assertAlmostEqual(data["export_kw"],.1)
        self.assertEqual(data["energy_flow_origins"]["home_kw"],"balance")

    def test_unsigned_battery_zero_only(self):
        prefs={"energy_sources":[{"type":"solar","stat_rate":"sensor.pv"},{"type":"home","stat_rate":"sensor.home"},{"type":"grid"},{"type":"battery"}]}
        states={k:SimpleNamespace(state=v,attributes={"unit_of_measurement":"W"}) for k,v in [("sensor.pv",220),("sensor.home",870),("sensor.example_potenza",0)]}
        discovered=m.discover_power(prefs,states.get,lambda _:[],["sensor.example_potenza"])
        data=m.snapshot(discovered,states.get)
        self.assertEqual(data["battery_net_kw"],0)
        self.assertAlmostEqual(data["grid_net_kw"],.65)
        states["sensor.example_potenza"].state=100
        data=m.snapshot(discovered,states.get)
        self.assertIsNone(data["battery_net_kw"])
        self.assertIsNone(data["grid_net_kw"])

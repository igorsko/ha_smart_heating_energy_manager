import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as N
pkg=types.ModuleType("calibration_inputs_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".calibration_inputs")

class InputTests(unittest.TestCase):
    def test_incomplete_devices_with_meter(self):
        devices={"stove":{"kind":"fuel","technical_configured":False,"control_entity":"climate.stove","efficiency":1,"fuel_energy_kwh":1},
                 "hp":{"kind":"heat_pump","technical_configured":False,"control_entity":"climate.hp"}}
        entries=[N(entity_id=e,unique_id=e,device_id=d,platform=p,disabled_by=None) for e,d,p in [
            ("climate.stove","a","winnet_stove"),("sensor.stove_estimated_pellet_consumed","a","winnet_stove"),
            ("climate.hp","b","daikin"),("sensor.hp_heating_energy_consumption_yearly","b","daikin"),
            ("sensor.hp_heating_energy_consumption_daily","b","daikin"),("sensor.hp_cooling_energy_consumption_yearly","b","daikin")]]
        states={e.entity_id:N(state="10",attributes={"unit_of_measurement":"kg" if "pellet" in e.entity_id else "kWh","state_class":"total_increasing"}) for e in entries}
        resolved,report=m.calibration_inputs(devices,entries,states.get)
        self.assertTrue(report["stove"]["usable"])
        self.assertTrue(report["hp"]["usable"])
        self.assertEqual(resolved["stove"]["fuel_energy_kwh"],4.8)
        self.assertEqual(resolved["hp"]["energy_entity"],"sensor.hp_heating_energy_consumption_yearly")
        self.assertFalse(resolved["hp"]["technical_configured"])
        self.assertNotIn("energy_entity",devices["hp"])
    def test_missing_source_and_manual_priority(self):
        devices={"hp":{"kind":"heat_pump","technical_configured":False}}
        _,report=m.calibration_inputs(devices,[],lambda _:None)
        self.assertFalse(report["hp"]["usable"])
        devices["hp"]["energy_entity"]="sensor.manual"
        resolved,report=m.calibration_inputs(devices,[],lambda _:None)
        self.assertTrue(report["hp"]["usable"])
        self.assertEqual(resolved["hp"]["energy_entity"],"sensor.manual")

    def test_localized_and_resistance_sources(self):
        devices={"hp":{"kind":"heat_pump","technical_configured":False,"control_entity":"climate.hp"},
                 "r":{"kind":"resistance","technical_configured":False,"control_entity":"switch.r"}}
        entries=[N(entity_id=e,unique_id=e,device_id=d,platform=p,disabled_by=None) for e,d,p in [
            ("climate.hp","a","daikin"),("sensor.hp_consumo_riscaldamento_annuale","a","daikin"),
            ("sensor.hp_consumo_raffrescamento_annuale","a","daikin"),("switch.r","b","other"),
            ("sensor.r_power","b","other")]]
        states={e.entity_id:N(state="10",attributes={"unit_of_measurement":"W" if e.entity_id.endswith("_power") else "kWh","state_class":"total_increasing","device_class":"power" if e.entity_id.endswith("_power") else "energy"}) for e in entries if e.entity_id.startswith("sensor.")}
        resolved,report=m.calibration_inputs(devices,entries,states.get)
        self.assertEqual(resolved["hp"]["energy_entity"],"sensor.hp_consumo_riscaldamento_annuale")
        self.assertEqual(resolved["r"]["power_entity"],"sensor.r_power")
        self.assertTrue(report["r"]["usable"])

    def test_onecta_cross_device_isolation(self):
        devices={"hp":{"kind":"heat_pump","technical_configured":False,"control_entity":"climate.unit_room_temperature"}}
        entries=[N(entity_id=e,unique_id=e,device_id=d,platform="daikin_onecta",disabled_by=None,config_entry_id=c) for e,d,c in [
            ("climate.unit_room_temperature","a","one"),
            ("sensor.unit_climatecontrol_heating_energy_consumption_yearly","b","one"),
            ("sensor.other_climatecontrol_heating_energy_consumption_yearly","c","one"),
            ("sensor.unit_climatecontrol_heating_energy_consumption_monthly","d","two")]]
        state=N(state="10",attributes={"unit_of_measurement":"kWh","state_class":"total_increasing"})
        resolved,report=m.calibration_inputs(devices,entries,lambda _:state)
        self.assertEqual(resolved["hp"]["energy_entity"],entries[1].entity_id)
        self.assertTrue(report["hp"]["usable"])

    def test_vertigo_request_is_not_measured_runtime(self):
        entry=N(entity_id="switch.unit_heating",unique_id="heat",device_id="a",platform="olimpia_vertigo",disabled_by=None)
        devices={"r":{"kind":"resistance","technical_configured":False,"control_entity":entry.entity_id}}
        resolved,report=m.calibration_inputs(devices,[entry],lambda _:None)
        self.assertFalse(report["r"]["usable"])
        self.assertEqual(resolved["r"]["state_entity"],entry.entity_id)
        devices["r"]["manual_input_rate"]=1.5
        resolved,report=m.calibration_inputs(devices,[entry],lambda _:None)
        self.assertFalse(report["r"]["usable"])
        self.assertNotIn("manual_input_rate",resolved["r"])
        devices["r"]["power_entity"]="sensor.dedicated_power"
        _,report=m.calibration_inputs(devices,[entry],lambda _:None)
        self.assertTrue(report["r"]["usable"])

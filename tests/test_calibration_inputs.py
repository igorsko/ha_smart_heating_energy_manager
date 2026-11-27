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

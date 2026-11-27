import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager"/(name+".py"))
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

heat=load("heat_sources")
tariff=load("tariff_discovery")

class SourceTariffTests(unittest.TestCase):
    def test_heat_only(self):
        self.assertFalse(heat.eligible("switch.irrigation",{}))
        self.assertFalse(heat.eligible("switch.uv",{}))
        self.assertTrue(heat.eligible("switch.heating",{},True))
        self.assertTrue(heat.eligible("climate.room",{"hvac_modes":["heat"]}))
        self.assertFalse(heat.eligible("climate.cool",{"hvac_modes":["cool"]}))
    def test_index(self):
        e=SimpleNamespace(entity_id="sensor.pun",platform="pun",disabled_by=None)
        s=SimpleNamespace(state="120",attributes={"unit_of_measurement":"EUR/MWh"})
        self.assertEqual(tariff.candidates([e],lambda _:s),["sensor.pun"])
        self.assertAlmostEqual(tariff.index_value("120","EUR/MWh"),.12)
        self.assertIsNone(tariff.index_value("120","W"))

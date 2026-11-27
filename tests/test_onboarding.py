import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location("onboarding",Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager/onboarding.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class OnboardingTests(unittest.TestCase):
    def test_new_is_not_ready(self):
        data=m.merge_basic({},{"kind":"heat_pump","control_entity":"climate.test"},"Test")
        self.assertFalse(m.ready(data))
    def test_edit_preserves_existing(self):
        old={"kind":"fuel","efficiency":.9,"capacity_kw":9,"fuel_price":7,"fuel_quantity":15,"fuel_energy_kwh":4.8,"fuel_mass_entity":"sensor.mass"}
        data=m.merge_basic(old,{"kind":"fuel"},"New name")
        self.assertTrue(m.ready(data))
        self.assertEqual(data["fuel_mass_entity"],"sensor.mass")
        self.assertEqual(data["efficiency"],.9)
    def test_unique_meter(self):
        entries=[SimpleNamespace(entity_id="sensor.power")]
        state=SimpleNamespace(attributes={"device_class":"power","unit_of_measurement":"W"})
        self.assertEqual(m.suggest_sensors(entries,lambda _:state,"heat_pump"),{"power_entity":"sensor.power"})
        self.assertEqual(m.suggest_sensors(entries,lambda _:state,"fuel"),{})
        entries.append(SimpleNamespace(entity_id="sensor.power2"))
        self.assertEqual(m.suggest_sensors(entries,lambda _:state,"heat_pump"),{})

import importlib.util
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("thermal_zones",Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager/thermal_zones.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ThermalZonesTests(unittest.TestCase):
    def test_curve(self):
        curve=m.parse_curve("7=4\n-7=2")
        self.assertEqual(m.cop_at(curve,0,3),(3,"configured_curve"))
        self.assertEqual(m.cop_at(curve,-20,2.5),(2.5,"manual"))
        self.assertEqual(m.cop_at(curve,None,2.5),(2.5,"manual"))
    def test_invalid_curve(self):
        for text in ("0=2","0=nan\n7=4","0=3\n0=4","7=-2\n0=3"):
            with self.assertRaises(ValueError):
                m.parse_curve(text)
    def test_zone(self):
        self.assertAlmostEqual(m.zone_demand(20,0,100),2)
        self.assertIsNone(m.zone_demand(20,0,None))
        self.assertEqual(m.zone_demand(20,25,100),0)
        self.assertTrue(m.zone_status({"target_c":21},20,0)["below_target"])

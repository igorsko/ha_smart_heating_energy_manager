import unittest
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("generators", Path(__file__).parents[1] / "custom_components/smart_heating_energy_manager/generators.py")
g = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = g
spec.loader.exec_module(g)

class GeneratorTests(unittest.TestCase):
    def test_heat_pump_only(self):
        self.assertEqual(g.rank_generators([g.Generator("hp","heat_pump",4,6)], .2, 2), [("hp",.05)])
    def test_biomass_only_without_electricity_price(self):
        result = g.rank_generators([g.Generator("wood","fuel",.8,5,8,10,5)], None, 2)
        self.assertEqual(result,[("wood",.2)])
    def test_mixed_capacity(self):
        sources = [g.Generator("hp","heat_pump",4,2),g.Generator("gas","fuel",.9,8,1,1,10)]
        self.assertEqual(g.rank_generators(sources,.2,3)[0][0],"gas")
    def test_no_sources(self):
        self.assertEqual(g.rank_generators([], .2, 3),[])
    def test_unknown_demand(self):
        self.assertEqual(g.rank_generators([g.Generator("hp","heat_pump",4,6)], .2, None),[])

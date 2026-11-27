"""Regression tests for redundant configuration fields."""
import ast
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager"
class ConfiguratorFieldsTests(unittest.TestCase):
    def test_building_only_outdoor(self):
        tree=ast.parse((ROOT/"config_flow.py").read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="async_step_building")
        strings={n.value for n in ast.walk(node) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        self.assertNotIn("indoor",strings)
        self.assertIn("outdoor",strings)
    def test_tariff_components_do_not_reconfigure_base(self):
        tree=ast.parse((ROOT/"config_flow.py").read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="async_step_advanced_tariff")
        strings={n.value for n in ast.walk(node) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        self.assertTrue({"fixed","pun","use_index"}.isdisjoint(strings))
    def test_translations(self):
        for p in ("strings.json","translations/en.json","translations/it.json"):
            steps=json.loads((ROOT/p).read_text())["options"]["step"]
            self.assertEqual(set(steps["building"]["data"]),{"outdoor"})
            self.assertTrue({"fixed","pun","use_index"}.isdisjoint(steps["advanced_tariff"]["data"]))

import importlib.util
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("learned",Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager/learned.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class LearnedTests(unittest.TestCase):
    def setUp(self):
        self.config={"indoor":"sensor.a","outdoor":"sensor.b","h":200,"generators":{}}
        self.result={"status":"estimated","fit":{"loss_w_k":150,"capacity_kwh_k":4,"cop":3,"rmse_kw":.5,"samples":30},"calculated_at":"2026-01-01"}
    def test_opt_in(self):
        record=m.accepted(self.result,self.config)
        self.assertEqual(m.effective_loss(self.config,record),(200,"manual"))
        self.assertEqual(m.effective_loss({**self.config,"apply_learned":True},record),(150,"learned"))
    def test_reset_and_mapping_change(self):
        record=m.accepted(self.result,self.config)
        self.assertIsNone(m.current(record,{**self.config,"calibration_generation":1}))
        self.assertIsNone(m.current(record,{**self.config,"indoor":"sensor.c"}))
    def test_invalid(self):
        self.result["fit"]["cop"]=float("nan")
        self.assertIsNone(m.accepted(self.result,self.config))

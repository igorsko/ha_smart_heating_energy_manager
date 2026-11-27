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
        self.result["validation"]={"status":"evaluated","mae_c":.2,"rmse_c":.3,"bias_c":.1,"baseline_mae_c":.4,"samples":12,"training_samples":24}
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

    def test_reference_membership_and_no_cop(self):
        config={**self.config,"indoor_reference":["sensor.a","sensor.b"]}
        self.result["fit"].update(cop=None,cop_source="not_applicable")
        record=m.accepted(self.result,config)
        self.assertIsNotNone(record)
        self.assertIsNone(m.current(record,{**config,"indoor_reference":["sensor.a"]}))

    def test_unvalidated_and_poor_models_stay_manual(self):
        config={**self.config,"apply_learned":True}
        record=m.accepted(self.result,config)
        self.assertEqual(m.effective_loss(config,record),(200,"manual"))
        self.result["validation"]={"status":"evaluated","mae_c":.4,"rmse_c":.5,"bias_c":.1,"baseline_mae_c":.2,"samples":12,"training_samples":24}
        record=m.accepted(self.result,config)
        self.assertEqual(m.validation_status(record["validation"]),"poor_validation")
        self.assertEqual(m.effective_loss(config,record),(200,"manual"))

    def test_cop_requires_specific_holdout_and_stability(self):
        config={**self.config,"apply_learned":True,"generators":{"hp":{"kind":"heat_pump"}}}
        self.result["fit"]["cop_source"]="estimated"
        self.result["validation"]={"status":"evaluated","mae_c":.2,"rmse_c":.3,"bias_c":.1,"baseline_mae_c":.4,"samples":12,"training_samples":24,"hp_samples":8,"hp_mae_c":.2,"hp_baseline_mae_c":.4,"training_cop":3.1,"training_cop_source":"estimated"}
        record=m.accepted(self.result,config)
        self.assertEqual(m.validated_cop(config,record),3)
        self.assertEqual(m.cop_context(config,record)["scope"],"single_generator")
        self.assertIsNone(m.validated_cop({**config,"apply_learned":False},record))
        self.result["validation"]["hp_samples"]=2
        self.assertIsNone(m.validated_cop(config,m.accepted(self.result,config)))
        self.result["validation"].update(hp_samples=8,training_cop=5)
        self.assertIsNone(m.validated_cop(config,m.accepted(self.result,config)))
        self.result["validation"]["training_cop"]=3.1
        config["generators"]["hp2"]={"kind":"heat_pump"}
        self.assertEqual(m.cop_context(config,m.accepted(self.result,config))["scope"],"aggregate")

import importlib.util
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
spec=importlib.util.spec_from_file_location("forecast_validation",Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager/forecast_validation.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ForecastValidationTests(unittest.TestCase):
    def test_frozen_forecast(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        target=now+timedelta(hours=1)
        rows=[]
        m.issue(rows,now,"ref",[{"datetime":target.isoformat(),"temperature_c":5}],{},20)
        m.issue(rows,now,"ref",[{"datetime":target.isoformat(),"temperature_c":9}],{},20)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["prediction"],5)
        m.observe(rows,target,"ref",20,7)
        self.assertEqual(m.summarize(rows,"ref")["outdoor"]["mae_c"],2)
    def test_expired_and_wrong_reference(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        target=now+timedelta(hours=1)
        for ref,when in (("other",target),("ref",target+timedelta(minutes=11))):
            rows=m.issue([],now,"ref",[{"datetime":target.isoformat(),"temperature_c":5}],{},20)
            m.observe(rows,when,ref,20,7)
            self.assertEqual(rows[0]["status"],"expired")
    def test_conditional_indoor(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        rows=m.issue([],now,"ref",[],{"baseline":[{"datetime":now.isoformat(),"end_c":21}]},20)
        m.observe(rows,now+timedelta(hours=1),"ref",19,5)
        result=m.summarize(rows,"ref")["indoor_scenario"]
        self.assertTrue(result["conditional"])
        self.assertEqual(result["mae_c"],2)
        self.assertEqual(result["baseline_mae_c"],1)

    def test_pv_completed_hour_and_reference(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        start=now+timedelta(hours=1)
        end=start+timedelta(hours=1)
        rows=m.issue([],now,"ref",[],{},20,[{"datetime":start.isoformat(),"pv_kwh":1.2}],"pv")
        m.observe(rows,end,"ref",20,7)
        self.assertEqual(rows[0]["status"],"pending")
        m.observe_pv(rows,end,"pv",{end.isoformat():1.0})
        result=m.summarize(rows,"ref","pv")["pv_hour"]
        self.assertEqual(result["unit"],"kWh")
        self.assertAlmostEqual(result["mae"],.2)
        self.assertEqual(result["lead_hours"]["0-6"]["samples"],1)

    def test_pv_source_identity_rejects_duplicate_meters(self):
        source={"stat_energy_from":"sensor.pv","config_entry_solar_forecast":["provider"]}
        self.assertEqual(m.pv_identity({"solar":[source,source]}),(None,[]))
        self.assertEqual(m.pv_identity({"solar":[source]})[1],["sensor.pv"])

    def test_pv_missing_actual_not_zero(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        start=now+timedelta(hours=1)
        rows=m.issue([],now,"ref",[],{},20,[{"datetime":start.isoformat(),"pv_kwh":1}],"pv")
        m.observe_pv(rows,now+timedelta(hours=9),"pv",{})
        self.assertEqual(rows[0]["status"],"expired")
        self.assertEqual(m.summarize(rows,"ref","pv")["pv_hour"]["samples"],0)

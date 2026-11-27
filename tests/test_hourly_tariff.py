import importlib
import sys
import types
import unittest
from pathlib import Path
pkg=types.ModuleType("hourly_tariff_tests")
pkg.__path__=[str(Path(__file__).parents[1]/"custom_components/smart_heating_energy_manager")]
sys.modules[pkg.__name__]=pkg
m=importlib.import_module(pkg.__name__+".hourly_tariff")
joint=importlib.import_module(pkg.__name__+".joint_plan")

class HourlyTariffTests(unittest.TestCase):
    def test_conversion_and_components(self):
        attrs={"unit_of_measurement":"EUR/MWh","raw_today":[{"start":"2026-11-27T12:00:00+01:00","end":"2026-11-27T13:00:00+01:00","value":100}]}
        p=m.marginal_forecast(attrs,{"use_index":True,"spread":.02})
        self.assertAlmostEqual(p["2026-11-27T11:00:00+00:00"],.12)
        self.assertEqual(m.marginal_forecast(attrs,{"use_index":False}),{})
    def test_dst_and_invalid(self):
        a={"unit_of_measurement":"€/kWh","prices":{"2026-10-25T02:00:00+02:00":.1,"2026-10-25T02:00:00+01:00":.2,"2026-10-25T03:00:00":.3}}
        self.assertEqual(len(m.parse_prices(a)),2)
        self.assertEqual(m.parse_prices({"unit_of_measurement":"W","prices":a["prices"]}),{})
    def test_direct_attributes(self):
        from datetime import datetime, timezone
        a={"unit_of_measurement":"€/kWh",datetime(2026,1,1,10,tzinfo=timezone.utc):.2,"2026-01-01 11:00:00+00:00":.3,"2026-01-01 12:00:00+00:00":None}
        self.assertEqual(m.parse_prices(a),{"2026-01-01T10:00:00+00:00":.2,"2026-01-01T11:00:00+00:00":.3})
    def test_fallback(self):
        self.assertEqual(m.price_at("2026-11-27T12:00:00+01:00",{},.3,"index"),(.3,"current_index_assumed"))
    def test_joint_price_changes_window(self):
        h=[];s=[]
        for hour,price in [(9,.4),(10,.1),(11,.3)]:
            t=f"2026-11-27T{hour:02}:00:00+00:00"
            h.append({"datetime":t,"heat_kw":0,"electricity_kwh":0,"fuel_cost":0,"electricity_price":price})
            s.append({"datetime":t,"pv_kwh":0})
        result=joint.optimize(h,s,0,.3,{"entity":"switch.boiler","below_minimum":False,"ideal_heat_kwh":1,"rated_kw":1},export_price=0)
        self.assertEqual(result["dhw_start"],"2026-11-27T10:00:00+00:00")
        self.assertAlmostEqual(result["net_cost"],.1)

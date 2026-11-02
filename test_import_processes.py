import io
import json
import math
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from weather_import import read_table,guess_columns,normalize_weather
from processes import amc2_cn,help_lateral_rate,giroud_contact_rate,modified_penman_pet
from help_mvp import simulate,load_weather


class ImportTests(unittest.TestCase):
    def test_rain_only_requires_explicit_missing_weather(self):
        raw,_=read_table(b'date,precip_mm\n2024-01-01,5\n2024-01-02,0\n','rain.csv')
        mapping=guess_columns(raw[0])
        with self.assertRaises(ValueError): normalize_weather(raw,mapping)
        out=normalize_weather(raw,mapping,constant_temp_c=-5,constant_pet_mm=.3)
        self.assertEqual([r['precip_mm'] for r in out],[5.,0.])
        self.assertTrue(all(r['temp_c']==-5 and r['pet_mm']==.3 for r in out))

    def test_french_dates_comma_decimals_and_unit_conversion(self):
        raw,_=read_table('jour;pluie\n01/02/2024;0,5\n02/02/2024;1,2\n'.encode(),'rain.csv')
        out=normalize_weather(raw,guess_columns(raw[0]),date_format='%d/%m/%Y',precip_unit='cm',constant_temp_c=10,constant_pet_mm=0)
        self.assertEqual(out[0]['date'],'2024-02-01')
        self.assertEqual(sum(r['precip_mm'] for r in out),17.)

    def test_excel_dates_sheet_selection(self):
        try: import openpyxl
        except ImportError: self.skipTest('openpyxl not installed')
        b=openpyxl.Workbook(); b.active.title='Other'
        s=b.create_sheet('Rainfall'); s.append(['日期','降水量']); s.append([datetime(2024,1,1),10]);s.append([datetime(2024,1,2),3])
        payload=io.BytesIO();b.save(payload)
        raw,names=read_table(payload.getvalue(),'test.xlsx',sheet='Rainfall')
        self.assertEqual(names,['Other','Rainfall'])
        out=normalize_weather(raw,guess_columns(raw[0]),constant_temp_c=15,constant_pet_mm=2)
        self.assertEqual(out[0]['date'],'2024-01-01');self.assertEqual(out[1]['precip_mm'],3.)

    def test_missing_duplicate_dates_and_negative_values_rejected(self):
        for text in ['date,precip_mm\n2024-01-01,-1\n','date,precip_mm\n2024-01-01,1\n2024-01-03,2\n',
                     'date,precip_mm\n2024-01-01,1\n2024-01-01,2\n','date,precip_mm\n2024-01-01,NaN\n']:
            raw,_=read_table(text.encode(),'rain.csv')
            with self.assertRaises(ValueError): normalize_weather(raw,guess_columns(raw[0]),constant_temp_c=15,constant_pet_mm=2)

    def test_energy_forcing_preserved_and_rh_range(self):
        raw=[dict(date='2024-06-01',precip_mm=5,temp_c=20,solar_mj_m2_day=15,rh_percent=60,wind_m_s=2)]
        out=normalize_weather(raw,guess_columns(raw[0]),constant_pet_mm=0,energy=True)
        self.assertEqual(out[0]['solar_mj_m2_day'],15)
        raw[0]['rh_percent']=101
        with self.assertRaises(ValueError): normalize_weather(raw,guess_columns(raw[0]),constant_pet_mm=0,energy=True)


class ProcessTests(unittest.TestCase):
    def test_cn_regression_reference_geometry(self):
        self.assertAlmostEqual(amc2_cn('help_vegetation',78,.04,152.4,'good',.1),80.87,places=8)
        self.assertAlmostEqual(amc2_cn('help_slope',78,.04,152.4),78,places=8)
        self.assertGreater(amc2_cn('help_slope',78,.1,152.4),78)

    def test_steady_drainage_limits_continuity_and_monotonicity(self):
        self.assertEqual(help_lateral_rate(0,40000,.03,30),0)
        self.assertAlmostEqual(help_lateral_rate(100,40000,0,30),40000*(4*(100/30000)/math.pi)**2)
        critical=.2*.03*30000
        low=help_lateral_rate(critical*(1-1e-7),40000,.03,30)
        high=help_lateral_rate(critical*(1+1e-7),40000,.03,30)
        self.assertLess(abs(high-low)/max(high,low),1e-5)
        q=[help_lateral_rate(h,40000,.03,30) for h in [1,10,100,200,500]]
        self.assertEqual(q,sorted(q))

    def test_membrane_defects_and_contact_sensitivity(self):
        args=(300,.02,600)
        zero=giroud_contact_rate(*args,'giroud_good',0,.784,0,100)
        good=giroud_contact_rate(*args,'giroud_good',2.5,.784,2.5,100)
        poor=giroud_contact_rate(*args,'giroud_poor',2.5,.784,2.5,100)
        self.assertEqual(zero,0);self.assertGreater(good,0);self.assertGreater(poor,good)
        self.assertAlmostEqual(giroud_contact_rate(*args,'giroud_good',5,.784,5,100),good*2)
        self.assertLessEqual(poor,.02*(1+300/600))

    def test_modified_penman_physical_bounds_and_wet_day_convention(self):
        self.assertEqual(modified_penman_pet('2024-06-01',20,0,100,2,45),0.)
        dry=modified_penman_pet('2024-06-01',20,15,40,2,45)
        humid=modified_penman_pet('2024-06-01',20,15,100,2,45)
        wet=modified_penman_pet('2024-06-01',20,15,40,2,45,precip_mm=10)
        self.assertGreater(dry,humid);self.assertAlmostEqual(wet,humid)
        self.assertLess(dry,15.)

    def test_advanced_two_year_mass_balance(self):
        config=json.loads((ROOT/'examples/advanced_methods.json').read_text(encoding='utf-8'))
        result=simulate(config,load_weather(ROOT/'examples/weather_energy_synthetic.csv'))
        self.assertLess(result['summary']['maximum_absolute_daily_balance_error_mm'],1e-8)
        self.assertLess(result['summary']['maximum_absolute_layer_balance_error_mm'],1e-8)
        self.assertTrue(any(r['lai']>0 for r in result['daily']))
        self.assertTrue(any(r['soil_evaporation_mm']>0 for r in result['daily']))
        self.assertTrue(any(r['transpiration_mm']>0 for r in result['daily']))
        self.assertTrue(any(r['effective_cn']!=config['curve_number'] for r in result['daily']))
        for row in result['daily']:
            self.assertLessEqual(row['et_mm'],row['pet_mm']+1e-9)


if __name__=='__main__': unittest.main()

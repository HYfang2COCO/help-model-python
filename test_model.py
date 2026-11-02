import copy
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from help_mvp import (HelpMVP, default_layer, generate_synthetic_weather, migrate_config,
                      run, simulate, validate_config, validate_weather,load_weather)

ROOT = Path(__file__).resolve().parents[1]


def cfg(*kinds, **kwargs):
    return dict(schema_version=2,layers=[default_layer(k,f'l{i}') for i,k in enumerate(kinds)],**kwargs)


def forcing(n=100, precip=100., pet=0.):
    return [dict(date=(date(2024,1,1)+timedelta(days=i)).isoformat(),precip_mm=precip,temp_c=15.,pet_mm=pet) for i in range(n)]


class RoutingTests(unittest.TestCase):
    def assertBalanced(self,result):
        self.assertLess(result['summary']['maximum_absolute_daily_balance_error_mm'],1e-8)
        self.assertLess(result['summary']['maximum_absolute_layer_balance_error_mm'],1e-8)
        self.assertLess(abs(result['summary']['cumulative_balance_error_mm']),1e-7)
        layers = {l['id']:l for l in result['config']['layers']}
        for r in result['layers']:
            l = layers[r['layer_id']]
            self.assertGreaterEqual(r['storage_mm'],-1e-9)
            self.assertLessEqual(r['storage_mm'],l.get('porosity',0)*l['thickness_mm']+1e-9)
            for k in ('inflow_mm','vertical_out_mm','lateral_gross_mm','et_mm'):
                self.assertGreaterEqual(r[k],-1e-9)
        for r in result['daily']:
            self.assertLessEqual(r['et_mm'],r['pet_mm']+1e-9)
            self.assertAlmostEqual(r['rain_mm']+r['snowmelt_mm'],r['direct_runoff_mm']+r['saturation_runoff_mm']+r['infiltration_mm'],places=8)

    def test_all_examples_two_years(self):
        for f in ROOT.glob('examples/*.json'):
            if f.name in ('legacy_config.json','config.schema.json'):
                continue
            with self.subTest(f=f.name):
                c=json.loads(f.read_text(encoding='utf-8'))
                w=load_weather(ROOT/'examples/weather_energy_synthetic.csv') if c.get('pet_method')=='modified_penman' else generate_synthetic_weather(2024,2)
                r = simulate(c,w)
                self.assertBalanced(r)
                self.assertTrue(any(d['snowfall_mm']>0 for d in r['daily']))
                self.assertTrue(any(d['snowmelt_mm']>0 for d in r['daily']))

    def test_impermeable_membrane_blocks_and_no_teleport(self):
        c = cfg('soil','geomembrane','waste',root_depth_mm=0)
        c['layers'][1]['leakage_multiplier'] = 0
        c['layers'][2]['initial_theta'] = c['layers'][2]['field_capacity']
        r = simulate(c,forcing(20))
        self.assertBalanced(r)
        self.assertTrue(all(x['vertical_out_mm']==0 for x in r['layers'] if x['layer_id']=='l1'))
        self.assertEqual(r['summary']['bottom_leakage_mm'],0)
        self.assertTrue(all(x['inflow_mm']==0 for x in r['layers'] if x['layer_id']=='l2'))

    def test_multiple_independent_drains(self):
        c = cfg('drainage','barrier','drainage','geomembrane',root_depth_mm=0)
        for d in c['layers']:
            if d['kind']=='drainage':
                d.update(initial_theta=d['porosity'], lateral_ksat_mm_day=1e6)
        r = simulate(c,forcing(3,0))
        self.assertBalanced(r)
        for ident in ('l0','l2'):
            self.assertGreater(sum(x['collected_mm'] for x in r['layers'] if x['layer_id']==ident),0)
        self.assertAlmostEqual(sum(x['collected_mm'] for x in r['layers']),r['summary']['leachate_collected_mm'])

    def test_analytic_single_layer_darcy(self):
        c = cfg('barrier',substeps_per_day=1,root_depth_mm=0)
        l = c['layers'][0]
        l.update(thickness_mm=100,porosity=.5,field_capacity=.2,wilting_point=.1,initial_theta=.4,ksat_mm_day=2.)
        r = simulate(c,forcing(1,0))
        # wet=20mm, drainable pore fraction=.3, h=66.6667mm
        self.assertAlmostEqual(r['summary']['bottom_leakage_mm'],2*(1+(20/.3)/100))
        self.assertBalanced(r)

    def test_competing_fluxes_cannot_double_spend(self):
        c = cfg('drainage',substeps_per_day=1,root_depth_mm=0)
        l = c['layers'][0]
        l.update(initial_theta=l['porosity'],ksat_mm_day=1e9,lateral_ksat_mm_day=1e12)
        wet = (l['initial_theta']-l['field_capacity'])*l['thickness_mm']
        r = simulate(c,forcing(1,0))
        self.assertAlmostEqual(r['summary']['bottom_leakage_mm']+r['summary']['leachate_collected_mm'],wet)
        self.assertBalanced(r)

    def test_recirculation_delay_and_rejected_overflow(self):
        c = cfg('soil','drainage',recirculation_fraction=1.,recirculation_target_id='l0',root_depth_mm=0)
        c['layers'][0].update(initial_theta=.46,ksat_mm_day=0.)
        c['layers'][1].update(initial_theta=.38,lateral_ksat_mm_day=1e8)
        r = simulate(c,forcing(3,0))
        self.assertBalanced(r)
        self.assertEqual(r['daily'][0]['recirculated_today_mm'],0)
        self.assertGreater(r['daily'][0]['recirculated_next_day_mm'],0)
        self.assertAlmostEqual(r['daily'][1]['recirculation_surface_runoff_mm'],r['daily'][0]['recirculated_next_day_mm'])
        self.assertEqual(r['summary']['leachate_collected_mm'],0.)

    def test_reorder_changes_flow_and_keeps_target_id(self):
        c = cfg('drainage','geomembrane','waste',root_depth_mm=0,recirculation_target_id='l2')
        c['layers'][1]['leakage_multiplier'] = 0.
        c['layers'][0]['initial_theta'] = c['layers'][0]['field_capacity']
        c['layers'][2]['initial_theta'] = c['layers'][2]['field_capacity']
        first = simulate(c,forcing(20))
        c['layers'][0],c['layers'][2] = c['layers'][2],c['layers'][0]
        second = simulate(c,forcing(20))
        self.assertEqual(second['config']['recirculation_target_id'],'l2')
        self.assertGreater(first['summary']['leachate_collected_mm'],second['summary']['leachate_collected_mm'])

    def test_top_membrane_and_consecutive_membranes(self):
        c = cfg('geomembrane','geomembrane','soil')
        c['layers'][0]['leakage_multiplier'] = 0.
        r = simulate(c,forcing(10))
        self.assertEqual(sum(x['infiltration_mm'] for x in r['daily']),0)
        self.assertBalanced(r)

    def test_empty_dry_profile_and_extreme_pet(self):
        c = cfg('soil','barrier')
        for l in c['layers']:
            l['initial_theta'] = 0.
        r = simulate(c,forcing(10,0,1e4))
        self.assertEqual(r['summary']['evapotranspiration_mm'],0.)
        self.assertBalanced(r)

    def test_randomized_profiles_storms_snow_recirculation(self):
        rng = random.Random(42)
        kinds = ['soil','waste','drainage','barrier','geomembrane']
        for trial in range(25):
            ks = ['soil']+[rng.choice(kinds) for _ in range(rng.randint(0,12))]
            c = cfg(*ks,substeps_per_day=rng.choice([1,4,24]),root_depth_mm=500,
                    recirculation_fraction=rng.choice([0.,.5,1.]),recirculation_target_id='l0')
            for l in c['layers']:
                l['ksat_mm_day'] = 10**rng.uniform(-5,5)
                if l['kind']!='geomembrane':
                    l['initial_theta'] = rng.uniform(0,l['porosity'])
            weather = forcing(60,0)
            for w in weather:
                w.update(precip_mm=rng.choice([0,10,250,1000]),temp_c=rng.uniform(-20,30),pet_mm=rng.uniform(0,10))
            with self.subTest(trial=trial):
                self.assertBalanced(simulate(c,weather))

    def test_migration_of_actual_original(self):
        old = json.loads((ROOT/'examples/legacy_config.json').read_text())
        migrated = validate_config(migrate_config(old))
        self.assertIn('liner',old)  # input not mutated
        self.assertEqual(migrated['layers'][-1]['kind'],'barrier')
        self.assertAlmostEqual(migrated['layers'][-1]['ksat_mm_day'],.002)
        self.assertBalanced(simulate(migrated,generate_synthetic_weather(2024,1)))

    def test_exports_and_period_totals(self):
        with tempfile.TemporaryDirectory() as d:
            summary = run(cfg('soil','drainage'),forcing(50),d)
            for name in ['daily.csv','layers.csv','monthly.csv','annual.csv','config.json','summary.json']:
                self.assertTrue((Path(d)/name).stat().st_size>0)
            result = simulate(cfg('soil','drainage'),forcing(50))
            self.assertAlmostEqual(sum(x['bottom_leakage_mm'] for x in result['monthly']),summary['bottom_leakage_mm'])
            self.assertAlmostEqual(summary['bottom_leakage_m3'],summary['bottom_leakage_mm']*10.)


class ValidationTests(unittest.TestCase):
    def test_huge_integer_rejected_cleanly(self):
        c=cfg('soil')
        c['layers'][0]['thickness_mm']=10**1000
        with self.assertRaises(ValueError):
            validate_config(c)

    def test_cli_with_legacy_windows_encoding(self):
        env=dict(os.environ,PYTHONIOENCODING='cp1252')
        p=subprocess.run([sys.executable,str(ROOT/'help_mvp.py'),'validate','--config',
                          str(ROOT/'examples/composite_liner.json')],capture_output=True,env=env)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('配置通过校验',p.stdout.decode('utf-8'))

    def test_invalid_numbers_and_types(self):
        for key in ('thickness_mm','ksat_mm_day','porosity','field_capacity','wilting_point','initial_theta','brooks_corey_lambda'):
            for value in (math.nan,math.inf,-1,True,'1',None):
                c = cfg('soil')
                c['layers'][0][key] = value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    validate_config(c)
        for value in (1.5,True,0,1441):
            with self.assertRaises(ValueError):
                validate_config(cfg('soil',substeps_per_day=value))

    def test_semantic_validation(self):
        cases=[]
        for key,value in [('porosity',.2),('initial_theta',.9),('kind','clay'),('lateral_ksat_mm_day',1),('id','中文')]:
            c=cfg('soil'); c['layers'][0][key]=value; cases.append(c)
        c=cfg('soil','waste'); c['layers'][1]['id']='l0'; cases.append(c)
        c=cfg('soil'); c['layers']=[]; cases.append(c)
        cases += [cfg('geomembrane'),cfg('soil',recirculation_fraction=.2),
                  cfg('soil','geomembrane',recirculation_target_id='l1'),cfg('soil',curve_number=100)]
        for c in cases:
            with self.subTest(c=c),self.assertRaises(ValueError):
                validate_config(c)

    def test_weather_dates_and_numbers(self):
        for change in ({'precip_mm':-1},{'pet_mm':'NaN'},{'temp_c':'Infinity'},{'date':'bad'}):
            w=forcing(2);w[0].update(change)
            with self.assertRaises(ValueError): validate_weather(w)
        w=forcing(2); w[1]['date']=w[0]['date']
        with self.assertRaises(ValueError): validate_weather(w)
        sim=HelpMVP(cfg('soil')); sim.day(forcing(1)[0])
        initial=sim.storage()
        with self.assertRaises(ValueError): sim.day(forcing(1)[0])
        self.assertEqual(initial,sim.storage())

    def test_examples_match_json_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest('可选依赖 jsonschema 未安装')
        schema=json.loads((ROOT/'examples/config.schema.json').read_text())
        for f in ROOT.glob('examples/*.json'):
            if f.name not in ('legacy_config.json','config.schema.json'):
                jsonschema.validate(json.loads(f.read_text(encoding='utf-8')),schema)


if __name__=='__main__':
    unittest.main()

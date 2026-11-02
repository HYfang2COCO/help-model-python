import sys
import unittest
import copy
import os
from datetime import date
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None


@unittest.skipIf(AppTest is None,'Streamlit 可选依赖未安装')
class UITests(unittest.TestCase):
    def app(self):
        at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        self.assertEqual(len(at.exception),0)
        at.selectbox(key='ui_language').set_value('zh').run()
        return at

    def test_default_english_and_language_order(self):
        with patch.dict(os.environ):
            os.environ.pop('HELP_UI_LANG', None)
            at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        self.assertEqual(at.selectbox(key='ui_language').value,'en')
        self.assertEqual(at.selectbox(key='ui_language').options,['English','Français','中文'])
        self.assertEqual(at.title[0].value,'HELP — Multilayer water balance')

    def test_date_range_aggregation_language_and_new_run_reset(self):
        at=self.app()
        at.button(key='run_model').click().run()
        before=copy.deepcopy(at.session_state['result']['summary'])
        chosen=(date(2024,2,28),date(2024,3,1))
        at.date_input(key='chart_dates_1').set_value(chosen).run()
        at.selectbox(key='chart_step').set_value('month').run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('3 天 · 2 个数据点' in c.value for c in at.caption))
        self.assertEqual(at.session_state['result']['summary'],before)
        at.selectbox(key='ui_language').set_value('fr').run()
        self.assertEqual(at.date_input(key='chart_dates_1').value,chosen)
        self.assertEqual(at.selectbox(key='chart_step').value,'month')
        at.date_input(key='chart_dates_1').set_value((date(2024,2,29),date(2024,2,29))).run()
        self.assertEqual(len(at.exception),0)
        at.text_area(key='weather_paste').set_value('date,precip_mm\n2026-01-01,5\n2026-01-02,0\n').run()
        at.button(key='run_model').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.date_input(key='chart_dates_2').value,(date(2026,1,1),date(2026,1,2)))

    def test_add_reorder_edit_delete_and_run(self):
        at=self.app()
        initial=len(at.session_state['cfg']['layers'])
        at.selectbox(key='add_kind').set_value('drainage')
        at.button(key='add_layer').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.session_state['cfg']['layers']),initial+1)
        ident=at.session_state['cfg']['layers'][-1]['id']
        rev=at.session_state['revision']
        at.selectbox(key=f'selected_{rev}').set_value(ident).run()
        at.button(key='move_-1').click().run()
        self.assertEqual(at.session_state['cfg']['layers'][-2]['id'],ident)
        rev=at.session_state['revision']
        at.selectbox(key=f'selected_{rev}').set_value(ident).run()
        at.number_input(key=f'param_{ident}_thickness_mm_{rev}').set_value(450.)
        next(b for b in at.button if b.label=='保存此层参数').click().run()
        self.assertEqual(next(l for l in at.session_state['cfg']['layers'] if l['id']==ident)['thickness_mm'],450.)
        rev=at.session_state['revision']
        at.selectbox(key=f'selected_{rev}').set_value(ident).run()
        at.button(key='delete_layer').click().run()
        self.assertEqual(len(at.session_state['cfg']['layers']),initial)
        at.button(key='run_model').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.session_state['result']['summary']['days'],731)
        self.assertLess(at.session_state['result']['summary']['maximum_absolute_daily_balance_error_mm'],1e-8)

    def test_inapplicable_fields_and_invalid_range(self):
        at=self.app()
        rev=at.session_state['revision']
        membrane=next(l['id'] for l in at.session_state['cfg']['layers'] if l['kind']=='geomembrane')
        at.selectbox(key=f'selected_{rev}').set_value(membrane).run()
        self.assertFalse(any('porosity' in str(x.key) for x in at.number_input))
        at.number_input(key=f'param_{membrane}_thickness_mm_{rev}').set_value(0.)
        next(b for b in at.button if b.label=='保存此层参数').click().run()
        self.assertTrue(len(at.error)>0)
        self.assertGreater(next(l['thickness_mm'] for l in at.session_state['cfg']['layers'] if l['id']==membrane),0)

    def test_type_switch_and_stale_result_warning(self):
        at=self.app()
        at.button(key='run_model').click().run()
        rev=at.session_state['revision']
        selected=at.session_state['cfg']['layers'][0]['id']
        at.selectbox(key=f'type_{selected}_{rev}').set_value('geomembrane').run()
        at.button(key='change_type').click().run()
        self.assertEqual(len(at.exception),0)
        layer=at.session_state['cfg']['layers'][0]
        self.assertEqual(layer['kind'],'geomembrane')
        self.assertNotIn('porosity',layer)
        self.assertTrue(any('上次运行' in w.value for w in at.warning))

    def test_global_validation_and_save(self):
        at=self.app()
        rev=at.session_state['revision']
        at.number_input(key=f'global_curve_number_{rev}').set_value(100.)
        next(b for b in at.button if b.label=='保存全局设置').click().run()
        self.assertTrue(len(at.error)>0)
        self.assertEqual(at.session_state['cfg']['curve_number'],78.)
        at.number_input(key=f'global_curve_number_{rev}').set_value(85.)
        at.number_input(key=f'nstep_{rev}').set_value(48)
        at.number_input(key=f'global_recirculation_fraction_{rev}').set_value(.3)
        at.selectbox(key=f'rec_target_{rev}').set_value('waste_2')
        next(b for b in at.button if b.label=='保存全局设置').click().run()
        self.assertEqual(at.session_state['cfg']['curve_number'],85.)
        self.assertEqual(at.session_state['cfg']['substeps_per_day'],48)
        at.button(key='run_model').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.session_state['result']['config']['recirculation_fraction'],.3)

    def test_language_switch_preserves_profile_and_results(self):
        at=self.app()
        at.button(key='add_layer').click().run()
        saved=copy.deepcopy(at.session_state['cfg'])
        at.button(key='run_model').click().run()
        summary=copy.deepcopy(at.session_state['result']['summary'])
        for code,title in [('fr','HELP — Bilan hydrique multicouche'),('en','HELP — Multilayer water balance'),('zh','HELP 多层水量模型')]:
            at.selectbox(key='ui_language').set_value(code).run()
            self.assertEqual(len(at.exception),0)
            self.assertEqual(at.title[0].value,title)
            self.assertEqual(at.session_state['cfg'],saved)
            self.assertEqual(at.session_state['result']['summary'],summary)
            self.assertFalse(any('Python 独立近似研究模型' in c.value for c in at.caption))
            self.assertEqual(len(at.warning),0)

    def test_french_and_english_validation_and_run(self):
        for code,error_text in [('fr','doit être'),('en','must be')]:
            at=self.app()
            at.selectbox(key='ui_language').set_value(code).run()
            rev=at.session_state['revision']
            at.number_input(key=f'param_soil_1_thickness_mm_{rev}').set_value(0.)
            next(b for b in at.button if b.label in ('Enregistrer la couche','Save layer parameters')).click().run()
            self.assertTrue(any(error_text in e.value for e in at.error))
            self.assertEqual(len(at.exception),0)
            at.button(key='run_model').click().run()
            self.assertEqual(at.session_state['result']['summary']['days'],731)
            self.assertEqual(len(at.exception),0)

    def test_pasted_rainfall_run_and_changed_forcing_warning(self):
        at=self.app()
        at.text_area(key='weather_paste').set_value('date,precip_mm\n2024-01-01,5\n2024-01-02,0\n2024-01-03,12.5\n').run()
        at.button(key='run_model').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.session_state['result']['summary']['days'],3)
        self.assertAlmostEqual(at.session_state['result']['summary']['precip_mm'],17.5)
        self.assertEqual(at.session_state['result']['input_provenance']['constant_temp_c'],15.)
        at.number_input(key='import_pet').set_value(3.).run()
        self.assertTrue(any('上次运行' in w.value for w in at.warning))

    def test_process_settings_save_and_penman_run(self):
        at=self.app();rev=at.session_state['revision']
        at.selectbox(key=f'process_pet_method_{rev}').set_value('modified_penman')
        at.selectbox(key=f'process_lateral_method_{rev}').set_value('help_steady')
        next(b for b in at.button if b.label=='保存计算方法').click().run()
        at.button(key='run_model').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.session_state['result']['config']['pet_method'],'modified_penman')


if __name__=='__main__':
    unittest.main()

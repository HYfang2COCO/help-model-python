"""HTTP-level checks for the packaged web interface and solver integration."""
import io
import json
import sys
import threading
import unittest
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from help_mvp import simulate
from web_server import LocalServer


class WebServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(('127.0.0.1', 0))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.config = json.loads((ROOT/'examples/composite_liner.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, payload=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        data = json.dumps(payload).encode() if payload is not None else None
        return urlopen(Request(self.url+path, data=data, headers=headers), timeout=30)

    def forcing(self):
        return dict(text='date,rain\n2026-01-01,5\n2026-01-02,0\n2026-01-03,12.5\n',
                    mapping={'date':'date','precip_mm':'rain'}, source='unit test',
                    options={'constant_temp_c':15,'constant_pet_mm':2,'precip_unit':'mm'})

    def test_root_and_all_packaged_assets(self):
        for path in ('/', '/web/app.js', '/web/time-series.js', '/web/data.js', '/web/style.css', '/web/icon.svg',
                     '/examples/rainfall_template.csv', '/docs/V22_METHODS.md'):
            with self.subTest(path=path), self.request(path) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 0)
        with self.request('/api/health') as response:
            self.assertEqual(json.load(response)['interface'], 'web')

    def test_same_python_results_and_complete_download(self):
        payload = dict(self.forcing(), config=self.config)
        with self.request('/api/run', payload) as response:
            result = json.load(response)
        weather = [dict(date=f'2026-01-0{i}', precip_mm=p,temp_c=15.,pet_mm=2.) for i,p in enumerate((5.,0.,12.5),1)]
        direct = simulate(self.config, weather)
        self.assertEqual(result['summary'], direct['summary'])
        self.assertEqual(result['daily'], direct['daily'])
        with self.request(result['download_url']) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), {'config.json','summary.json','input_provenance.json',
                    'weather.csv','daily.csv','layers.csv','monthly.csv','annual.csv'})
                self.assertEqual(json.loads(archive.read('input_provenance.json'))['source'], 'unit test')

    def test_bad_weather_and_bad_config_do_not_run(self):
        bad = self.forcing()
        bad['text'] = 'date,rain\n2026-01-01,5\n2026-01-03,2\n'
        for path,payload in [('/api/normalize',bad),('/api/validate',{'config':{'schema_version':2,'layers':[]}}),
                             ('/api/validate',{'config':[]})]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                self.request(path,payload)
            self.assertEqual(caught.exception.code,400)
            self.assertTrue(json.loads(caught.exception.read())['error'])

    def test_french_units_dates_and_explicit_constants(self):
        payload=dict(text='jour;pluie\n01/02/2026;1,2\n02/02/2026;0,3\n',mapping={'date':'jour','precip_mm':'pluie'},
                     options={'date_format':'%d/%m/%Y','precip_unit':'cm','constant_temp_c':10,'constant_pet_mm':1},lang='fr')
        with self.request('/api/normalize',payload) as response:
            weather=json.load(response)['weather']
        self.assertEqual([w['precip_mm'] for w in weather],[12.,3.])
        self.assertEqual(weather[0]['date'],'2026-02-01')
        del payload['options']['constant_temp_c']
        with self.assertRaises(HTTPError) as caught:
            self.request('/api/normalize',payload)
        self.assertEqual(caught.exception.code,400)

    def test_advanced_penman_run_uses_radiation_and_balances(self):
        config=json.loads((ROOT/'examples/advanced_methods.json').read_text(encoding='utf-8'))
        text='\n'.join((ROOT/'examples/weather_energy_synthetic.csv').read_text(encoding='utf-8-sig').splitlines()[:15])
        from weather_import import guess_columns
        payload=dict(config=config,text=text,mapping=guess_columns(text.splitlines()[0].split(',')),
                     options={'energy':True,'constant_pet_mm':0})
        with self.request('/api/run',payload) as response:
            result=json.load(response)
        self.assertEqual(result['summary']['days'],14)
        self.assertGreater(result['daily'][0]['pet_mm'],0)
        self.assertLess(result['summary']['maximum_absolute_daily_balance_error_mm'],1e-7)

    def test_static_boundaries_and_cross_origin_requests(self):
        for path in ('/web/../../web_server.py','/help_mvp.py','/web/%2e%2e/%2e%2e/README.md'):
            with self.subTest(path=path),self.assertRaises(HTTPError) as caught:
                self.request(path)
            self.assertEqual(caught.exception.code,404)
        with self.assertRaises(HTTPError) as caught:
            self.request('/api/validate',{'config':self.config},origin='https://example.com')
        self.assertEqual(caught.exception.code,403)


if __name__ == '__main__':
    unittest.main()

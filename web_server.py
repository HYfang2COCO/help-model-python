"""Local HTML interface and the existing HELP-inspired Python solver. Standard library only."""
from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import secrets
import threading
import webbrowser
import zipfile
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from help_mvp import VERSION, migrate_config, profile_warnings, simulate, validate_config
from i18n import localize_error, translate
from weather_import import normalize_weather, read_table

ROOT = Path(__file__).resolve().parent


def result_archive(result):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for key in ('config', 'summary', 'input_provenance'):
            archive.writestr(f'{key}.json', json.dumps(result[key], ensure_ascii=False, indent=2))
        for key in ('weather', 'daily', 'layers', 'monthly', 'annual'):
            stream = io.StringIO(newline='')
            rows = result[key]
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            archive.writestr(f'{key}.csv', stream.getvalue().encode('utf-8-sig'))
    return output.getvalue()


def normalize_request(payload):
    text = payload.get('text')
    if not isinstance(text, str):
        raise ValueError('Weather text is required')
    rows, _ = read_table(text.encode('utf-8-sig'), 'weather.csv')
    options = payload.get('options', {})
    if not isinstance(options, dict):
        raise ValueError('Invalid import options')
    allowed = {'date_format', 'precip_unit', 'constant_temp_c', 'constant_pet_mm', 'energy'}
    if set(options) - allowed:
        raise ValueError('Unknown import option')
    weather = normalize_weather(rows, payload.get('mapping', {}), **options)
    provenance = dict(source=payload.get('source', 'web input'), mapping=payload.get('mapping'), **options)
    return weather, provenance


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.downloads = OrderedDict()
        self.download_lock = threading.Lock()
        self.run_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = 'HELP-Local/2.3'

    def send_bytes(self, data, content_type, status=200, attachment=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if attachment:
            self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload, status=200):
        self.send_bytes(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8', status)

    def allowed_request(self):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.headers.get('Host') not in hosts:
            self.send_json({'error': 'Use the local application URL'}, 403)
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{h}' for h in hosts}:
            self.send_json({'error': 'Open the interface from the local server'}, 403)
            return False
        return True

    def do_GET(self):
        if not self.allowed_request():
            return
        path = unquote(urlsplit(self.path).path)
        if path == '/api/health':
            return self.send_json({'status': 'ready', 'version': VERSION, 'interface': 'web'})
        if path.startswith('/api/download/'):
            token = path.removeprefix('/api/download/')
            with self.server.download_lock:
                data = self.server.downloads.get(token)
            if data is None:
                return self.send_json({'error': 'Result expired; run the model again'}, 404)
            return self.send_bytes(data, 'application/zip', attachment='HELP_results.zip')
        relative = path.lstrip('/') or 'index.html'
        file = (ROOT / relative).resolve()
        allowed = relative in {'index.html', 'README.md', 'README_en.md', 'README_fr.md'} or relative.startswith(('web/', 'docs/', 'examples/', 'sample_outputs/'))
        if not allowed or not file.is_relative_to(ROOT) or not file.is_file():
            return self.send_json({'error': 'File not found'}, 404)
        content_type = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        if file.suffix == '.js':
            content_type = 'text/javascript'
        if content_type.startswith('text/'):
            content_type += '; charset=utf-8'
        self.send_bytes(file.read_bytes(), content_type)

    def do_POST(self):
        if not self.allowed_request():
            return
        payload = {}
        try:
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.send_json({'error': 'Use application/json'}, 415)
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16_000_000:
                return self.send_json({'error': 'Request must be 1 byte to 16 MB'}, 413)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Request must be a JSON object')
            path = urlsplit(self.path).path
            if path == '/api/validate':
                raw = payload['config']
                if not isinstance(raw, dict):
                    raise ValueError('Configuration must be an object')
                config = validate_config(migrate_config(raw) if raw.get('schema_version') != 2 else raw)
                return self.send_json({'config': config, 'warnings': [translate(w, payload.get('lang', 'zh')) for w in profile_warnings(config)]})
            if path == '/api/normalize':
                weather, provenance = normalize_request(payload)
                return self.send_json({'weather': weather, 'provenance': provenance})
            if path == '/api/run':
                weather, provenance = normalize_request(payload)
                config = validate_config(payload['config'])
                if not self.server.run_lock.acquire(blocking=False):
                    return self.send_json({'error': 'Another simulation is running; try again shortly'}, 409)
                try:
                    result = simulate(config, weather)
                    result['input_provenance'] = provenance
                    archive = result_archive(result)
                    token = secrets.token_urlsafe(24)
                    with self.server.download_lock:
                        self.server.downloads[token] = archive
                        while len(self.server.downloads) > 4:
                            self.server.downloads.popitem(last=False)
                    return self.send_json(dict(summary=result['summary'], daily=result['daily'],
                                               monthly=result['monthly'], annual=result['annual'],
                                               download_url=f'/api/download/{token}'))
                finally:
                    self.server.run_lock.release()
            self.send_json({'error': 'Unknown endpoint'}, 404)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            lang = payload.get('lang', 'zh') if isinstance(payload, dict) else 'zh'
            self.send_json({'error': localize_error(error, lang)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='Open the web interface in your browser')
    args = parser.parse_args()
    server = None
    for port in range(args.port, args.port + 20):
        try:
            server = LocalServer(('127.0.0.1', port))
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit('No available local port; choose another --port')
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'HELP web interface: {url}\nKeep this window open. Press Ctrl+C to stop.', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

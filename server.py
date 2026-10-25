#!/usr/bin/env python3
"""PixelForge local photo editor server. Uses only Python's standard library."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import mimetypes, os, re, json

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
INPUTS = DATA / 'inputs'
OUTPUTS = DATA / 'outputs'
INPUTS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 100 * 1024 * 1024


def safe_name(raw, fallback='image'):
    name = Path(unquote(raw or fallback)).name
    name = re.sub(r'[^A-Za-z0-9._ ()-]+', '_', name).strip(' .')
    return (name or fallback)[:160]

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/files':
            payload = {
                'inputs': sorted([p.name for p in INPUTS.iterdir() if p.is_file()], reverse=True),
                'outputs': sorted([p.name for p in OUTPUTS.iterdir() if p.is_file()], reverse=True),
            }
            data = json.dumps(payload).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data); return
        if parsed.path.startswith('/saved/inputs/') or parsed.path.startswith('/saved/outputs/'):
            kind, raw = parsed.path.split('/')[2], parsed.path.split('/')[3]
            base = INPUTS if kind == 'inputs' else OUTPUTS
            target = (base / safe_name(raw)).resolve()
            if target.parent != base.resolve() or not target.is_file():
                self.send_error(404); return
            data = target.read_bytes()
            self.send_response(200); self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data); return
        if parsed.path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ('/api/inputs', '/api/outputs'):
            self.send_error(404); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self.send_error(400, 'Invalid Content-Length'); return
        if length <= 0 or length > MAX_UPLOAD:
            self.send_error(413 if length > MAX_UPLOAD else 400, 'Upload must be between 1 byte and 100 MB'); return
        name = safe_name(parse_qs(parsed.query).get('filename', ['image'])[0])
        if not Path(name).suffix:
            content_type = self.headers.get('Content-Type', '')
            name += mimetypes.guess_extension(content_type) or '.bin'
        folder = INPUTS if parsed.path.endswith('/inputs') else OUTPUTS
        target = folder / name
        # Avoid overwriting a different image with the same filename.
        if target.exists():
            stem, suffix = target.stem, target.suffix
            i = 2
            while (folder / f'{stem}_{i}{suffix}').exists(): i += 1
            target = folder / f'{stem}_{i}{suffix}'
        remaining = length
        with target.open('wb') as f:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk: break
                f.write(chunk); remaining -= len(chunk)
        if remaining:
            target.unlink(missing_ok=True); self.send_error(400, 'Incomplete upload'); return
        body = json.dumps({'ok': True, 'filename': target.name, 'path': str(target.relative_to(ROOT))}).encode()
        self.send_response(201); self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Keep the console compact: log only server errors.
        if args and str(args[1:2]).startswith("('4"):
            super().log_message(fmt, *args)

if __name__ == '__main__':
    host, port = '127.0.0.1', 8000
    server = ThreadingHTTPServer((host, port), Handler)
    print(f'PixelForge Photo Editor running at http://{host}:{port}')
    print('Uploaded originals: data/inputs | Exported images: data/outputs')
    print('Press Ctrl+C to stop the server.')
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nServer stopped.')
    finally: server.server_close()

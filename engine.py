"""Linewatch's loopback-only app service and packaged monitor entry point."""
import argparse
from contextlib import contextmanager
import copy
import fcntl
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
from urllib.parse import parse_qs, urlparse

os.umask(0o077)
os.environ.setdefault('INTERNET_MONITOR_HOME', str(Path.home() / 'Library/Application Support/Linewatch'))
import monitor as m
import mail_templates
from keychain_store import store_password

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets'
DEFAULT = ASSETS.parent / 'config.example.json'
RUNNER = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve())]
m.RUNNER = RUNNER


def initialise():
    m.ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not (m.ROOT / 'config.json').exists():
        shutil.copyfile(DEFAULT, m.ROOT / 'config.json')
    (m.ROOT / 'logs').mkdir(exist_ok=True)


@contextmanager
def locked():
    with (m.ROOT / '.monitor.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('A speed test is running. Wait for it to finish before changing settings.')
        yield


def running():
    with (m.ROOT / '.monitor.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True


def schedule_enabled():
    result = subprocess.run(['/bin/launchctl', 'print', f'gui/{os.getuid()}/{m.LABEL}'], capture_output=True, timeout=10)
    return result.returncode == 0


def state():
    c = m.config()
    c.setdefault('profile', {})
    c.setdefault('templates', {'subject': mail_templates.SUBJECT, 'body': mail_templates.BODY})
    with m.database() as db:
        rows = m.rows_since(db, c['report_days'] * 24)
        recent = m.rows_since(db, c['average_hours'])
        last_sent = db.execute("SELECT value FROM state WHERE key='last_email_utc'").fetchone()
    return {'config': c, 'measurements': rows[-2000:], 'average_mbps': m.average(recent),
            'sample_count': sum(r['status'] == 'ok' for r in recent),
            'draft': mail_templates.draft(c, recent), 'busy': running(),
            'schedule_enabled': schedule_enabled(), 'last_email_utc': last_sent[0] if last_sent else None,
            'data_directory': str(m.ROOT), 'version': '1.0.0'}


def save_settings(payload):
    with locked():
        c = m.config()
        for key in ('plan_mbps', 'threshold_mbps', 'hours', 'average_hours', 'minimum_samples', 'report_days', 'interface', 'connection_notes'):
            if key in payload:
                c[key] = payload[key]
        c['profile'] = {k: str(payload.get('profile', {}).get(k, ''))[:2000] for k in ('provider', 'provider_email', 'customer_name', 'account_reference', 'user_email')}
        c['templates'] = {k: str(payload.get('templates', {}).get(k, default))[:20000] for k, default in (('subject', mail_templates.SUBJECT), ('body', mail_templates.BODY))}
        for key in ('enabled', 'host', 'port', 'security', 'username', 'from', 'to', 'cooldown_hours', 'use_complaint_template'):
            if key in payload.get('email', {}):
                c['email'][key] = payload['email'][key]
        m.validate_config(c)
        temporary = m.ROOT / 'config.json.tmp'
        temporary.write_text(json.dumps(c, indent=2))
        temporary.replace(m.ROOT / 'config.json')
        if schedule_enabled():
            m.schedule(c)
        with m.database() as db:
            m.report(db, c)
    return {'message': 'Settings saved'}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Session tokens and configuration never enter request logs.

    def reply(self, status, body, content_type='application/json', headers=None):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Referrer-Policy', 'no-referrer')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def authorised(self):
        if self.headers.get('Host') != self.server.host:
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:
            return False
        return secrets.compare_digest(cookie.get('linewatch').value if cookie.get('linewatch') else '', self.server.token)

    def do_GET(self):
        path = urlparse(self.path)
        if self.headers.get('Host') != self.server.host:
            return self.reply(403, {'error': 'Invalid host'})
        token = parse_qs(path.query).get('token', [''])[0]
        if path.path == '/' and token and secrets.compare_digest(token, self.server.token):
            return self.reply(303, '', headers={'Location': '/', 'Set-Cookie': f'linewatch={self.server.token}; HttpOnly; SameSite=Strict; Path=/'})
        if not self.authorised():
            return self.reply(403, {'error': 'Open Linewatch from the app to start a session'})
        try:
            if path.path == '/api/state':
                return self.reply(200, state())
            allowed = {'/': ASSETS / 'index.html', '/app.js': ASSETS / 'app.js', '/style.css': ASSETS / 'style.css'}
            if path.path.startswith('/fonts/') and Path(path.path).name in ('Inter.ttf', 'JetBrainsMono.ttf'):
                allowed[path.path] = ASSETS / 'fonts' / Path(path.path).name
            file = allowed.get(path.path)
            if not file:
                return self.reply(404, {'error': 'Not found'})
            return self.reply(200, file.read_bytes(), mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        except Exception:
            return self.reply(500, {'error': 'Could not load app data. Check your local configuration and logs.'})

    def do_POST(self):
        if not self.authorised() or self.headers.get('X-Linewatch') != '1' or self.headers.get('Origin', f'http://{self.server.host}') != f'http://{self.server.host}':
            return self.reply(403, {'error': 'Invalid app session'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 100000:
                return self.reply(413, {'error': 'Request too large'})
            payload = json.loads(self.rfile.read(size) or '{}')
            if not isinstance(payload, dict):
                raise ValueError('Expected a settings object')
            path = urlparse(self.path).path
            if path == '/api/settings':
                return self.reply(200, save_settings(payload))
            if path == '/api/password':
                c = m.config()
                store_password(c['email']['keychain_service'], c['email']['username'], payload.get('password', ''))
                return self.reply(200, {'message': 'App password saved in macOS Keychain'})
            if path == '/api/schedule':
                with locked():
                    result = m.schedule(m.config(), remove=not payload.get('enabled'))
                return self.reply(200, {'message': result})
            if path == '/api/test':
                if running():
                    raise ValueError('A test is already running')
                with (m.ROOT / 'logs/monitor.log').open('a') as out, (m.ROOT / 'logs/error.log').open('a') as err:
                    subprocess.Popen(RUNNER + ['run'], stdout=out, stderr=err, start_new_session=True)
                return self.reply(200, {'message': 'Speed test started. Results will appear here when it finishes.'})
            if path in ('/api/report', '/api/reveal'):
                with locked(), m.database() as db:
                    m.report(db, m.config())
                target = m.ROOT / 'reports' / 'latest.html' if path == '/api/report' else m.ROOT / 'reports'
                subprocess.run(['/usr/bin/open', str(target)], check=True)
                return self.reply(200, {'message': 'Report opened' if path == '/api/report' else 'Exports folder opened'})
            return self.reply(404, {'error': 'Not found'})
        except (ValueError, KeyError, TypeError) as exc:
            return self.reply(400, {'error': str(exc)})
        except Exception:
            return self.reply(500, {'error': 'The operation failed. Your measurements are retained; check the local logs.'})


def main():
    initialise()
    if len(sys.argv) > 1 and sys.argv[1] != 'serve':
        return m.main()
    server = HTTPServer(('127.0.0.1', 0), Handler)
    server.host = f'127.0.0.1:{server.server_port}'
    server.token = secrets.token_urlsafe(32)
    print(json.dumps({'url': f'http://{server.host}/?token={server.token}'}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

import copy
import http.cookiejar
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor, urlopen

import engine
import mail_templates as templates
import monitor as m


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(m, 'ROOT', Path(self.tmp.name))
        self.patch.start()
        engine.initialise()
        self.c = m.config()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_template_uses_actual_average(self):
        rows = [{'status':'ok','download_mbps':70},{'status':'ok','download_mbps':90},{'status':'failed','download_mbps':None}]
        self.c['profile'].update(provider='Example Fibre', customer_name='Example Customer')
        draft = templates.draft(self.c, rows)
        self.assertIn('80.0 Mbps', draft['body'])
        self.assertIn('Successful tests: 2', draft['body'])
        self.assertIn('Example Fibre', draft['subject'])

    def test_unknown_or_unsafe_template_fields_rejected(self):
        for value in ('{unknown}', '{provider.__class__}', '{provider[0]}', '{provider!r}', '{provider:>10}'):
            with self.assertRaises(ValueError):
                templates.render(value, {'provider':'Example'})

    def test_email_header_injection_and_invalid_config_rejected(self):
        for key, value in [('plan_mbps',True), ('minimum_samples',2.5), ('hours',[]), ('average_hours',float('nan'))]:
            c=copy.deepcopy(self.c);c[key]=value
            with self.assertRaises(ValueError):m.validate_config(c)
        self.c['email']['from']='you@example.com\nBcc: someone@example.com'
        with self.assertRaises(ValueError):m.validate_config(self.c)

    def test_save_only_allowed_settings_and_keep_secrets_out(self):
        payload=copy.deepcopy(self.c)
        payload['email']['password']='must-not-be-written'
        payload['email']['keychain_service']='unexpected-service'
        payload['hours']=[3,8,11,14,17,20]
        with patch.object(engine,'schedule_enabled',return_value=False):
            engine.save_settings(payload)
        saved=(m.ROOT/'config.json').read_text()
        self.assertNotIn('must-not-be-written',saved)
        self.assertNotIn('unexpected-service',saved)
        self.assertEqual(m.config()['hours'],[3,8,11,14,17,20])

    def test_schedule_uses_packaged_runner(self):
        with patch.object(m.Path,'home',return_value=m.ROOT),patch.object(m.subprocess,'run'):
            m.schedule(self.c)
        import plistlib
        payload=plistlib.loads((m.ROOT/'Library/LaunchAgents/local.internet-monitor.plist').read_bytes())
        self.assertEqual(payload['ProgramArguments'],engine.RUNNER+['run','--scheduled'])

    def test_session_and_cross_site_protection(self):
        server=engine.HTTPServer(('127.0.0.1',0),engine.Handler)
        server.host=f'127.0.0.1:{server.server_port}'
        server.token=secrets.token_urlsafe(32)
        base='http://'+server.host
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with self.assertRaises(HTTPError) as exc:urlopen(base+'/api/state')
            self.assertEqual(exc.exception.code,403)
            opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            self.assertEqual(opener.open(base+'/?token='+server.token).status,200)
            with patch.object(engine,'schedule_enabled',return_value=False):
                self.assertEqual(json.load(opener.open(base+'/api/state'))['version'],'1.2.0')
            bad=Request(base+'/api/settings',data=b'{}',headers={'X-Fibbernet':'1','Origin':'https://attacker.example'})
            with self.assertRaises(HTTPError) as exc:opener.open(bad)
            self.assertEqual(exc.exception.code,403)
            with self.assertRaises(HTTPError) as exc:opener.open(base+'/../config.json')
            self.assertEqual(exc.exception.code,404)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    unittest.main()

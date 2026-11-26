import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import monitor as m


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = json.loads((Path(__file__).parent / 'config.example.json').read_text())
        self.root_patch = patch.object(m, 'ROOT', self.root)
        self.root_patch.start()
        self.db = m.database()

    def tearDown(self):
        self.db.close()
        self.root_patch.stop()
        self.tmp.cleanup()

    def add(self, value, status='ok'):
        r = dict.fromkeys(m.FIELDS, '')
        r.update(timestamp_utc=m.now().isoformat(), status=status, download_mbps=value, upload_mbps=30, latency_ms=12)
        self.db.execute('INSERT INTO measurements VALUES (?,?,?,?,?,?,?,?,?)', [r[k] for k in m.FIELDS])
        self.db.commit()

    def test_units_and_invalid_values(self):
        self.assertEqual(m.parse_result({'dl_throughput':700_000_000, 'ul_throughput':40_000_000})[:2], (700,40))
        for bad in (-1, float('nan'), None, '700', True):
            with self.assertRaises(ValueError):
                m.parse_result({'dl_throughput':bad, 'ul_throughput':1})
        with self.assertRaises(ValueError):
            m.parse_result({'dl_throughput':1, 'ul_throughput':1, 'error_code':5})

    def test_failed_tests_not_counted_as_zero(self):
        self.add(100)
        self.add(300)
        self.add(None, 'failed')
        self.assertEqual(m.average(m.rows_since(self.db,24)), 200)
        text = m.report(self.db,self.c)
        self.assertIn('Successful tests: 2 | Failed tests: 1', text)
        self.assertIn('Average download: 200.0 Mbps',text)
        self.assertTrue((self.root/'reports/latest.csv').exists())

    def test_timeout_is_saved(self):
        with patch.object(m.subprocess,'run', side_effect=subprocess.TimeoutExpired('networkQuality',240)):
            row = m.collect(self.db,self.c)
        self.assertEqual(row['status'],'failed')
        self.assertIsNone(row['download_mbps'])
        self.assertTrue((self.root/row['raw_file']).exists())

    def test_email_threshold_minimum_cooldown_and_failure_retry(self):
        self.c['email'].update(enabled=True, host='smtp.example.org',username='user', **{'from':'from@example.org','to':['to@example.org']})
        self.add(70)
        with patch.object(m.smtplib,'SMTP') as smtp, patch.dict(m.os.environ,{'INTERNET_MONITOR_SMTP_PASSWORD':'test-only'}):
            self.assertIn('insufficient',m.email_alert(self.db,self.c))
            smtp.assert_not_called()
            self.add(80)
            self.add(90)
            m.report(self.db,self.c)
            smtp.return_value.__enter__.return_value = smtp.return_value
            smtp.return_value.send_message.return_value = {}
            self.assertEqual(m.email_alert(self.db,self.c),'Email alert sent')
            self.assertIn('cooldown',m.email_alert(self.db,self.c))
            self.assertEqual(smtp.return_value.send_message.call_count,1)
            self.db.execute('DELETE FROM state')
            smtp.return_value.send_message.side_effect = OSError('offline')
            with self.assertRaises(OSError):
                m.email_alert(self.db,self.c)
            self.assertIsNone(self.db.execute('SELECT value FROM state').fetchone())

    def test_boundary_does_not_alert(self):
        self.c['email']['enabled']=True
        for _ in range(3): self.add(700)
        self.assertIn('above threshold',m.email_alert(self.db,self.c))


if __name__ == '__main__':
    unittest.main()

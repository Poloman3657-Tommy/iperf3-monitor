"""Offline export preserves evidence, escapes device text and replaces files atomically."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from gui_runner import RunConfig
import monitor


class HtmlReportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('html_report'), 'HTML exporter is missing')
        import html_report
        self.report = html_report
        self.samples = [dict(start=20, end=21, mbps=10, status='LOW', observed_at='2026-09-15T14:00:00+08:00')]
        self.summary = monitor.summarize(self.samples, 'INTERRUPTED', 'Stopped by user')

    def test_single_html_preserves_samples_dates_and_last_station_record(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            attack = '</script><script>globalThis.injected=true</script>&測試'
            records = [dict(event_id=0, status='RUNNING'), dict(event_id=0, status='ERROR', error=attack)]
            (out / 'mcs-events.jsonl').write_text('\n'.join(json.dumps(r) for r in records), encoding='utf-8')
            path = self.report.save_report(self.samples, self.summary, RunConfig(iperf='private/path'), out, 'hours')
            html = path.read_text(encoding='utf-8')
            payload = json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.S)[1])
            self.assertEqual(payload['samples'][0], [20, 21, 10, 'LOW', self.samples[0]['observed_at']])
            self.assertEqual(payload['summary'], self.summary)
            self.assertEqual(payload['station']['0']['error'], attack)
            self.assertEqual(payload['config']['time_unit'], 'hours')
            self.assertNotIn(attack, html)
            self.assertNotIn('private/path', html)
            self.assertNotRegex(html, r'(?:src|href)=["\']https?://')
            self.assertIn("connect-src 'none'", html)

    def test_failed_save_leaves_existing_report_intact(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / 'report.html').write_text('previous', encoding='utf-8')
            with patch('html_report.os.replace', side_effect=OSError('read only')):
                with self.assertRaises(OSError):
                    self.report.save_report(self.samples, self.summary, RunConfig(iperf=''), out)
            self.assertEqual((out / 'report.html').read_text(), 'previous')
            self.assertEqual([p.name for p in out.iterdir()], ['report.html'])

    def test_empty_run_is_exportable_but_corrupt_station_log_is_not_silenced(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            self.assertTrue(self.report.save_report([], monitor.summarize([], 'ERROR', 'no connection'), RunConfig(iperf=''), out).exists())
            (out / 'mcs-events.jsonl').write_text('{bad', encoding='utf-8')
            with self.assertRaises(ValueError):
                self.report.save_report(self.samples, self.summary, RunConfig(iperf=''), out)


if __name__ == '__main__':
    unittest.main()

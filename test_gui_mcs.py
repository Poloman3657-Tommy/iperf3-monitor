"""Native Tk integration: fake diagnostic worker, real event loop and event table."""
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from gui import MonitorApp
from mcs import SshSettings, parse_station
from test_station import STATION, MAC, TX, RX
from mcs import McsDispatcher


class GuiMcsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda kind, value, tb: self.errors.append(str(value))
        self.app = MonitorApp(self.root, settings_path=Path(self.folder.name) / 'config.json')

    def tearDown(self):
        self.app.close()
        self.folder.cleanup()
        self.assertFalse(self.errors)

    def pump(self, until):
        deadline = time.monotonic() + 5
        while not until() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(until())

    def test_blank_ip_skips_worker_and_dialog_test_then_roundtrips(self):
        self.app.ssh_settings = SshSettings(enabled=True, host='')
        self.app.config = self.app.read_config(check_executable=False)
        with patch('gui.McsDispatcher', side_effect=AssertionError('Blank IP must skip SSH')):
            self.app.events.put(('started', Path(self.folder.name)))
            self.app.events.put(('sample', dict(start=21, end=22, mbps=10, status='LOW', observed_at='2026-09-15T14:32:08+08:00')))
            self.pump(lambda: len(self.app.samples) == 1)
        self.app._update_metrics()
        self.assertIn('2026-09-15 14:32:08', self.app.tree.set('event-0', 'date'))
        self.app.tree.selection_set('event-0')
        self.root.update()
        self.assertIn('2026-09-15 14:32:08', self.app.mcs_detail.get('1.0', 'end'))
        self.app.edit_ssh()
        dialog = self.app.ssh_dialog
        with patch('mcs_dialog.capture', side_effect=AssertionError('Blank test must skip SSH')):
            dialog.test_button.invoke()
            self.assertIsNone(dialog.thread)
        dialog.password.set('runtime-only-test')
        dialog.apply_button.invoke()
        self.app.save_settings()
        raw = self.app.settings_path.read_text(encoding='utf-8')
        self.assertNotIn('runtime-only-test', raw)

    def test_low_events_capture_once_and_results_preserve_selected_row(self):
        self.app.config = replace(self.app.read_config(check_executable=False),
                                  ssh=SshSettings(enabled=True, host='192.0.2.10'))
        self.app.ssh_password = 'runtime-only-test'
        captures = []
        def capture(*args):
            captures.append(True)
            return dict(status='OK', peers=[dict(parse_station(STATION, MAC, 'wlan2.2'), status='OK')])
        with patch('mcs.capture', side_effect=capture):
            self.app.events.put(('started', Path(self.folder.name)))
            for a, status in [(0, 'WARMUP'), (20, 'LOW'), (21, 'LOW')]:
                self.app.events.put(('sample', dict(start=a, end=a+1, mbps=10, status=status)))
            self.pump(lambda: self.app.mcs_results.get(0, {}).get('status') == 'OK')
            self.app._update_metrics()
            self.assertEqual(len(captures), 1)
            self.app.tree.selection_set('event-0')
            self.root.update()
            for a, status in [(22, 'OK'), (23, 'LOW')]:
                self.app.events.put(('sample', dict(start=a, end=a+1, mbps=10, status=status)))
            self.pump(lambda: self.app.mcs_results.get(1, {}).get('status') == 'OK')
            self.app._update_metrics()
            self.assertEqual(len(captures), 2)
            self.assertEqual(self.app.tree.selection(), ('event-0',))
            self.assertIn('TX 960.7 / RX 1080.6', self.app.tree.set('event-0', 'mcs'))
            self.assertIn('TX 960.7 / RX 1080.6', self.app.tree.set('event-1', 'mcs'))
            self.assertIn('rx bitrate: ' + RX, self.app.mcs_detail.get('1.0', 'end'))
            self.app.dispatcher.close(timeout=2)

    def test_close_keeps_event_loop_alive_until_cancel_record_is_saved(self):
        entered, release = threading.Event(), threading.Event()
        def delayed_connect(*args):
            entered.set()
            release.wait(3)
            return dict(status='CANCELLED', peers=[])
        with patch('mcs.capture', side_effect=delayed_connect):
            self.app.dispatcher = McsDispatcher(SshSettings(enabled=True, host='192.0.2.10'),
                'dummy', self.folder.name, self.app.events, Path(self.folder.name) / 'hosts')
            self.app.dispatcher.submit(0, dict(start=20, end=21, mbps=10))
            self.assertTrue(entered.wait(2))
            self.app.close()
            self.assertFalse(self.app.closed, 'Closing must not kill a worker with only RUNNING saved')
            release.set()
            self.pump(lambda: self.app.closed)
            raw = (Path(self.folder.name) / 'mcs-events.jsonl').read_text(encoding='utf-8')
            self.assertIn('CANCELLED', raw)


if __name__ == '__main__':
    unittest.main()

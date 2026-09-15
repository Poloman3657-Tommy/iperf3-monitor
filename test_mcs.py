"""MCS diagnostics: exact parsing, safe commands, and one trigger per LOW episode."""
import importlib.util
import unittest
import queue
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import Mock
from unittest.mock import patch


class McsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('mcs'), 'MCS module is not implemented')
        import mcs
        self.mcs = mcs

    def test_peerlist_uses_complete_mac_lines_and_deduplicates(self):
        text = '2 peer(s) connected:\n\n EA:8C:B6:92:F0:B2\n aa:bb:cc:dd:ee:ff\nEA:8C:B6:92:F0:B2\n'
        self.assertEqual(self.mcs.parse_peers(text), ['EA:8C:B6:92:F0:B2', 'AA:BB:CC:DD:EE:FF'])
        self.assertEqual(self.mcs.parse_peers('0 peer(s) connected:\n'), [])
        with self.assertRaises(ValueError):
            self.mcs.parse_peers('1 peer(s) connected:\nnot-a-mac\n')

    def test_gate_ignores_warmup_and_retriggers_only_after_recovery(self):
        gate = self.mcs.LowEventGate()
        observed = [gate.observe(s) for s in ['WARMUP', 'LOW', 'LOW', 'OK', 'LOW', 'LOW']]
        self.assertEqual(observed, [None, 0, None, None, 1, None])

    def test_gate_matches_report_event_ids_across_missing_intervals(self):
        import monitor
        samples = [dict(start=a, end=b, status=s, mbps=10) for a, b, s in
                   [(0, 1, 'WARMUP'), (1, 2, 'LOW'), (2, 3, 'LOW'), (5, 6, 'LOW'), (6, 7, 'OK'), (7, 8, 'LOW')]]
        gate = self.mcs.LowEventGate()
        ids = [gate.observe(s['status'], s['start'], s['end']) for s in samples]
        self.assertEqual([v for v in ids if v is not None], list(range(len(monitor.summarize(samples, 'COMPLETE', None)['events']))))

    def test_blank_ip_never_opens_ssh_or_creates_diagnostic_files(self):
        with tempfile.TemporaryDirectory() as folder, patch('paramiko.SSHClient', side_effect=AssertionError('No SSH allowed')):
            settings = self.mcs.SshSettings(enabled=True, host='  ')
            self.assertEqual(self.mcs.capture(settings, '', Path(folder) / 'hosts')['status'], 'DISABLED')
            dispatcher = self.mcs.McsDispatcher(settings, '', folder, queue.Queue(), Path(folder) / 'hosts')
            dispatcher.submit(0, dict(start=20, end=21, mbps=10))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_dispatcher_records_busy_events_and_cancellation(self):
        entered = threading.Event()
        def blocked(settings, password, hosts, cancel):
            entered.set()
            if not cancel.wait(3):
                raise AssertionError('Cancellation was not propagated')
            return dict(status='CANCELLED', peers=[])
        with tempfile.TemporaryDirectory() as folder, patch('mcs.capture', side_effect=blocked):
            events = queue.Queue()
            dispatcher = self.mcs.McsDispatcher(self.mcs.SshSettings(enabled=True, host='192.0.2.10'), 'dummy', folder, events, Path(folder) / 'hosts')
            sample = dict(start=20, end=21, mbps=10)
            dispatcher.submit(0, sample)
            self.assertTrue(entered.wait(2))
            dispatcher.submit(1, sample)
            dispatcher.close(timeout=2)
            self.assertFalse(dispatcher.busy)
            values = [events.get_nowait()[1] for _ in range(events.qsize())]
            self.assertEqual([v['status'] for v in values], ['RUNNING', 'SKIPPED_BUSY', 'CANCELLED'])
            self.assertEqual([v['event_id'] for v in values], [0, 1, 0])
            self.assertNotIn('dummy', (Path(folder) / 'mcs-events.jsonl').read_text(encoding='utf-8'))

    def test_timeout_also_bounds_a_server_that_never_acknowledges_exec(self):
        closed = threading.Event()
        channel = Mock()
        channel.close.side_effect = closed.set
        def no_ack(command):
            if not closed.wait(2):
                raise AssertionError('Command acknowledgement hung')
            raise OSError('channel closed')
        channel.exec_command.side_effect = no_ack
        client = Mock()
        client.get_transport.return_value.open_session.return_value = channel
        with self.assertRaises(TimeoutError):
            self.mcs._sudo(client, 'fixed command', 'dummy', threading.Event(), time.monotonic() + .1)
        channel.sendall.assert_not_called()

    def test_redacts_password_before_truncating_remote_error(self):
        password = 'test-only-sensitive-password'
        channel, client = Mock(), Mock()
        client.get_transport.return_value.open_session.return_value = channel
        channel.recv_ready.return_value = False
        channel.recv_stderr_ready.side_effect = [True, False, False]
        channel.recv_stderr.return_value = ('x' * 490 + password).encode()
        channel.exit_status_ready.return_value = True
        channel.recv_exit_status.return_value = 1
        with self.assertRaises(RuntimeError) as caught:
            self.mcs._sudo(client, 'fixed command', password, threading.Event(), time.monotonic() + 2)
        self.assertNotIn(password[:10], str(caught.exception))
        self.assertIn('[REDACTED]', str(caught.exception))

    def test_settings_reject_command_injection_and_missing_host(self):
        for changed in [dict(host='X.X.X.X'), dict(vap='wlan2.2; reboot'), dict(port=0), dict(username='tech\nroot')]:
            with self.assertRaises(ValueError):
                self.mcs.SshSettings(**(dict(enabled=True, host='192.0.2.10') | changed)).validated()
        self.assertFalse(self.mcs.SshSettings(enabled=True, host='').validated().active)
        valid = self.mcs.SshSettings(enabled=True, host='192.0.2.10', vap='wlan2.2').validated()
        command = self.mcs.sudo_command(valid.vap, 'station', 'EA:8C:B6:92:F0:B2')
        self.assertIn('sudo -S', command)
        self.assertIn('iw dev', command)
        self.assertIn('wlan2.2', command)
        with self.assertRaises(ValueError):
            self.mcs.sudo_command('wlan2.2', 'reboot')


if __name__ == '__main__':
    unittest.main()

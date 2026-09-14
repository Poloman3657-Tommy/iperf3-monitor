"""Test desktop runner intent using real child processes, without requiring a GUI."""
import argparse
import importlib.util
from pathlib import Path
import queue
import sys
import tempfile
import threading
import unittest

import monitor


class BundlePathsTests(unittest.TestCase):
    def test_frozen_app_finds_its_own_iperf_and_writable_results_next_to_exe(self):
        from unittest.mock import patch
        import os
        import gui_runner
        with tempfile.TemporaryDirectory(prefix='iperf portable ') as folder:
            base = Path(folder)
            name = 'iperf3.exe' if os.name == 'nt' else 'iperf3'
            bundled = base / 'iperf3' / name
            bundled.parent.mkdir()
            bundled.write_text('fixture')
            bundled.chmod(0o755)
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(base / 'IperfMonitor.exe')):
                self.assertEqual(gui_runner.find_iperf(), str(bundled))
                self.assertEqual(gui_runner.RunConfig(iperf=str(bundled)).output, base / 'gui-results')


class CollectionEventsTests(unittest.TestCase):
    def test_continuous_run_has_no_former_twenty_second_deadline(self):
        from unittest.mock import patch
        stop, clock, received = threading.Event(), [0.0], []
        args = argparse.Namespace(duration=0, parallel=1, warmup=0, threshold=100)
        code = "import time; print('[ 5] 0.00-1.00 sec 1 MBytes 50 Mbits/sec', flush=True); print('[ 5] 1.00-2.00 sec 1 MBytes 50 Mbits/sec', flush=True); time.sleep(30)"

        def on_sample(sample):
            received.append(sample)
            clock[0] = 30.0  # Advance beyond the old duration + 20 deadline.
            if len(received) == 2:
                stop.set()

        with tempfile.TemporaryDirectory() as folder, patch.object(monitor.time, 'monotonic', side_effect=lambda: clock[0]):
            samples, state, _ = monitor.collect([sys.executable, '-c', code], args, Path(folder),
                                                stop_event=stop, on_sample=on_sample, quiet=True)
        self.assertEqual(state, 'INTERRUPTED')
        self.assertEqual(len(samples), 2)

    def test_unexpected_completion_of_continuous_run_is_not_pass(self):
        args = argparse.Namespace(duration=0, parallel=1, warmup=0, threshold=100)
        code = "print('[ 5] 0.00-1.00 sec 1 MBytes 200 Mbits/sec'); print('iperf Done.')"
        with tempfile.TemporaryDirectory() as folder:
            _, state, error = monitor.collect([sys.executable, '-c', code], args, Path(folder), quiet=True)
        self.assertEqual(state, 'ERROR')
        self.assertIn('Continuous', error)

    def test_stop_drains_a_burst_already_written_by_the_child(self):
        stop = threading.Event()
        args = argparse.Namespace(duration=60, parallel=1, warmup=0, threshold=100)
        lines = [f'[ 5] {i}.00-{i+1}.00 sec 1 MBytes 50 Mbits/sec' for i in range(5)]
        code = f'import sys,time; sys.stdout.write({chr(10).join(lines)!r} + "\\n"); sys.stdout.flush(); time.sleep(30)'
        with tempfile.TemporaryDirectory() as folder:
            samples, state, _ = monitor.collect([sys.executable, '-c', code], args, Path(folder),
                                                stop_event=stop, on_sample=lambda s: stop.set(), quiet=True)
            self.assertEqual(state, 'INTERRUPTED')
            self.assertEqual(len(samples), 5, 'Stopping must preserve the entire received burst')
            self.assertEqual(len((Path(folder) / 'iperf.log').read_text().splitlines()), 5)

    def test_stop_retains_received_sample_and_notifies_without_passing(self):
        stop = threading.Event()
        received, lines = [], []

        def sample_ready(sample):
            received.append(sample)
            stop.set()

        args = argparse.Namespace(duration=60, parallel=1, warmup=20, threshold=100)
        code = "import time; print('[ 5] 0.00-1.00 sec 1 MBytes 50 Mbits/sec', flush=True); time.sleep(30)"
        with tempfile.TemporaryDirectory() as folder:
            samples, state, error = monitor.collect(
                [sys.executable, '-c', code], args, Path(folder),
                stop_event=stop, on_sample=sample_ready, on_line=lines.append, quiet=True)
            self.assertEqual(state, 'INTERRUPTED')
            self.assertEqual(len(received), 1)
            self.assertEqual(samples[0]['status'], 'WARMUP')
            self.assertTrue(lines)
            self.assertIn('WARMUP', (Path(folder) / 'samples.csv').read_text())


class DesktopConfigTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('gui_runner'), 'Desktop runner is not implemented')
        import gui_runner
        self.runner = gui_runner

    def config(self, **changes):
        data = dict(iperf=sys.executable, server='192.168.137.57', port=4477,
                    duration=60, warmup=20, threshold=100, parallel=1,
                    reverse=False, output=Path(tempfile.gettempdir()))
        return self.runner.RunConfig(**(data | changes)).validated()

    def test_command_uses_argument_list_and_explicit_download(self):
        normal = self.config().command()
        self.assertIsInstance(normal, list)
        self.assertNotIn('-R', normal)
        self.assertIn('-R', self.config(reverse=True).command())
        self.assertEqual(normal[normal.index('-p') + 1], '4477')
        self.assertEqual(normal[normal.index('-f') + 1], 'm')

    def test_zero_duration_preserves_warmup_and_requests_native_continuous_test(self):
        config = self.config(duration=0)
        self.assertEqual(config.warmup, 20)
        args = config.command()
        self.assertEqual(args[args.index('-t') + 1], '0')

    def test_udp_command_has_explicit_per_stream_rate_and_reverse(self):
        config = self.config(protocol='UDP', udp_mbps=25.5, parallel=2, reverse=True)
        args = config.command()
        self.assertIn('-u', args)
        self.assertIn('-R', args)
        self.assertEqual(args[args.index('-b') + 1], '25500000')
        self.assertEqual(args[args.index('-P') + 1], '2')
        tcp = self.config(protocol='TCP', udp_mbps=25.5).command()
        self.assertNotIn('-u', tcp)
        self.assertNotIn('-b', tcp)

    def test_invalid_settings_fail_before_start(self):
        for changes in [dict(server='1.2.3.4 & calc'), dict(port=65536), dict(port=1.5),
                        dict(duration=20), dict(duration=-1), dict(threshold=float('nan')), dict(warmup=-1),
                        dict(parallel=0), dict(iperf='not-an-executable-123')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.config(**changes)

    def test_worker_failure_always_publishes_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            blocking = Path(folder) / 'not-a-directory'
            blocking.write_text('keep')
            config = self.config(output=blocking)
            events = queue.Queue()
            self.runner.run_test(config, threading.Event(), events)
            messages = []
            while not events.empty():
                messages.append(events.get_nowait())
            finished = [value for kind, value in messages if kind == 'finished']
            self.assertEqual(len(finished), 1)
            self.assertEqual(finished[0].summary['verdict'], 'ERROR')
            self.assertTrue(finished[0].summary['error'])
            self.assertEqual(blocking.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()

"""Behavior tests: warm-up boundaries, strict threshold, parsing, failures."""
import importlib.util
import unittest
import argparse
import sys
import tempfile
from pathlib import Path

MODULE = Path(__file__).with_name('monitor.py')


class MonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MODULE.exists():
            import monitor
            cls.m = monitor

    def setUp(self):
        self.assertTrue(MODULE.exists(), 'Monitoring implementation is missing')

    def test_warmup_and_crossing_interval_are_not_alarm(self):
        for start, end in [(0, 1), (19, 20), (19.99, 21)]:
            self.assertEqual(self.m.classify(start, end, 1, 20, 100), 'WARMUP')
        self.assertEqual(self.m.classify(20, 21, 99, 20, 100), 'LOW')

    def test_exact_threshold_passes_and_zero_is_low(self):
        self.assertEqual(self.m.classify(20, 21, 100, 20, 100), 'OK')
        self.assertEqual(self.m.classify(20, 21, 0, 20, 100), 'LOW')

    def test_units_and_summary_exclusion(self):
        for number, unit, expected in [('99999', 'K', 99.999), ('100', 'M', 100), ('1.2', 'G', 1200), ('12', '', 0.000012)]:
            line = f'[  5]  20.00-21.00 sec  12 MBytes {number} {unit}bits/sec'
            self.assertAlmostEqual(self.m.parse_interval(line, 1)['mbps'], expected)
            self.assertIsNone(self.m.parse_interval(line + ' sender', 1))
            self.assertIsNone(self.m.parse_interval(line + ' receiver', 1))

    def test_parallel_uses_only_sum(self):
        self.assertIsNone(self.m.parse_interval('[ 5] 20.00-21.00 sec 1 MBytes 50 Mbits/sec', 2))
        self.assertEqual(self.m.parse_interval('[SUM] 20.00-21.00 sec 1 MBytes 100 Mbits/sec', 2)['mbps'], 100)

    def test_zero_byte_interval_is_still_a_measurement(self):
        sample = self.m.parse_interval('[ 5] 20.00-21.00 sec 0.00 Bytes 0.00 Kbits/sec', 1)
        self.assertIsNotNone(sample, 'A complete traffic stall must not disappear from monitoring')
        self.assertEqual(sample['mbps'], 0)

    def test_invalid_interval_is_rejected(self):
        for args in [(21, 20, 100), (20, 20, 100), (20, 21, -1), (20, 21, float('nan'))]:
            with self.assertRaises(ValueError):
                self.m.classify(*args, 20, 100)

    def test_outages_merge_only_adjacent_low_intervals(self):
        samples = [dict(start=a, end=b, mbps=v, status=s) for a, b, v, s in
                   [(0, 1, 1, 'WARMUP'), (20, 21, 90, 'LOW'), (21, 22, 80, 'LOW'),
                    (22, 23, 110, 'OK'), (23, 24, 0, 'LOW')]]
        result = self.m.summarize(samples, 'COMPLETE', None)
        self.assertEqual(result['verdict'], 'LOW')
        self.assertEqual(result['low_seconds'], 3)
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(result['events'][0]['min_mbps'], 80)

    def test_failed_or_empty_run_never_passes(self):
        self.assertEqual(self.m.summarize([], 'COMPLETE', None)['verdict'], 'NO_DATA')
        samples = [dict(start=20, end=21, mbps=200, status='OK')]
        self.assertEqual(self.m.summarize(samples, 'ERROR', 'Connection refused')['verdict'], 'ERROR')

    def test_collect_keeps_raw_and_samples_when_process_fails(self):
        args = argparse.Namespace(duration=21, parallel=1, warmup=20, threshold=100)
        code = "print('[ 5] 0.00-1.00 sec 0.00 Bytes 0.00 Kbits/sec'); print('iperf3: error - connection lost'); raise SystemExit(1)"
        with tempfile.TemporaryDirectory() as directory:
            samples, state, error = self.m.collect([sys.executable, '-c', code], args, Path(directory))
            self.assertEqual(state, 'ERROR')
            self.assertIn('connection lost', error)
            self.assertEqual(samples[0]['status'], 'WARMUP')
            self.assertIn('connection lost', (Path(directory) / 'iperf.log').read_text())
            self.assertIn('WARMUP', (Path(directory) / 'samples.csv').read_text())

    def test_silent_process_is_stopped_by_deadline(self):
        # A shortened deadline tests a real silent child without a 20-second wait.
        args = argparse.Namespace(duration=-19.9, parallel=1, warmup=20, threshold=100)
        with tempfile.TemporaryDirectory() as directory:
            _, state, error = self.m.collect([sys.executable, '-c', 'import time; time.sleep(30)'], args, Path(directory))
            self.assertEqual(state, 'ERROR')
            self.assertIn('exceeded', error)

    def test_tiny_positive_bitrate_must_not_become_unlimited(self):
        from unittest.mock import patch
        with patch.object(sys, 'argv', ['monitor.py', '--bitrate', '0.0000001']):
            with self.assertRaises(SystemExit) as caught:
                self.m.arguments()
        self.assertEqual(caught.exception.code, 2)


if __name__ == '__main__':
    unittest.main()

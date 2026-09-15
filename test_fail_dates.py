"""Fail timestamps must survive event merging, export, and delayed GUI/SSH work."""
import argparse
import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import monitor


class FailDateTests(unittest.TestCase):
    def test_event_retains_first_detection_date_and_exports_it_without_ssh(self):
        samples = [dict(start=i, end=i+1, mbps=10, status='LOW', observed_at=date)
                   for i, date in [(20, '2026-09-15T23:59:59+08:00'), (21, '2026-09-16T00:00:00+08:00')]]
        with tempfile.TemporaryDirectory() as folder:
            summary = monitor.save_summary(samples, 'COMPLETE', None, Path(folder))
            self.assertEqual(summary['events'][0].get('detected_at'), samples[0]['observed_at'])
            with (Path(folder) / 'low_events.csv').open(encoding='utf-8', newline='') as stream:
                self.assertEqual(next(csv.DictReader(stream))['detected_at'], samples[0]['observed_at'])

    def test_collector_stamps_receipt_before_delayed_callbacks(self):
        instant = datetime(2026, 9, 15, 6, 32, 8, tzinfo=timezone.utc)
        command = [sys.executable, '-c', "print('[ 5] 0.00-1.00 sec 1 MBytes 10 Mbits/sec'); print('iperf Done.')"]
        args = argparse.Namespace(duration=1, parallel=1, warmup=0, threshold=100)
        with tempfile.TemporaryDirectory() as folder, patch('monitor.datetime') as clock:
            clock.now.return_value = instant
            # Simulate a later wall clock in the consumer callback; receipt time must already exist.
            samples, state, error = monitor.collect(command, args, Path(folder), quiet=True,
                on_line=lambda _: setattr(clock.now, 'return_value', instant + timedelta(hours=1)))
            self.assertEqual(state, 'COMPLETE', error)
            expected = instant.astimezone().isoformat(timespec='milliseconds')
            self.assertEqual(samples[0].get('observed_at'), expected)
            with (Path(folder) / 'samples.csv').open(encoding='utf-8', newline='') as stream:
                self.assertEqual(next(csv.DictReader(stream))['observed_at'], expected)


if __name__ == '__main__':
    unittest.main()

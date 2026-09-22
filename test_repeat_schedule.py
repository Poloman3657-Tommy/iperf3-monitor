"""Repeat scheduling uses elapsed wall time and never overlaps unfinished reports."""
import importlib.util
import argparse
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from gui_runner import RunConfig
import monitor


class RepeatScheduleTests(unittest.TestCase):
    def test_wait_starts_at_round_completion_and_deadline_includes_wait(self):
        self.assertIsNotNone(importlib.util.find_spec('repeat_schedule'), 'Scheduler missing')
        from repeat_schedule import RepeatSchedule
        schedule = RepeatSchedule(repeat_minutes=5, total_minutes=12, now=100)
        self.assertTrue(schedule.ready(100))
        schedule.begin_round(100)
        schedule.finish_round(160)
        self.assertFalse(schedule.ready(459.99))
        self.assertTrue(schedule.ready(460))
        self.assertEqual(schedule.deadline, 820)
        schedule.begin_round(500)  # An outstanding report delayed this start.
        self.assertEqual(schedule.round_number, 2)
        schedule.finish_round(560)
        self.assertFalse(schedule.ready(860), 'Never start a round after total wall time')
        self.assertTrue(schedule.expired(820))

    def test_settings_roundtrip_and_continuous_disables_schedule(self):
        self.assertIn('total_minutes', RunConfig.__dataclass_fields__, 'Scheduling preferences missing')
        from config_store import save_config, load_config
        config = RunConfig(iperf='', duration=60, repeat_minutes=5, total_minutes=30).validated(check_executable=False)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            save_config(config, path)
            self.assertEqual(load_config(path).repeat_minutes, 5)
            self.assertEqual(load_config(path).total_minutes, 30)
        config = RunConfig(iperf='', duration=0, repeat_minutes='ignored', total_minutes='ignored').validated(check_executable=False)
        self.assertEqual((config.repeat_minutes, config.total_minutes), (0, 0))
        for change in [dict(repeat_minutes=-1),dict(total_minutes=float('inf')),dict(total_minutes=True),dict(total_minutes=10**400)]:
            with self.assertRaises(ValueError):
                RunConfig(iperf='', **change).validated(check_executable=False)

    def test_total_deadline_stops_even_a_silent_child_and_preserves_output(self):
        import inspect
        self.assertIn('stop_at', inspect.signature(monitor.collect).parameters, 'Collector needs an independent schedule deadline')
        command = [sys.executable, '-c', "import time; print('[ 5] 0.00-1.00 sec 1 MBytes 50 Mbits/sec', flush=True); time.sleep(30)"]
        args = argparse.Namespace(duration=60, parallel=1, warmup=0, threshold=100)
        with tempfile.TemporaryDirectory() as folder:
            started = time.monotonic()
            samples, state, error = monitor.collect(command, args, Path(folder), quiet=True, stop_at=started+.8)
            self.assertLess(time.monotonic()-started, 4)
            self.assertEqual(state, 'INTERRUPTED')
            self.assertEqual(len(samples), 1)
            self.assertIn('Schedule time limit', error)
            self.assertIn('LOW', (Path(folder)/'samples.csv').read_text())

    def test_expired_schedule_never_launches_a_new_child(self):
        import inspect
        self.assertIn('stop_at', inspect.signature(monitor.collect).parameters)
        args = argparse.Namespace(duration=60, parallel=1, warmup=0, threshold=100)
        with tempfile.TemporaryDirectory() as folder, patch('monitor.subprocess.Popen') as spawn:
            samples, state, error = monitor.collect(['unused'], args, Path(folder), quiet=True, stop_at=time.monotonic()-1)
            spawn.assert_not_called()
            self.assertEqual(state, 'INTERRUPTED')
            self.assertIn('Schedule time limit', error)


if __name__ == '__main__':
    unittest.main()

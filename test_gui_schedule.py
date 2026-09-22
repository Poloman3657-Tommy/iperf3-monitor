"""Native Tk schedule controls and complete round/report/cancel lifecycle."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from gui import MonitorApp
from gui_runner import RunOutcome
import monitor


class GuiScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = MonitorApp(self.root, iperf=__import__('sys').executable,
                              settings_path=Path(self.temp.name)/'config.json')
        self.errors = []
        self.root.report_callback_exception = lambda kind, value, tb: self.errors.append(str(value))
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.pump(lambda: self.app.closed)
        self.temp.cleanup()
        self.assertFalse(self.errors)

    def pump(self, condition, timeout=7):
        deadline = time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(condition())

    def settings(self, repeat='.002', total='.04'):
        self.assertIn('repeat_minutes', self.app.vars, 'Repeat controls missing')
        for key, value in dict(duration='1',warmup='0',repeat_minutes=repeat,total_minutes=total,output=self.temp.name).items():
            self.app.vars[key].set(value)

    def worker(self, calls, verdict='COMPLETE'):
        def run(config, stop, events, **kwargs):
            if calls:
                marked = calls[-1][0].with_name(calls[-1][0].name+'_LOW')
                self.assertTrue((marked/'report.html').exists(), 'Next run started before previous report completed and marked')
            output = config.output / str(len(calls)+1)
            output.mkdir()
            started = time.monotonic()
            sample = dict(start=0,end=1,mbps=10,status='LOW')
            finished = time.monotonic()
            calls.append((output,started,finished,kwargs))
            events.put(('started',output))
            events.put(('sample',sample))
            events.put(('finished',RunOutcome(config,output,[sample],monitor.summarize([sample],verdict,'test failure' if verdict=='ERROR' else None),finished)))
        return run

    def test_zero_seconds_disables_and_ignores_schedule_entries(self):
        self.settings()
        self.app.vars['duration'].set('0')
        self.assertTrue(self.app.repeat_entry.instate(['disabled']))
        self.assertTrue(self.app.total_entry.instate(['disabled']))
        self.app.vars['repeat_minutes'].set('ignored')
        self.app.vars['total_minutes'].set('ignored')
        cfg = self.app.read_config(check_executable=False)
        self.assertEqual((cfg.repeat_minutes,cfg.total_minutes),(0,0))
        self.app.vars['duration'].set('1')
        self.assertFalse(self.app.repeat_entry.instate(['disabled']))

    def test_repeats_waits_for_reports_and_expires_without_extra_round(self):
        self.settings()
        calls=[]
        with patch('gui.run_test',side_effect=self.worker(calls)), patch('monitor.draw_plot'):
            self.app.start()
            self.pump(lambda: self.app.schedule is None and not self.app.active and self.app.report_worker is None and not self.app.report_pending)
            self.assertGreaterEqual(len(calls),2)
            for previous,current in zip(calls,calls[1:]):
                self.assertGreaterEqual(current[1]-previous[2], .12)
            deadline=calls[0][3]['stop_at']
            self.assertTrue(all(call[1]<deadline for call in calls))
            self.assertEqual(len({call[0].parent for call in calls}),1)
            self.assertIn('總時間',self.app.schedule_status.get())
            self.assertTrue(self.app.start_button.instate(['!disabled']))

    def test_stop_during_wait_and_measurement_error_cancel_future_rounds(self):
        self.settings(repeat='5',total='30')
        calls=[]
        with patch('gui.run_test',side_effect=self.worker(calls)), patch('monitor.draw_plot'):
            self.app.start()
            self.pump(lambda: self.app.report_file is not None)
            self.assertIsNotNone(self.app.schedule)
            self.assertTrue(self.app.repeat_entry.instate(['disabled']))
            self.app.stop_button.invoke()
            self.assertIsNone(self.app.schedule)
            self.assertEqual(len(calls),1)
        self.settings(repeat='0',total='1')
        failed=[]
        with patch('gui.run_test',side_effect=self.worker(failed,'ERROR')), patch('monitor.draw_plot'):
            self.app.start()
            self.pump(lambda: self.app.report_file is not None)
            self.assertIsNone(self.app.schedule)
            self.assertEqual(len(failed),1)
            self.assertIn('錯誤',self.app.schedule_status.get())


if __name__ == '__main__':
    unittest.main()

"""Plot transformations must preserve units, sample values and low-rate events."""
import importlib.util
import unittest


class ChartingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('charting'), 'Chart helpers are not implemented')
        import charting
        self.chart = charting

    def test_auto_time_units_at_seconds_minutes_hours_and_days(self):
        for seconds, expected in [(0, 'seconds'), (59, 'seconds'), (60, 'minutes'),
                                  (3599, 'minutes'), (3600, 'hours'), (86399, 'hours'), (86400, 'days')]:
            self.assertEqual(self.chart.resolve_time_unit('auto', seconds), expected)
        self.assertEqual(self.chart.resolve_time_unit('seconds', 200000), 'seconds')
        self.assertEqual(self.chart.format_time_tick(90000, 'days'), '1.04167')
        self.assertEqual(self.chart.format_time_tick(180, 'minutes'), '3')

    def test_curve_passes_samples_without_overshoot_or_mutation(self):
        import numpy as np
        samples = [dict(start=i, end=i+1, mbps=v, status='LOW' if v < 100 else 'OK')
                   for i, v in enumerate([200, 50, 900, 0, 500])]
        original = [s.copy() for s in samples]
        x, y = self.chart.curve_points(samples)
        self.assertGreater(len(x), len(samples) * 2)
        for i, sample in enumerate(samples):
            center = i + .5
            self.assertAlmostEqual(float(np.interp(center, x, y)), sample['mbps'])
            if i + 1 < len(samples):
                segment = y[(x >= center) & (x <= center + 1)]
                self.assertGreaterEqual(float(segment.min()), min(sample['mbps'], samples[i+1]['mbps']))
                self.assertLessEqual(float(segment.max()), max(sample['mbps'], samples[i+1]['mbps']))
        self.assertEqual(samples, original)

    def test_empty_single_and_gapped_samples_are_drawn_honestly(self):
        import numpy as np
        x, y = self.chart.curve_points([])
        self.assertEqual(len(x), 0)
        one = dict(start=0, end=1, mbps=0, status='LOW')
        x, y = self.chart.curve_points([one])
        self.assertTrue(np.all(y == 0))
        x, y = self.chart.curve_points([one, dict(start=3, end=4, mbps=100, status='OK')])
        self.assertTrue(np.isnan(y).any(), 'Missing intervals must not be connected by a curve')

    def test_axes_convert_labels_only_and_keep_mbps_and_raw_low_points(self):
        from matplotlib.figure import Figure
        ax = Figure().subplots()
        samples = [dict(start=0, end=60, mbps=90, status='LOW'), dict(start=60, end=120, mbps=110, status='OK')]
        self.chart.draw_throughput(ax, samples, 20, 100, 'minutes')
        self.assertIn('minutes', ax.get_xlabel())
        self.assertIn('Mbps', ax.get_ylabel())
        self.assertEqual(ax.xaxis.get_major_formatter()(60, 0), '1')
        low = next(c for c in ax.collections if c.get_label() == 'Below threshold')
        self.assertEqual(list(low.get_offsets()[0]), [30, 90])

    def test_low_event_backgrounds_do_not_create_one_artist_per_event(self):
        from matplotlib.figure import Figure
        ax = Figure().subplots()
        samples = [dict(start=i, end=i+1, mbps=50 if i % 2 else 200, status='LOW' if i % 2 else 'OK')
                   for i in range(200)]
        self.chart.draw_throughput(ax, samples, 20, 100, 'auto')
        self.assertLessEqual(len(ax.patches), 1, 'Long runs must not create thousands of span patches')


if __name__ == '__main__':
    unittest.main()

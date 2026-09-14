"""Time viewport navigation must preserve history and make brief failures inspectable."""
import importlib.util
import unittest


class ViewportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('viewport'))
        import viewport
        self.v = viewport

    def test_manual_zoom_survives_arriving_samples_and_preserves_cursor_anchor(self):
        view = self.v.TimeViewport()
        view.zoom(0.5, 25, 100)
        self.assertEqual(view.limits(100), (12.5, 62.5))
        self.assertEqual(view.limits(120), (12.5, 62.5))
        self.assertEqual(view.mode, 'manual')

    def test_drag_and_scroll_clamp_to_available_data(self):
        view = self.v.TimeViewport()
        view.set_window(10, 20, 100)
        view.pan(-500, 100)
        self.assertEqual(view.limits(100), (0, 10))
        view.move_to(1, 100)
        self.assertEqual(view.limits(100), (90, 100))
        self.assertEqual(view.fractions(100), (.9, 1))

    def test_follow_keeps_zoom_width_while_show_all_expands(self):
        view = self.v.TimeViewport()
        view.set_window(20, 30, 100)
        view.follow_latest(100)
        self.assertEqual(view.limits(130), (120, 130))
        view.show_all()
        self.assertEqual(view.limits(150), (0, 150))
        new_view = self.v.TimeViewport()
        new_view.follow_latest(3)
        self.assertEqual(new_view.limits(100), (40, 100))

    def test_focus_on_day_three_failure_has_context(self):
        view = self.v.TimeViewport()
        start = 3*86400 + 123
        view.focus_event(start, start+2, 4*86400)
        left, right = view.limits(4*86400)
        self.assertLess(left, start)
        self.assertGreater(right, start+2)
        self.assertLessEqual(right-left, 15)
        self.assertEqual(view.limits(5*86400), (left, right))

    def test_zoom_limits_handle_tiny_or_empty_ranges(self):
        view = self.v.TimeViewport()
        for _ in range(50):
            view.zoom(.1, 0, 0)
        self.assertEqual(view.limits(0), (0, 1))
        for _ in range(50):
            view.zoom(10, 0, 100)
        self.assertEqual(view.limits(100), (0, 100))


if __name__ == '__main__':
    unittest.main()

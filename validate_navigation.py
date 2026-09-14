"""Synthetic multi-day Tk/Matplotlib interaction checks; no network traffic."""
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

from matplotlib.backend_bases import MouseEvent
from gui import MonitorApp
from gui_runner import RunConfig


def main():
    with tempfile.TemporaryDirectory(prefix='iperf-navigation-') as folder:
        root = tk.Tk(); root.withdraw()
        errors = []
        root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
        app = MonitorApp(root, sys.executable, settings_path=Path(folder) / 'config.json')
        app.config = RunConfig(iperf=sys.executable, duration=0)
        app.samples = [dict(start=i, end=i+1, mbps=40 if i % 2000 in (1000, 1001) else 900,
                            status='LOW' if i % 2000 in (1000, 1001) else 'OK')
                       for i in range(4*86400)]
        try:
            start = time.perf_counter()
            app._update_metrics(); app._draw(); app.canvas.draw()
            overview_time = time.perf_counter()-start
            assert len(app.tree.get_children()) > 100
            app.tree.selection_set('event-150'); root.update()
            event = app.event_records[150]
            left, right = app.viewport.limits(app._timeline_end())
            assert left < event['start'] < event['end'] < right and right-left < 20
            app.canvas.draw()
            x, y = app.ax.transData.transform(((left+right)/2, 100))
            wheel = MouseEvent('scroll_event', app.canvas, x, y, button='up', step=1)
            app.canvas.callbacks.process('scroll_event', wheel)
            zoomed = app.viewport.limits(app._timeline_end())
            assert zoomed[1]-zoomed[0] < right-left
            app.canvas.draw()
            x, y = app.ax.transData.transform((sum(zoomed)/2, 100))
            for name, px in [('button_press_event', x), ('motion_notify_event', x+35),
                             ('motion_notify_event', x), ('button_release_event', x)]:
                app.canvas.callbacks.process(name, MouseEvent(name, app.canvas, px, y, button=1))
            restored = app.viewport.limits(app._timeline_end())
            assert abs(restored[0]-zoomed[0]) < .05, (restored, zoomed)

            # Returning to an already-selected event must work after navigating away.
            app.show_all()
            with patch.object(app.tree, 'identify_row', return_value='event-150'):
                app._on_event_clicked(SimpleNamespace(y=20))
            selected_view = app.viewport.limits(app._timeline_end())
            app.active = True
            app.samples.append(dict(start=4*86400, end=4*86400+1, mbps=900, status='OK'))
            app._update_metrics(); app._draw()
            assert app.viewport.limits(app._timeline_end()) == selected_view
            assert app.tree.selection() == ('event-150',)
            app.follow_latest()
            assert app.viewport.limits(app._timeline_end())[1] == app._timeline_end()
            app._on_timeline_scroll('moveto', '0.25')
            assert app.viewport.mode == 'manual'
            assert abs(app.viewport.limits(app._timeline_end())[0] / app._timeline_end() - .25) < .0001
            app.show_all()
            assert app.viewport.limits(app._timeline_end()) == (0, app._timeline_end())
            app._on_event_selected()
            start = time.perf_counter(); app._draw(); app.canvas.draw()
            detail_time = time.perf_counter()-start
            output = Path(__file__).resolve().parent / 'validation' / 'navigation'
            output.mkdir(parents=True, exist_ok=True)
            app.ax.set_title('Synthetic day-3 failure: zoomed view', loc='left')
            app.figure.savefig(output / 'day-3-failure.png', dpi=160)
            assert not errors, errors
            print(f'PASS: 4-day synthetic data, {app.tree_rows} accessible events; overview {overview_time:.3f}s, detail {detail_time:.3f}s; wheel, drag-back, scrollbar, same-row focus, stable history and follow.')
        finally:
            app.active = False
            app.close()


if __name__ == '__main__':
    main()

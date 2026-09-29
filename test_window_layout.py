"""Small screens must retain the status footer and access to every setting."""
import importlib.util
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch


class WindowSizingTests(unittest.TestCase):
    def test_initial_window_and_minimum_fit_available_work_area(self):
        self.assertIsNotNone(importlib.util.find_spec('window_layout'), 'Responsive layout helpers missing')
        from window_layout import window_dimensions
        for width,height in [(1920,1040),(1366,728),(1093,582),(910,480),(800,560)]:
            with self.subTest(width=width,height=height):
                w,h,min_w,min_h=window_dimensions(width,height)
                self.assertLessEqual(w,width-24)
                self.assertLessEqual(h,height-50)
                self.assertLessEqual(min_w,w)
                self.assertLessEqual(min_h,h)


class NativeLayoutTests(unittest.TestCase):
    def test_footer_and_form_remain_accessible_at_small_sizes_and_font_scales(self):
        from gui import MonitorApp
        for width,height,factor in [(1100,650,1),(960,600,1.25),(850,540,1.5)]:
            with self.subTest(width=width,height=height,factor=factor), tempfile.TemporaryDirectory() as folder:
                root=tk.Tk();root.withdraw()
                root.tk.call('tk','scaling',float(root.tk.call('tk','scaling'))*factor)
                app=MonitorApp(root,settings_path=Path(folder)/'config.json')
                errors=[]
                root.report_callback_exception=lambda kind,value,tb:errors.append(str(value))
                try:
                    root.geometry(f'{width}x{height}')
                    # Unmapped Tk windows do not lay out their outer frame. Map invisibly
                    # so bounds reflect a real window, without displaying test windows.
                    root.attributes('-alpha',0)
                    if sys.platform=='win32':
                        root.attributes('-disabled',True)
                    root.deiconify()
                    root.update()
                    self.assertFalse(errors)
                    self.assertLessEqual(root.winfo_height(),height,'Minimum height prevents fitting the screen')
                    self.assertTrue(hasattr(app,'footer_labels'),'Footer must reserve its own space')
                    for label in app.footer_labels:
                        self.assertGreaterEqual(label.winfo_height(),label.winfo_reqheight())
                        self.assertGreaterEqual(label.winfo_rooty(),root.winfo_rooty())
                        self.assertLessEqual(label.winfo_rooty()+label.winfo_height(),root.winfo_rooty()+height)
                    self.assertGreater(app.canvas.get_tk_widget().winfo_height(),60)
                    self.assertGreater(app.ax.bbox.height,40,'Final chart axes must remain readable after resize')
                    for card in app.metric_cards:
                        self.assertGreater(card.winfo_width(),80)
                        self.assertLessEqual(card.winfo_x()+card.winfo_width(),card.master.winfo_width())
                    app.form_scroll.canvas.yview_moveto(1)
                    root.update()
                    top=app.form_scroll.canvas.winfo_rooty()
                    bottom=top+app.form_scroll.canvas.winfo_height()
                    self.assertGreaterEqual(app.report_button.winfo_rooty(),top)
                    self.assertLessEqual(app.report_button.winfo_rooty()+app.report_button.winfo_height(),bottom)
                    self.assertLess(app.form_scroll.canvas.yview()[0],app.form_scroll.canvas.yview()[1])
                    # Tab navigation must reveal a setting even after scrolling away.
                    app.form_scroll._focus(SimpleNamespace(widget=app.total_entry))
                    root.update()
                    self.assertGreaterEqual(app.total_entry.winfo_rooty(),top)
                    self.assertLessEqual(app.total_entry.winfo_rooty()+app.total_entry.winfo_height(),bottom)
                    # Parent scrolling must not steal the plot's wheel-to-zoom action.
                    chart=app.canvas.get_tk_widget()
                    for panel in (app.form_scroll,app.right_scroll):
                        before=panel.canvas.yview()
                        with patch.object(panel,'winfo_containing',return_value=chart):
                            self.assertIsNone(panel._wheel(SimpleNamespace(x_root=0,y_root=0,delta=-120)))
                        self.assertEqual(panel.canvas.yview(),before)
                    before=app.right_scroll.canvas.yview()
                    app.right_scroll._focus(SimpleNamespace(widget=chart.master.master))
                    self.assertEqual(app.right_scroll.canvas.yview(),before,'Focusing the notebook must not jump to its bottom')
                    long_path='圖檔：C:\\'+'long-folder\\'*50+'result_LOW.png'
                    app.report_status.set(long_path)
                    root.update()
                    entry=app.footer_labels[-1]
                    self.assertEqual(entry.get(),long_path)
                    entry.xview_moveto(1)
                    self.assertGreater(entry.xview()[0],0)
                    entry.insert(0,'must not edit')
                    self.assertEqual(app.report_status.get(),long_path)
                    self.assertLessEqual(entry.winfo_rooty()+entry.winfo_height(),root.winfo_rooty()+height)
                    self.assertFalse(errors)
                finally:
                    app.close()


if __name__ == '__main__':
    unittest.main()

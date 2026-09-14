"""Tkinter desktop iperf3 monitor. Start with: python gui.py [--iperf PATH]."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import queue
import shlex
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except ModuleNotFoundError as exc:
    if __name__ != '__main__':
        raise
    # Install into the interpreter that actually launched this file, not an unrelated pip.
    install = [sys.executable, '-m', 'pip', 'install', '-r',
               str(Path(__file__).resolve().with_name('requirements.txt'))]
    command = subprocess.list2cmdline(install) if os.name == 'nt' else shlex.join(install)
    print(f'ERROR: Missing Python dependency: {exc.name}\n'
          f'Python interpreter: {sys.executable}\n\n'
          'Use run-gui.cmd (Windows) or run-gui.sh (Ubuntu/macOS) to select the project environment.\n'
          f'Or install dependencies with this same interpreter:\n{command}', file=sys.stderr)
    raise SystemExit(2) from None

from gui_runner import RunConfig, RunOutcome, app_directory, find_iperf, run_test
from config_store import load_config, save_config
from charting import draw_throughput
import monitor

TIME_LABELS = {'自動': 'auto', '秒': 'seconds', '分': 'minutes', '時': 'hours', '天': 'days'}

class MonitorApp:
    """Own every Tk/Matplotlib operation on the main thread; workers only enqueue data."""

    def __init__(self, root: tk.Tk, iperf: str = '', settings_path: Path | None = None):
        self.root = root
        self.settings_path = settings_path or app_directory() / 'config.json'
        load_error = None
        try:
            defaults = load_config(self.settings_path)
        except (OSError, ValueError) as exc:
            load_error = f'設定檔載入失敗：{exc}。目前顯示內建預設；原檔未變更。'
            defaults = RunConfig(iperf='')
        self.active = self.closing = self.closed = False
        self.worker = None
        self.stop_event = threading.Event()
        self.events = queue.Queue()
        self.samples = []
        self.output = None
        self.last_outcome = None
        self.config = None
        self.started_at = self.last_draw = 0.0
        self.controls = []
        self.vars = {name: tk.StringVar(value=str(value)) for name, value in {
            'iperf': iperf or defaults.iperf or find_iperf(), 'server': defaults.server, 'port': defaults.port,
            'duration': defaults.duration, 'warmup': defaults.warmup, 'threshold': defaults.threshold,
            'parallel': defaults.parallel, 'protocol': defaults.protocol, 'udp_mbps': defaults.udp_mbps,
            'output': defaults.output,
            'time_unit': next(label for label, value in TIME_LABELS.items() if value == defaults.time_unit),
            'direction': '下載：server → 本機' if defaults.reverse else '上傳：本機 → server',
        }.items()}
        self.status = tk.StringVar(value='就緒：確認設定後按「開始測速」。')
        self.path_status = tk.StringVar(value='測試紀錄與圖表會自動保存。')
        self.metrics = {key: tk.StringVar(value='—') for key in ('current', 'minimum', 'average', 'low')}
        self._build()
        self.vars['protocol'].trace_add('write', lambda *_: self._update_protocol_state())
        self.vars['time_unit'].trace_add('write', lambda *_: self._draw())
        self._update_protocol_state()
        if load_error:
            self.status.set(load_error)
            self.status_label.configure(foreground='#c6373e')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(100, self._poll)

    def _build(self):
        self.root.title('iperf3 即時速率監測')
        self.root.geometry('1160x800')
        self.root.minsize(980, 680)
        style = ttk.Style(self.root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TFrame', background='#f3f6fa')
        style.configure('TLabel', background='#f3f6fa', foreground='#182a3c')
        style.configure('Header.TLabel', font=('TkDefaultFont', 19, 'bold'))
        style.configure('Metric.TLabel', font=('TkDefaultFont', 17, 'bold'))
        style.configure('Start.TButton', padding=(18, 9), font=('TkDefaultFont', 11, 'bold'))
        style.configure('TButton', padding=(9, 5))
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill='both', expand=True)
        header = ttk.Frame(outer)
        header.pack(fill='x', pady=(0, 14))
        ttk.Label(header, text='iperf3 即時速率監測', style='Header.TLabel').pack(side='left')
        self.stop_button = ttk.Button(header, text='停止', command=self.stop, state='disabled')
        self.stop_button.pack(side='right', padx=(8, 0))
        self.start_button = ttk.Button(header, text='開始測速', command=self.start, style='Start.TButton')
        self.start_button.pack(side='right')
        self.save_button = ttk.Button(header, text='儲存設定', command=self.save_settings)
        self.save_button.pack(side='right', padx=(0, 8))
        self.controls.append((self.save_button, 'normal'))
        body = ttk.Frame(outer)
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        form = ttk.Frame(body, padding=(0, 0, 18, 0))
        form.grid(row=0, column=0, sticky='nsw')
        form.columnconfigure(0, weight=1)
        ttk.Label(form, text=f'執行環境：{platform.system()}（自動偵測）').grid(row=0, column=0, sticky='w', pady=(0, 9))
        rows = [('server', 'Server IP'), ('port', 'Port'), ('duration', '測試秒數（0＝持續）'),
                ('warmup', '忽略開始秒數'), ('threshold', '低速門檻（Mbps）'), ('parallel', '平行連線數')]
        for index, (name, label) in enumerate(rows, 1):
            box = ttk.Frame(form)
            box.grid(row=index, column=0, sticky='ew', pady=3)
            ttk.Label(box, text=label, width=19).pack(side='left')
            entry = ttk.Entry(box, textvariable=self.vars[name], width=17)
            entry.pack(side='right', fill='x', expand=True)
            self.controls.append((entry, 'normal'))
        modes = ttk.Frame(form)
        modes.grid(row=7, column=0, sticky='ew', pady=(10, 3))
        ttk.Label(modes, text='協定').grid(row=0, column=0, sticky='w')
        ttk.Label(modes, text='傳輸方向').grid(row=0, column=1, sticky='w', padx=(10, 0))
        protocol = ttk.Combobox(modes, textvariable=self.vars['protocol'], state='readonly', width=7, values=['TCP', 'UDP'])
        protocol.grid(row=1, column=0, sticky='ew')
        self.controls.append((protocol, 'readonly'))
        direction = ttk.Combobox(modes, textvariable=self.vars['direction'], state='readonly', width=23,
                                 values=['上傳：本機 → server', '下載：server → 本機'])
        direction.grid(row=1, column=1, sticky='ew', padx=(10, 0))
        self.controls.append((direction, 'readonly'))
        udp_box = ttk.Frame(form)
        udp_box.grid(row=8, column=0, sticky='ew', pady=(5, 0))
        ttk.Label(udp_box, text='UDP Mbps／每條', width=19).pack(side='left')
        self.udp_entry = ttk.Entry(udp_box, textvariable=self.vars['udp_mbps'], width=17)
        self.udp_entry.pack(side='right', fill='x', expand=True)
        self.controls.append((self.udp_entry, 'normal'))
        for row, name, label, callback in [(9, 'iperf', 'iperf3 執行檔', self._pick_iperf),
                                           (12, 'output', '結果資料夾', self._pick_output)]:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', pady=(14, 3))
            entry = ttk.Entry(form, textvariable=self.vars[name], width=36)
            entry.grid(row=row + 1, column=0, sticky='ew')
            button = ttk.Button(form, text='瀏覽…', command=callback)
            button.grid(row=row + 2, column=0, sticky='e', pady=(4, 0))
            self.controls.extend([(entry, 'normal'), (button, 'normal')])
        ttk.Label(form, text='秒數設 0：持續測試，按停止才結束。\n每秒更新，開始前 20 秒預設不報警。\n低於門檻標紅；停止後保存已收到資料。',
                  wraplength=300).grid(row=15, column=0, sticky='w', pady=(18, 0))
        self.folder_button = ttk.Button(form, text='開啟本次結果資料夾', command=self.open_output, state='disabled')
        self.folder_button.grid(row=16, column=0, sticky='ew', pady=(16, 0))

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky='nsew')
        metric_row = ttk.Frame(right)
        metric_row.pack(fill='x', pady=(0, 8))
        for key, title in [('current', '目前 Mbps'), ('minimum', '暖機後最低 Mbps'),
                           ('average', '暖機後平均 Mbps'), ('low', '低速累計秒數')]:
            card = ttk.Frame(metric_row, padding=(8, 6))
            card.pack(side='left', fill='x', expand=True)
            ttk.Label(card, text=title).pack(anchor='w')
            ttk.Label(card, textvariable=self.metrics[key], style='Metric.TLabel').pack(anchor='w')
        tabs = ttk.Notebook(right)
        tabs.pack(fill='both', expand=True)
        chart_tab, log_tab = ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(chart_tab, text='即時曲線與低速事件')
        tabs.add(log_tab, text='iperf3 原始輸出')
        chart_options = ttk.Frame(chart_tab, padding=(6, 5))
        chart_options.pack(fill='x')
        ttk.Label(chart_options, text='時間單位').pack(side='left')
        # Display-only control remains available during a measurement.
        self.time_unit_combo = ttk.Combobox(chart_options, textvariable=self.vars['time_unit'],
                                           values=list(TIME_LABELS), width=7, state='readonly')
        self.time_unit_combo.pack(side='left', padx=(8, 12))
        ttk.Label(chart_options, text='曲線連接取樣點；警示仍依原始取樣判定。').pack(side='left')
        self.figure = Figure(figsize=(8, 4.4), dpi=100, layout='constrained')
        self.ax = self.figure.subplots()
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_tab)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.tree = ttk.Treeview(chart_tab, columns=('start', 'end', 'seconds', 'minimum'), show='headings', height=5)
        for col, title in [('start', '開始（秒）'), ('end', '結束（秒）'), ('seconds', '持續（秒）'), ('minimum', '最低 Mbps')]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=105, anchor='e')
        self.tree.pack(fill='x', padx=5)
        ttk.Label(chart_tab, text='事件表顯示最近 100 次；完整事件與原始輸出皆自動存檔。').pack(anchor='w', padx=5, pady=4)
        self.log = tk.Text(log_tab, wrap='none', state='disabled', height=18)
        scroll = ttk.Scrollbar(log_tab, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.log.pack(fill='both', expand=True)
        self.progress = ttk.Progressbar(outer, mode='determinate')
        self.progress.pack(fill='x', pady=(12, 5))
        self.status_label = ttk.Label(outer, textvariable=self.status, wraplength=1050)
        self.status_label.pack(fill='x')
        ttk.Label(outer, textvariable=self.path_status, wraplength=1050).pack(fill='x', pady=(3, 0))
        self._draw()

    def _pick_iperf(self):
        selected = filedialog.askopenfilename(parent=self.root, title='選擇本機 iperf3 執行檔')
        if selected:
            self.vars['iperf'].set(selected)

    def _pick_output(self):
        selected = filedialog.askdirectory(parent=self.root, title='選擇結果資料夾')
        if selected:
            self.vars['output'].set(selected)

    def read_config(self, *, check_executable=True) -> RunConfig:
        try:
            if not self.vars['output'].get().strip():
                raise ValueError('請選擇結果資料夾。')
            return RunConfig(
                iperf=self.vars['iperf'].get(), server=self.vars['server'].get(),
                port=int(self.vars['port'].get()), duration=int(self.vars['duration'].get()),
                warmup=float(self.vars['warmup'].get()), threshold=float(self.vars['threshold'].get()),
                parallel=int(self.vars['parallel'].get()), reverse=self.vars['direction'].get().startswith('下載'),
                protocol=self.vars['protocol'].get(), udp_mbps=float(self.vars['udp_mbps'].get()),
                time_unit=self._selected_time_unit(),
                output=Path(self.vars['output'].get()),
            ).validated(check_executable=check_executable)
        except ValueError as exc:
            raise ValueError(f'設定錯誤：{exc}') from exc

    def save_settings(self):
        if self.active:
            return
        try:
            save_config(self.read_config(check_executable=False), self.settings_path)
            self.status.set(f'設定已儲存：{self.settings_path}；下次啟動會載入。')
            self.status_label.configure(foreground='#107c60')
        except (OSError, ValueError) as exc:
            self.status.set(f'儲存設定失敗：{exc}')
            self.status_label.configure(foreground='#c6373e')

    def _update_protocol_state(self):
        self.udp_entry.configure(state='normal' if not self.active and self.vars['protocol'].get() == 'UDP' else 'disabled')

    def _selected_time_unit(self):
        value = self.vars['time_unit'].get()
        return TIME_LABELS.get(value, value)

    def _set_running(self, running):
        for widget, original in self.controls:
            widget.configure(state='disabled' if running else original)
        self.start_button.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running else 'disabled')
        self._update_protocol_state()

    def start(self):
        if self.active:
            return
        try:
            config = self.read_config()
        except ValueError as exc:
            self.status.set(str(exc))
            self.status_label.configure(foreground='#c6373e')
            return
        self.config, self.samples, self.output, self.last_outcome = config, [], None, None
        self.stop_event = threading.Event()
        self.events = queue.Queue()
        self.active = True
        self.started_at = time.monotonic()
        self._set_running(True)
        self.folder_button.configure(state='disabled')
        self.progress.stop()
        self.progress.configure(mode='indeterminate' if config.duration == 0 else 'determinate',
                                maximum=config.duration or 100, value=0)
        if config.duration == 0:
            self.progress.start(80)
        for var in self.metrics.values():
            var.set('—')
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        self.status.set(f'連線中：{config.server}:{config.port} …')
        self.status_label.configure(foreground='#182a3c')
        self.path_status.set('建立本次測試資料夾…')
        self._draw()
        self.worker = threading.Thread(target=run_test, args=(config, self.stop_event, self.events), daemon=False)
        self.worker.start()

    def stop(self):
        if self.active:
            self.stop_event.set()
            self.stop_button.configure(state='disabled')
            self.status.set('停止中，正在保存已取得的資料…')

    def _append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text)
        count = int(self.log.index('end-1c').split('.')[0])
        if count > 1000:
            self.log.delete('1.0', f'{count - 1000}.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def _poll(self):
        if self.closed:
            return
        changed = False
        for _ in range(300):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'started':
                self.output = value
                self.path_status.set(f'保存位置：{value}')
            elif kind == 'line':
                self._append_log(value)
            elif kind == 'sample':
                self.samples.append(value)
                changed = True
            elif kind == 'finished':
                self._finish(value)
                changed = False
                if self.closed:
                    return
        if self.active:
            if changed:
                self._update_metrics()
                if self.config.duration != 0:
                    self.progress['value'] = self.samples[-1]['end']
            if changed and time.monotonic() - self.last_draw >= 0.4:
                self._draw()
            if not self.samples and not self.stop_event.is_set():
                self.status.set(f'等待 iperf3 輸出… {time.monotonic() - self.started_at:.0f} 秒')
        self.root.after(100, self._poll)

    def _update_metrics(self):
        summary = monitor.summarize(self.samples, 'RUNNING', None)
        if self.samples:
            latest = self.samples[-1]
            self.metrics['current'].set(f"{latest['mbps']:,.3f}")
            if self.active and not self.stop_event.is_set():
                labels = {'WARMUP': '暖機中（暫不判定）',
                          'OK': '持續測速中' if self.config.duration == 0 else '測速中', 'LOW': '低速警示'}
                self.status.set(f"{labels[latest['status']]}：{latest['start']:.2f}–{latest['end']:.2f} 秒，{latest['mbps']:.3f} Mbps")
                self.status_label.configure(foreground='#c6373e' if latest['status'] == 'LOW' else '#182a3c')
        for key, source in [('minimum', 'min_mbps'), ('average', 'average_mbps')]:
            self.metrics[key].set('—' if summary[source] is None else f'{summary[source]:,.3f}')
        self.metrics['low'].set(f"{summary['low_seconds']:.2f}")
        self.tree.delete(*self.tree.get_children())
        for event in summary['events'][-100:]:
            self.tree.insert('', 'end', values=tuple(f'{event[key]:.3f}' for key in ('start', 'end', 'seconds', 'min_mbps')))

    def _draw(self):
        self.last_draw = time.monotonic()
        config = self.config
        warmup = config.warmup if config else 20
        threshold = config.threshold if config else 100
        draw_throughput(self.ax, self.samples, warmup, threshold, self._selected_time_unit())
        self.ax.set_title(f"{config.protocol} | {'Download / receiver' if config.reverse else 'Upload / sender'} | {config.server}:{config.port}" if config else 'iperf3 live throughput', loc='left', fontsize=11)
        self.ax.grid(alpha=0.2)
        self.ax.legend(loc='upper right', fontsize=8)
        self.canvas.draw_idle()

    def _finish(self, outcome: RunOutcome):
        self.active = False
        self.progress.stop()
        if outcome.config.duration == 0:
            self.progress.configure(value=0)
        self.samples, self.output = outcome.samples, outcome.output
        # The saved static renderer runs on the same thread as the live Matplotlib canvas.
        if self.output is not None and self.output.is_dir():
            try:
                monitor.draw_plot(self.samples, outcome.summary, outcome.config, self.output,
                                  time_unit=self._selected_time_unit())
            except Exception as exc:
                outcome.summary = monitor.summarize(self.samples, 'ERROR', f'PNG 儲存失敗：{exc}')
                try:
                    monitor.save_summary(self.samples, 'ERROR', outcome.summary['error'], self.output)
                except OSError as save_error:
                    outcome.summary['error'] += f'；摘要儲存失敗：{save_error}'
            self.folder_button.configure(state='normal')
        self.last_outcome = outcome
        self._set_running(False)
        self._update_metrics()
        self._draw()
        verdict = outcome.summary['verdict']
        labels = {'PASS': '完成：通過', 'LOW': '完成：偵測到低速', 'ERROR': '錯誤', 'INTERRUPTED': '已停止', 'NO_DATA': '沒有暖機後資料'}
        self.status.set(f"{labels.get(verdict, verdict)} | 低速 {outcome.summary['low_seconds']:.2f} 秒，{len(outcome.summary['events'])} 次事件"
                        + (f" | {outcome.summary['error']}" if outcome.summary['error'] else ''))
        self.status_label.configure(foreground='#107c60' if verdict == 'PASS' else '#c6373e')
        if self.output is None or not self.output.is_dir():
            self.path_status.set('無法建立結果資料夾；請檢查設定與寫入權限。')
        else:
            self.path_status.set(f'保存位置：{self.output}')
        if self.closing:
            self._destroy()

    def open_output(self):
        if self.output is None or not self.output.is_dir():
            return
        try:
            if os.name == 'nt':
                os.startfile(self.output)
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(self.output)])
        except OSError as exc:
            self.status.set(f'無法開啟資料夾：{exc}；可手動開啟 {self.output}')

    def close(self):
        if self.active:
            self.closing = True
            self.stop()
        else:
            self._destroy()

    def _destroy(self):
        self.closed = True
        # Cancel schedules only. Each widget deletes its own callback commands on destroy;
        # root.after_cancel would wrongly delete a Matplotlib child widget's command twice.
        for job in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', job)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iperf', default='', help='Optional path to the local iperf3 executable')
    args = parser.parse_args()
    root = tk.Tk()
    MonitorApp(root, args.iperf)
    root.mainloop()


if __name__ == '__main__':
    main()

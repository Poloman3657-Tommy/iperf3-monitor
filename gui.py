"""Tkinter desktop iperf3 monitor. Start with: python gui.py [--iperf PATH]."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
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
from viewport import TimeViewport, elapsed_label
from mcs import LowEventGate, McsDispatcher, result_label, format_capture
from mcs_dialog import SshDialog
from html_report import save_report
from repeat_schedule import RepeatSchedule
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
        self.schedule = self.schedule_config = None
        self.schedule_status = tk.StringVar(value='總排程設 0：只測一輪。')
        self.worker = None
        self.stop_event = threading.Event()
        self.events = queue.Queue()
        self.samples = []
        self.output = None
        self.last_outcome = None
        self.report_worker = self.report_file = None
        self.report_pending = False
        self.report_time_unit = 'auto'
        self.report_status = tk.StringVar(value='測試結束後自動保存互動 HTML 報告。')
        self.config = None
        self.ssh_settings, self.ssh_password = defaults.ssh, ''
        self.ssh_dialog = self.dispatcher = None
        self.mcs_results = {}
        self.low_gate = LowEventGate()
        self.mcs_status = tk.StringVar(value='SSH 未啟用；IP 空白時不連線。')
        self.started_at = self.last_draw = 0.0
        self.controls = []
        self.viewport = TimeViewport()
        self.drag_origin = None
        self.drag_moved = False
        self.event_records = []
        self.tree_rows = 0
        self.view_status = tk.StringVar(value='')
        self.event_caption = tk.StringVar(value='低速事件：0 次；點選事件可放大查看。')
        self.vars = {name: tk.StringVar(value=str(value)) for name, value in {
            'iperf': iperf or defaults.iperf or find_iperf(), 'server': defaults.server, 'port': defaults.port,
            'repeat_minutes': defaults.repeat_minutes, 'total_minutes': defaults.total_minutes,
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
        self.vars['duration'].trace_add('write', lambda *_: self._update_repeat_state())
        self.vars['protocol'].trace_add('write', lambda *_: self._update_protocol_state())
        self.vars['time_unit'].trace_add('write', lambda *_: self._draw())
        self._update_protocol_state()
        self._update_repeat_state()
        if load_error:
            self.status.set(load_error)
            self.status_label.configure(foreground='#c6373e')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(100, self._poll)

    def _build(self):
        self.root.title('iperf3 即時速率監測')
        self.root.geometry('1160x840')
        self.root.minsize(980, 740)
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
        self.ssh_button = ttk.Button(header, text='SSH / Station 設定', command=self.edit_ssh)
        self.ssh_button.pack(side='right', padx=(0, 8))
        self.controls.append((self.ssh_button, 'normal'))
        body = ttk.Frame(outer)
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        form = ttk.Frame(body, padding=(0, 0, 18, 0))
        form.grid(row=0, column=0, sticky='nsw')
        form.columnconfigure(0, weight=1)
        ttk.Label(form, text=f'執行環境：{platform.system()}（自動偵測）').grid(row=0, column=0, sticky='w', pady=(0, 9))
        rows = [('server', 'Server IP'), ('port', 'Port'), ('duration', '測試秒數（0＝持續）'),
                ('repeat_minutes', '重測等待（分鐘）'), ('total_minutes', '總排程分鐘（0單次）'),
                ('warmup', '忽略開始秒數'), ('threshold', '低速門檻（Mbps）'), ('parallel', '平行連線數')]
        for index, (name, label) in enumerate(rows, 1):
            box = ttk.Frame(form)
            box.grid(row=index, column=0, sticky='ew', pady=3)
            ttk.Label(box, text=label, width=19).pack(side='left')
            entry = ttk.Entry(box, textvariable=self.vars[name], width=17)
            entry.pack(side='right', fill='x', expand=True)
            self.controls.append((entry, 'normal'))
            if name == 'repeat_minutes':
                self.repeat_entry = entry
            elif name == 'total_minutes':
                self.total_entry = entry
        modes = ttk.Frame(form)
        modes.grid(row=9, column=0, sticky='ew', pady=(10, 3))
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
        udp_box.grid(row=10, column=0, sticky='ew', pady=(5, 0))
        ttk.Label(udp_box, text='UDP Mbps／每條', width=19).pack(side='left')
        self.udp_entry = ttk.Entry(udp_box, textvariable=self.vars['udp_mbps'], width=17)
        self.udp_entry.pack(side='right', fill='x', expand=True)
        self.controls.append((self.udp_entry, 'normal'))
        for row, name, label, callback in [(11, 'iperf', 'iperf3 執行檔', self._pick_iperf),
                                           (13, 'output', '結果資料夾', self._pick_output)]:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', pady=(14, 3))
            path_box = ttk.Frame(form)
            path_box.grid(row=row + 1, column=0, sticky='ew')
            entry = ttk.Entry(path_box, textvariable=self.vars[name], width=27)
            entry.pack(side='left', fill='x', expand=True)
            button = ttk.Button(path_box, text='瀏覽…', command=callback)
            button.pack(side='right', padx=(4, 0))
            self.controls.extend([(entry, 'normal'), (button, 'normal')])
        ttk.Label(form, text='秒數設 0：持續測試，按停止才結束。\n每秒更新，開始前 20 秒預設不報警。\n低於門檻標紅；停止後保存已收到資料。',
                  wraplength=300).grid(row=15, column=0, sticky='w', pady=(18, 0))
        self.folder_button = ttk.Button(form, text='開啟本次結果資料夾', command=self.open_output, state='disabled')
        self.folder_button.grid(row=16, column=0, sticky='ew', pady=(16, 0))
        self.report_button = ttk.Button(form, text='開啟 HTML 報告', command=self.open_report, state='disabled')
        self.report_button.grid(row=17, column=0, sticky='ew', pady=(6, 0))

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
        mcs_tab = ttk.Frame(tabs)
        tabs.add(mcs_tab, text='低速 Station 資料')
        ttk.Label(mcs_tab, textvariable=self.mcs_status, wraplength=700).pack(fill='x', padx=8, pady=8)
        self.mcs_detail = tk.Text(mcs_tab, wrap='word', state='disabled', height=15)
        mcs_scroll = ttk.Scrollbar(mcs_tab, command=self.mcs_detail.yview)
        self.mcs_detail.configure(yscrollcommand=mcs_scroll.set)
        mcs_scroll.pack(side='right', fill='y')
        self.mcs_detail.pack(fill='both', expand=True)
        chart_options = ttk.Frame(chart_tab, padding=(6, 5))
        chart_options.pack(fill='x')
        ttk.Label(chart_options, text='時間單位').pack(side='left')
        # Display-only control remains available during a measurement.
        self.time_unit_combo = ttk.Combobox(chart_options, textvariable=self.vars['time_unit'],
                                           values=list(TIME_LABELS), width=7, state='readonly')
        self.time_unit_combo.pack(side='left', padx=(8, 12))
        ttk.Label(chart_options, text='滾輪縮放、左鍵拖移；點選低速事件可定位。').pack(side='left')
        navigation = ttk.Frame(chart_tab, padding=(6, 2))
        navigation.pack(fill='x')
        ttk.Button(navigation, text='＋', width=3, command=lambda: self.zoom_view(.5)).pack(side='left')
        ttk.Button(navigation, text='－', width=3, command=lambda: self.zoom_view(2)).pack(side='left', padx=3)
        self.all_button = ttk.Button(navigation, text='顯示全部', command=self.show_all)
        self.all_button.pack(side='left', padx=3)
        self.follow_button = ttk.Button(navigation, text='跟隨最新', command=self.follow_latest)
        self.follow_button.pack(side='left', padx=3)
        ttk.Label(navigation, textvariable=self.view_status).pack(side='left', padx=5)
        self.figure = Figure(figsize=(8, 4.4), dpi=100, layout='constrained')
        self.ax = self.figure.subplots()
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_tab)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.canvas.mpl_connect('scroll_event', self._on_wheel)
        self.canvas.mpl_connect('button_press_event', self._on_drag_start)
        self.canvas.mpl_connect('motion_notify_event', self._on_drag_move)
        self.canvas.mpl_connect('button_release_event', self._on_drag_end)
        self.timeline_scroll = ttk.Scrollbar(chart_tab, orient='horizontal', command=self._on_timeline_scroll)
        self.timeline_scroll.pack(fill='x', padx=6, pady=(1, 4))
        event_box = ttk.Frame(chart_tab)
        event_box.pack(fill='x', padx=5)
        self.tree = ttk.Treeview(event_box, columns=('date', 'start', 'end', 'seconds', 'minimum', 'mcs'), show='headings', height=5, selectmode='browse')
        self.tree.heading('date', text='Fail 偵測日期時間（本機）')
        self.tree.column('date', width=240, minwidth=230)
        for col, title in [('start', '開始（秒）'), ('end', '結束（秒）'), ('seconds', '持續（秒）'), ('minimum', '最低 Mbps')]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=105, anchor='e')
        self.tree.heading('mcs', text='Station TX / RX (MBit/s)')
        self.tree.column('mcs', width=175, minwidth=100)
        event_scroll = ttk.Scrollbar(event_box, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=event_scroll.set)
        event_scroll.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='x', expand=True)
        event_horizontal = ttk.Scrollbar(chart_tab, orient='horizontal', command=self.tree.xview)
        self.tree.configure(xscrollcommand=event_horizontal.set)
        event_horizontal.pack(fill='x', padx=5)
        self.tree.bind('<<TreeviewSelect>>', self._on_event_selected)
        self.tree.bind('<ButtonRelease-1>', self._on_event_clicked)
        ttk.Label(chart_tab, textvariable=self.event_caption).pack(anchor='w', padx=5, pady=4)
        self.log = tk.Text(log_tab, wrap='none', state='disabled', height=18)
        scroll = ttk.Scrollbar(log_tab, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.log.pack(fill='both', expand=True)
        self.progress = ttk.Progressbar(outer, mode='determinate')
        self.progress.pack(fill='x', pady=(12, 5))
        self.status_label = ttk.Label(outer, textvariable=self.status, wraplength=1050)
        self.status_label.pack(fill='x')
        ttk.Label(outer, textvariable=self.schedule_status, wraplength=1050).pack(fill='x', pady=(3, 0))
        ttk.Label(outer, textvariable=self.path_status, wraplength=1050).pack(fill='x', pady=(3, 0))
        ttk.Label(outer, textvariable=self.report_status, wraplength=1050).pack(fill='x', pady=(3, 0))
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
                repeat_minutes=float(self.vars['repeat_minutes'].get()) if int(self.vars['duration'].get()) != 0 else 0,
                total_minutes=float(self.vars['total_minutes'].get()) if int(self.vars['duration'].get()) != 0 else 0,
                warmup=float(self.vars['warmup'].get()), threshold=float(self.vars['threshold'].get()),
                parallel=int(self.vars['parallel'].get()), reverse=self.vars['direction'].get().startswith('下載'),
                protocol=self.vars['protocol'].get(), udp_mbps=float(self.vars['udp_mbps'].get()),
                time_unit=self._selected_time_unit(), ssh=self.ssh_settings,
                output=Path(self.vars['output'].get()),
            ).validated(check_executable=check_executable)
        except ValueError as exc:
            raise ValueError(f'設定錯誤：{exc}') from exc

    def save_settings(self):
        if self.active or self.schedule is not None:
            return
        try:
            save_config(self.read_config(check_executable=False), self.settings_path)
            self.status.set(f'設定已儲存：{self.settings_path}；下次啟動會載入。')
            self.status_label.configure(foreground='#107c60')
        except (OSError, ValueError) as exc:
            self.status.set(f'儲存設定失敗：{exc}')
            self.status_label.configure(foreground='#c6373e')

    def _update_protocol_state(self):
        self.udp_entry.configure(state='normal' if not self.active and self.schedule is None and self.vars['protocol'].get() == 'UDP' else 'disabled')

    def _update_repeat_state(self):
        try:
            enabled = int(self.vars['duration'].get()) > 0 and not self.active and self.schedule is None
        except ValueError:
            enabled = False
        for entry in (self.repeat_entry, self.total_entry):
            entry.configure(state='normal' if enabled else 'disabled')

    def _selected_time_unit(self):
        value = self.vars['time_unit'].get()
        return TIME_LABELS.get(value, value)

    def _set_running(self, running):
        running = running or self.schedule is not None
        for widget, original in self.controls:
            widget.configure(state='disabled' if running else original)
        self.start_button.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running else 'disabled')
        self._update_protocol_state()
        self._update_repeat_state()

    def edit_ssh(self):
        if self.active or self.schedule is not None or (self.dispatcher and self.dispatcher.busy):
            return
        if self.ssh_dialog and not self.ssh_dialog.closed:
            self.ssh_dialog.window.lift()
            return
        def apply(settings, password):
            self.ssh_settings, self.ssh_password = settings, password
            self.mcs_status.set(f'SSH：{settings.host}:{settings.port} / {settings.vap}' if settings.active
                                else 'SSH 未啟用；IP 空白時不連線。')
        self.ssh_dialog = SshDialog(self.root, self.ssh_settings, self.ssh_password,
                                    self.settings_path.parent / 'ssh_known_hosts', apply)

    def _show_mcs(self, result):
        self.mcs_detail.configure(state='normal')
        self.mcs_detail.delete('1.0', 'end')
        self.mcs_detail.insert('end', format_capture(result) if result else '此事件未啟用 SSH 擷取。')
        self.mcs_detail.configure(state='disabled')

    def _receive_mcs(self, result):
        index = result['event_id']
        self.mcs_results[index] = result
        item = f'event-{index}'
        if self.tree.exists(item):
            self.tree.set(item, 'mcs', result_label(result))
        self.mcs_status.set(f"事件 {index + 1}：{result_label(result)}" +
                            (f"；{result['error']}" if result.get('error') else ''))
        selected = self.tree.selection()
        if not selected or selected[0] == item:
            self._show_mcs(result)

    def start(self):
        if self.active or self.schedule is not None or self.closing or self.report_pending or self.report_worker is not None or (self.dispatcher and self.dispatcher.busy):
            return
        try:
            config = self.read_config()
            if config.ssh.active and (not self.ssh_password or any(c in self.ssh_password for c in ('\r', '\n', '\0'))):
                raise ValueError('請在「SSH / Station 設定」輸入本次 SSH/sudo 密碼（不可包含換行）。')
        except ValueError as exc:
            self.status.set(str(exc))
            self.status_label.configure(foreground='#c6373e')
            return
        if config.total_minutes > 0:
            try:
                folder = config.output / ('schedule-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
                folder.mkdir(parents=True, exist_ok=False)
            except OSError as exc:
                self.status.set(f'無法建立排程資料夾：{exc}')
                self.status_label.configure(foreground='#c6373e')
                return
            self.schedule = RepeatSchedule(config.repeat_minutes, config.total_minutes, time.monotonic())
            self.schedule_config = replace(config, output=folder)
            config = self.schedule_config
        else:
            self.schedule_status.set('持續測試：排程欄位停用。' if config.duration == 0 else '單次測試：總排程分鐘為 0。')
        self._launch_round(config)

    def _launch_round(self, config):
        if self.schedule is not None:
            now = time.monotonic()
            if self.schedule.expired(now):
                self._end_schedule('已達總時間')
                return
            self.schedule.begin_round(now)
        self.config, self.samples, self.output, self.last_outcome = config, [], None, None
        self.report_file = None
        self.report_button.configure(state='disabled')
        self.report_status.set('測試結束後自動保存互動 HTML 報告。')
        self.dispatcher = None
        self.low_gate, self.mcs_results = LowEventGate(), {}
        self._show_mcs(None)
        self.mcs_status.set('等待暖機後的低速事件。' if config.ssh.active else 'SSH 未啟用；IP 空白時不連線。')
        self.viewport.show_all()
        self.drag_origin = None
        self.event_records, self.tree_rows = [], 0
        self.tree.delete(*self.tree.get_children())
        self.event_caption.set('低速事件：0 次；點選事件可放大查看。')
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
        options = dict(stop_at=self.schedule.deadline, schedule_round=self.schedule.round_number) if self.schedule else {}
        self.worker = threading.Thread(target=run_test, args=(config, self.stop_event, self.events), kwargs=options, daemon=False)
        self.worker.start()

    def stop(self):
        self._end_schedule('已手動停止排程')
        if self.dispatcher:
            self.dispatcher.close()
        if self.active:
            self.stop_event.set()
            self.stop_button.configure(state='disabled')
            self.status.set('停止中，正在保存已取得的資料…')

    def _end_schedule(self, reason):
        if self.schedule is not None:
            self.schedule_status.set(f'{reason}；共啟動 {self.schedule.round_number} 輪。')
            self.schedule = self.schedule_config = None
            self._set_running(self.active)

    def _advance_schedule(self):
        schedule = self.schedule
        if schedule is None:
            return
        now = time.monotonic()
        if schedule.expired(now):
            if self.dispatcher:
                self.dispatcher.close()
            if not self.active:
                self._end_schedule('已達總時間')
            else:
                self.schedule_status.set('已達總時間，正在停止本輪並保存資料…')
            return
        busy = self.report_pending or self.report_worker is not None or (self.dispatcher and self.dispatcher.busy)
        if not self.active and not busy and schedule.ready(now):
            self._launch_round(self.schedule_config)
            if self.schedule is None:
                return
        remaining = max(0, schedule.deadline-now)
        stage = '測速中' if self.active else '保存報告中' if busy else f'下輪倒數 {max(0, schedule.next_due-now):.0f} 秒'
        self.schedule_status.set(f'第 {schedule.round_number} 輪｜{stage}｜總排程剩餘 {remaining/60:.2f} 分鐘')

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
                if self.config.ssh.active:
                    self.dispatcher = McsDispatcher(self.config.ssh, self.ssh_password, value, self.events,
                                                   self.settings_path.parent / 'ssh_known_hosts')
                    if self.stop_event.is_set():
                        self.dispatcher.close()
            elif kind == 'line':
                self._append_log(value)
            elif kind == 'sample':
                self.samples.append(value)
                event_id = self.low_gate.observe(value['status'], value['start'], value['end'])
                if event_id is not None and self.dispatcher:
                    self.dispatcher.submit(event_id, value)
                changed = True
            elif kind == 'mcs':
                self._receive_mcs(value)
            elif kind == 'report':
                self.report_worker = None
                self.report_file, error = value
                self.report_status.set(f'HTML 儲存失敗：{error}' if error else f'HTML 已保存：{self.report_file}')
                self.report_button.configure(state='normal' if self.report_file else 'disabled')
                if error:
                    self._end_schedule('HTML 存檔錯誤，已停止排程')
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
        if not self.active:
            self._start_report()
        self._advance_schedule()
        if not self.active:
            pending = (self.dispatcher is not None and self.dispatcher.busy) or self.report_pending or self.report_worker is not None
            self.start_button.configure(state='disabled' if pending or self.schedule else 'normal')
            self.ssh_button.configure(state='disabled' if pending or self.schedule else 'normal')
            if self.closing and not pending:
                self._destroy()
                return
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
        self.event_records = summary['events']
        # Stable row IDs preserve selection and scroll position as later events arrive.
        for index in range(max(0, self.tree_rows-1), len(self.event_records)):
            event = self.event_records[index]
            values = (event.get('detected_at', '').replace('T', ' ') or '未提供',)
            values += tuple(f'{event[key]:.3f}' for key in ('start', 'end', 'seconds', 'min_mbps'))
            values += (result_label(self.mcs_results.get(index)),)
            item = f'event-{index}'
            if self.tree.exists(item):
                self.tree.item(item, values=values)
            else:
                self.tree.insert('', 'end', iid=item, values=values)
        self.tree_rows = len(self.event_records)
        self.event_caption.set(f'低速事件：{self.tree_rows} 次（全部保留）；點選事件可放大查看。')

    def _timeline_end(self):
        return self.samples[-1]['end'] if self.samples else 60.0

    def zoom_view(self, factor, anchor=None):
        end = self._timeline_end()
        left, right = self.viewport.limits(end)
        self.viewport.zoom(factor, (left+right)/2 if anchor is None else anchor, end)
        self._draw()

    def show_all(self):
        self.viewport.show_all()
        self._draw()

    def follow_latest(self):
        self.viewport.follow_latest(self._timeline_end())
        self._draw()

    def _on_wheel(self, event):
        if event.inaxes is self.ax and event.xdata is not None:
            self.zoom_view(.8 ** max(-10, min(10, event.step)), event.xdata)

    def _on_drag_start(self, event):
        if event.inaxes is self.ax and event.button == 1:
            left, right = self.viewport.limits(self._timeline_end())
            self.drag_origin = (event.x, left, right, max(1, self.ax.bbox.width))
            self.drag_moved = False

    def _on_drag_move(self, event):
        if self.drag_origin is None or event.x is None:
            return
        pixel, left, right, width = self.drag_origin
        if abs(pixel-event.x) < 2 and not self.drag_moved:
            return
        self.drag_moved = True
        shift = (pixel-event.x) / width * (right-left)
        self.viewport.set_window(left+shift, right+shift, self._timeline_end())
        if time.monotonic() - self.last_draw >= .05:
            self._draw()

    def _on_drag_end(self, event):
        if self.drag_origin is not None:
            self._on_drag_move(event)
            self.drag_origin = None
            self.drag_moved = False
            self._draw()

    def _on_timeline_scroll(self, action, value, kind=None):
        end = self._timeline_end()
        if action == 'moveto':
            self.viewport.move_to(float(value), end)
        elif action == 'scroll':
            left, right = self.viewport.limits(end)
            self.viewport.pan(int(value) * (right-left) * (.9 if kind == 'pages' else .1), end)
        self._draw()

    def _on_event_selected(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        index = int(selected[0].split('-')[1])
        if index >= len(self.event_records):
            return
        event = self.event_records[index]
        self._show_mcs(self.mcs_results.get(index) or dict(status='DISABLED', event_id=index,
                                                        detected_at=event.get('detected_at', ''), peers=[]))
        self.viewport.focus_event(event['start'], event['end'], self._timeline_end())
        self._draw()

    def _on_event_clicked(self, event):
        # TreeviewSelect does not fire again when clicking an already selected row.
        if self.tree.identify_row(event.y) in self.tree.selection():
            self._on_event_selected()

    def _draw(self):
        self.last_draw = time.monotonic()
        config = self.config
        warmup = config.warmup if config else 20
        threshold = config.threshold if config else 100
        end = self._timeline_end()
        limits = self.viewport.limits(end)
        view = draw_throughput(self.ax, self.samples, warmup, threshold, self._selected_time_unit(), x_limits=limits)
        self.timeline_scroll.set(*self.viewport.fractions(end))
        mode = {'all': '全部', 'manual': '歷史', 'follow': '跟隨'}[self.viewport.mode]
        reduced = ' · 總覽取極值' if view['overview'] else ''
        self.view_status.set(f'{mode}｜{elapsed_label(limits[0])}–{elapsed_label(limits[1])}{reduced}')
        self.ax.set_title(f"{config.protocol} | {'Download / receiver' if config.reverse else 'Upload / sender'} | {config.server}:{config.port}" if config else 'iperf3 live throughput', loc='left', fontsize=11)
        self.ax.grid(alpha=0.2)
        self.ax.legend(loc='upper right', fontsize=8)
        self.canvas.draw_idle()

    def _finish(self, outcome: RunOutcome):
        self.active = False
        if self.schedule:
            self.schedule.finish_round(outcome.finished_at if outcome.finished_at is not None else time.monotonic())
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
        if self.schedule and outcome.summary['verdict'] not in ('PASS', 'LOW'):
            reason = '已達總時間' if self.schedule.expired(time.monotonic()) else '測試錯誤或中斷，已停止排程'
            self._end_schedule(reason)
        self.report_pending = self.output is not None and self.output.is_dir()
        self.report_time_unit = self._selected_time_unit()
        if self.report_pending:
            self.report_status.set('等待 Station 查詢完成並保存 HTML 報告…')
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

    def _start_report(self):
        if not self.report_pending or self.report_worker is not None or (self.dispatcher and self.dispatcher.busy):
            return
        self.report_pending = False
        outcome, unit, events = self.last_outcome, self.report_time_unit, self.events
        self.report_status.set('正在保存互動 HTML 報告…')
        def work():
            try:
                path = save_report(outcome.samples, outcome.summary, outcome.config, outcome.output, unit)
                events.put(('report', (path, None)))
            except Exception as exc:
                error = str(exc)
                try:
                    (outcome.output / 'html-report-error.txt').write_text(error, encoding='utf-8')
                except OSError as save_error:
                    error += f'；錯誤紀錄也無法寫入：{save_error}'
                events.put(('report', (None, error)))
        self.report_worker = threading.Thread(target=work, daemon=False)
        self.report_worker.start()

    def open_report(self):
        if not self.report_file:
            return
        try:
            if os.name == 'nt':
                os.startfile(self.report_file)
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(self.report_file)])
        except OSError as exc:
            self.report_status.set(f'無法開啟 HTML：{exc}；可手動開啟 {self.report_file}')

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
        if self.closed:
            return
        self._end_schedule('關閉視窗，已停止排程')
        if self.active:
            self.closing = True
            self.stop()
        else:
            self._destroy()

    def _destroy(self):
        if self.dispatcher:
            self.dispatcher.close()
            if self.dispatcher.busy:
                # Keep pumping Tk until the bounded connect/command writes its final record.
                self.closing = True
                self.status.set('關閉中，等待 SSH 取消結果儲存…')
                self._set_running(True)
                self.stop_button.configure(state='disabled')
                return
        if self.report_pending or self.report_worker is not None:
            self.closing = True
            self._start_report()
            self.status.set('關閉中，等待 HTML 報告儲存…')
            self._set_running(True)
            self.stop_button.configure(state='disabled')
            return
        if self.ssh_dialog and not self.ssh_dialog.closed:
            self.ssh_dialog.close()
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

"""SSH settings and a cancellable connection test; all Tk calls stay on the UI thread."""
from dataclasses import asdict
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from mcs import SshSettings, capture, format_capture


class SshDialog:
    def __init__(self, parent, settings, password, known_hosts, on_apply):
        self.window = tk.Toplevel(parent)
        self.window.title('低速事件 SSH / Station 設定')
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.known_hosts, self.on_apply = known_hosts, on_apply
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.thread = None
        self.closed = False
        self.vars = {name: (tk.BooleanVar(self.window, value=value) if name == 'enabled'
                            else tk.StringVar(self.window, value=str(value)))
                     for name, value in asdict(settings).items()}
        self.password = tk.StringVar(self.window, value=password)
        box = ttk.Frame(self.window, padding=16)
        box.pack(fill='both', expand=True)
        self.inputs = []
        enabled = ttk.Checkbutton(box, text='低速事件發生時擷取 Station 資料', variable=self.vars['enabled'])
        enabled.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
        self.inputs.append(enabled)
        for row, (name, title) in enumerate([('host', 'SSH IP（空白＝不連線）'), ('port', 'SSH Port'),
                                             ('username', 'SSH 帳號'), ('vap', 'VAP')], 1):
            ttk.Label(box, text=title).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
            entry = ttk.Entry(box, textvariable=self.vars[name], width=30)
            entry.grid(row=row, column=1, sticky='ew')
            self.inputs.append(entry)
        ttk.Label(box, text='SSH / sudo 密碼').grid(row=5, column=0, sticky='w', pady=4)
        entry = ttk.Entry(box, textvariable=self.password, show='*', width=30)
        entry.grid(row=5, column=1, sticky='ew')
        self.inputs.append(entry)
        ttk.Label(box, text='密碼只供本次執行使用，不會儲存。\n首次連線請先測試並確認設備主機指紋。',
                  wraplength=480).grid(row=6, column=0, columnspan=2, sticky='w', pady=10)
        buttons = ttk.Frame(box)
        buttons.grid(row=7, column=0, columnspan=2, sticky='ew')
        self.test_button = ttk.Button(buttons, text='測試 SSH/Station', command=self.test)
        self.test_button.pack(side='left')
        self.apply_button = ttk.Button(buttons, text='套用', command=self.apply)
        self.apply_button.pack(side='right')
        ttk.Button(buttons, text='取消 / 關閉', command=self.close).pack(side='right', padx=6)
        self.output = tk.Text(box, width=65, height=12, wrap='word', state='disabled')
        self.output.grid(row=8, column=0, columnspan=2, sticky='nsew', pady=(10, 0))
        self.job = self.window.after(100, self.poll)

    def settings(self):
        return SshSettings(**{name: (int(var.get()) if name == 'port' else var.get())
                              for name, var in self.vars.items()}).validated()

    def show(self, text):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('end', text)
        self.output.configure(state='disabled')

    def apply(self):
        try:
            settings = self.settings()
        except ValueError as exc:
            self.show(str(exc))
            return
        self.on_apply(settings, self.password.get())
        self.close()

    def test(self):
        if self.thread is not None and self.thread.is_alive():
            return
        try:
            settings = self.settings()
        except ValueError as exc:
            self.show(str(exc))
            return
        if not settings.active:
            self.show('SSH 未啟用或 IP 空白：不連線、不執行任何遠端命令。')
            return
        password = self.password.get()
        self.show('連線中… 可按「取消 / 關閉」停止。')
        for widget in [*self.inputs, self.test_button, self.apply_button]:
            widget.configure(state='disabled')

        def approve(info):
            ready, response = threading.Event(), []
            self.events.put(('host', (info, ready, response)))
            while not ready.wait(.1):
                if self.cancel.is_set():
                    return False
            return response[0] and not self.cancel.is_set()

        def work():
            self.events.put(('result', capture(settings, password, self.known_hosts, self.cancel, approve)))
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()

    def poll(self):
        if self.closed:
            return
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'host':
                info, ready, response = value
                response.append(messagebox.askyesno('確認 SSH 主機指紋',
                    f"{info['host']}\n{info['type']}\n{info['fingerprint']}\n\n請與設備的主機指紋核對。是否信任並儲存？",
                    parent=self.window))
                ready.set()
            else:
                self.show(format_capture(value))
                for widget in [*self.inputs, self.test_button, self.apply_button]:
                    widget.configure(state='normal')
        self.job = self.window.after(100, self.poll)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel.set()
        self.window.after_cancel(self.job)
        self.window.destroy()

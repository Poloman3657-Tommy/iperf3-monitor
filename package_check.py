"""Bounded loopback diagnostic for a relocated frozen app; no external server access."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback


def check_package(report_path: str) -> int:
    report = Path(report_path).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    root = app = server = None
    result = {'passed': False, 'frozen': bool(getattr(sys, 'frozen', False)),
              'executable': sys.executable}
    try:
        import tkinter as tk
        import matplotlib
        from gui import MonitorApp
        from gui_runner import app_directory, find_iperf
        from config_store import load_config

        executable = find_iperf()
        if not executable:
            raise RuntimeError('Bundled iperf3 was not found')
        result.update(iperf=executable, matplotlib=matplotlib.__version__,
                      matplotlib_path=matplotlib.__file__, app_directory=str(app_directory()))
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        server = subprocess.Popen([executable, '-s', '-1', '-B', '127.0.0.1', '-p', str(port)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        time.sleep(0.5)
        if server.poll() is not None:
            raise RuntimeError('Bundled iperf3 server could not start')
        root = tk.Tk()
        root.withdraw()
        result['tcl_library'] = root.tk.eval('info library')
        errors = []
        root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
        preferences = report.parent / 'package-test-config.json'
        app = MonitorApp(root, settings_path=preferences)
        # Use the same buttons and event loop as the normal app, in continuous download mode.
        for key, value in {'server': '127.0.0.1', 'port': port, 'duration': 0, 'warmup': 1,
                           'protocol': 'UDP', 'udp_mbps': 25, 'parallel': 1,
                           'direction': '下載：server → 本機', 'output': report.parent / 'run-data'}.items():
            app.vars[key].set(str(value))
        app.start_button.invoke()
        if not app.active:
            raise RuntimeError(app.status.get())
        deadline, pumps, stopped, units_changed = time.monotonic() + 25, 0, False, False
        while app.active and time.monotonic() < deadline:
            root.update()
            pumps += 1
            if len(app.samples) >= 2 and not units_changed:
                if app.time_unit_combo.instate(['disabled']):
                    raise RuntimeError('Time units cannot be changed during a measurement')
                app.vars['time_unit'].set('分')
                units_changed = True
            if len(app.samples) >= 4 and not stopped:
                app.stop_button.invoke()
                stopped = True
            if errors:
                raise RuntimeError('; '.join(errors))
            time.sleep(0.01)
        if app.active:
            raise TimeoutError('Package loopback diagnostic timed out')
        outcome = app.last_outcome
        if outcome is None or outcome.summary['verdict'] != 'INTERRUPTED' or len(outcome.samples) < 4:
            raise RuntimeError(f'Unexpected measurement result: {outcome}')
        if (outcome.output / 'throughput.png').stat().st_size < 10000:
            raise RuntimeError('PNG report was not generated correctly')
        raw_log = (outcome.output / 'iperf.log').read_text(encoding='utf-8')
        if 'Mbits/sec' not in raw_log or 'Kbits/sec' in raw_log:
            raise RuntimeError('Desktop raw throughput output is not in Mbits/sec')
        if not outcome.summary['low_samples']:
            raise RuntimeError('UDP throughput was not classified below the test threshold')
        if 'minutes' not in app.ax.get_xlabel() or app.ax.get_ylabel() != 'Throughput (Mbps)':
            raise RuntimeError('Time-axis conversion changed the wrong axis')
        curve = next(line for line in app.ax.lines if line.get_label() == 'Throughput curve')
        if len(curve.get_xdata()) <= len(outcome.samples) * 2:
            raise RuntimeError('Smooth throughput curve was not rendered')
        app.save_button.invoke()
        restored = load_config(preferences)
        if (restored.protocol != 'UDP' or restored.udp_mbps != 25 or restored.parallel != 1 or
                not restored.reverse or restored.time_unit != 'minutes'):
            raise RuntimeError('Saved settings did not round-trip correctly')
        result.update(passed=True, samples=len(outcome.samples), ui_event_pumps=pumps,
                      output=str(outcome.output), summary=outcome.summary, config_roundtrip=True,
                      chart_time_unit=restored.time_unit, curve_points=len(curve.get_xdata()))
        return_code = 0
    except Exception:
        result['error'] = traceback.format_exc()
        return_code = 2
    finally:
        if app is not None and not app.closed:
            app.stop()
            deadline = time.monotonic() + 8
            while app.active and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            if not app.active:
                app.close()
        elif root is not None:
            root.destroy()
        if server is not None:
            if server.poll() is None:
                server.kill()
            server.wait(timeout=5)
        report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return return_code

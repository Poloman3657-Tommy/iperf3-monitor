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
        import paramiko
        from mcs import SshSettings, parse_station
        from gui import MonitorApp
        from gui_runner import app_directory, find_iperf
        from config_store import load_config

        executable = find_iperf()
        if not executable:
            raise RuntimeError('Bundled iperf3 was not found')
        result.update(iperf=executable, matplotlib=matplotlib.__version__,
                      paramiko=paramiko.__version__,
                      matplotlib_path=matplotlib.__file__, app_directory=str(app_directory()))
        # A TCP-available ephemeral port may be reserved for UDP on Windows.
        for _ in range(32):
            with socket.socket() as probe, socket.socket(type=socket.SOCK_DGRAM) as udp_probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
                try:
                    udp_probe.bind(('127.0.0.1', port))
                except OSError:
                    continue
                break
        else:
            raise RuntimeError('No available loopback TCP/UDP port found')
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
        # Even enabled=true must never connect when the optional IP is blank.
        app.ssh_settings = SshSettings(enabled=True, host='')
        app.ssh_password = 'package-check-runtime-only'
        # Use the same buttons and event loop as the normal app, in continuous download mode.
        for key, value in {'server': '127.0.0.1', 'port': port, 'duration': 0, 'warmup': 1,
                           'protocol': 'UDP', 'udp_mbps': 25, 'parallel': 1,
                           'direction': '下載：server → 本機', 'output': report.parent / 'run-data'}.items():
            app.vars[key].set(str(value))
        app.start_button.invoke()
        if not app.active:
            raise RuntimeError(app.status.get())
        deadline, pumps, stopped, units_changed = time.monotonic() + 25, 0, False, False
        historical_view = None
        while app.active and time.monotonic() < deadline:
            root.update()
            pumps += 1
            if len(app.samples) >= 2 and not units_changed:
                if app.time_unit_combo.instate(['disabled']):
                    raise RuntimeError('Time units cannot be changed during a measurement')
                app.vars['time_unit'].set('分')
                app.zoom_view(.5, .5)
                historical_view = app.viewport.limits(app._timeline_end())
                units_changed = True
            if len(app.samples) >= 3 and historical_view is not None:
                if app.viewport.limits(app._timeline_end()) != historical_view:
                    raise RuntimeError('Incoming samples reset the historical viewport')
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
        if app.dispatcher is not None or (outcome.output / 'mcs-events.jsonl').exists():
            raise RuntimeError('Blank SSH IP unexpectedly started diagnostics')
        if parse_station('Station EA:8C:B6:92:F0:B2 (on wlan2.2)\n signal: -56 dBm\n tx bitrate: 960.7 MBit/s HE-MCS 9\n rx bitrate: 1080.6 MBit/s HE-MCS 10', 'EA:8C:B6:92:F0:B2', 'wlan2.2')['rx_bitrate'] != '1080.6 MBit/s HE-MCS 10':
            raise RuntimeError('Station parsing is incorrect')
        app.tree.selection_set('event-0')
        root.update()
        event = app.event_records[0]
        if not event.get('detected_at') or not app.tree.set('event-0', 'date').startswith(event['detected_at'][:10]):
            raise RuntimeError('Fail detection date is missing from the event table')
        left, right = app.viewport.limits(app._timeline_end())
        if not (left <= event['start'] <= event['end'] <= right):
            raise RuntimeError('Low-event selection did not focus its interval')
        if 'minutes' not in app.ax.get_xlabel() or app.ax.get_ylabel() != 'Throughput (Mbps)':
            raise RuntimeError('Time-axis conversion changed the wrong axis')
        curve = next(line for line in app.ax.lines if line.get_label() == 'Throughput curve')
        if len(curve.get_xdata()) <= len(outcome.samples) * 2:
            raise RuntimeError('Smooth throughput curve was not rendered')
        app.save_button.invoke()
        restored = load_config(preferences)
        if restored.ssh.active or not restored.ssh.enabled or 'package-check-runtime-only' in preferences.read_text(encoding='utf-8'):
            raise RuntimeError('SSH settings/password isolation failed')
        if (restored.protocol != 'UDP' or restored.udp_mbps != 25 or restored.parallel != 1 or
                not restored.reverse or restored.time_unit != 'minutes'):
            raise RuntimeError('Saved settings did not round-trip correctly')
        result.update(passed=True, samples=len(outcome.samples), ui_event_pumps=pumps,
                      output=str(outcome.output), summary=outcome.summary, config_roundtrip=True,
                      chart_time_unit=restored.time_unit, curve_points=len(curve.get_xdata()),
                      navigation_verified=True, blank_ssh_verified=True)
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

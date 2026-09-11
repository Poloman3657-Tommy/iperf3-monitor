"""Exercise real Tk event handling and iperf3 without driving desktop mouse/keyboard.

Run with --live for the authorized NUC download test; otherwise test loopback only.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import time
import tkinter as tk
from unittest.mock import patch

from gui import MonitorApp
from gui_runner import RunConfig


def available_port():
    with socket.socket() as handle:
        handle.bind(('127.0.0.1', 0))
        return handle.getsockname()[1]


def exercise(executable, name, server, port, duration, warmup=20, reverse=False,
             stop_after=None, expected='PASS', output=None, close_on_stop=False,
             protocol='TCP', udp_mbps=1000, parallel=1):
    folder = output or Path(__file__).resolve().parent / 'validation' / 'gui' / name
    root = tk.Tk()
    root.withdraw()
    app = MonitorApp(root, executable, settings_path=folder / 'config.json')
    failures = []
    root.report_callback_exception = lambda kind, value, traceback: failures.append(str(value))
    for key, value in {'server': server, 'port': port, 'duration': duration,
                       'warmup': warmup, 'output': folder,
                       'protocol': protocol, 'udp_mbps': udp_mbps, 'parallel': parallel,
                       'direction': '下載：server → 本機' if reverse else '上傳：本機 → server'}.items():
        app.vars[key].set(str(value))
    observed = []
    app.start_button.invoke()
    assert app.active, app.status.get()
    assert app.save_button.instate(['disabled'])
    assert app.udp_entry.instate(['disabled'])
    if duration == 0:
        assert str(app.progress['mode']) == 'indeterminate'
    deadline = time.monotonic() + (duration if duration else (stop_after or 30)) + 30
    pumps = 0
    stopped = False
    try:
        while app.active and time.monotonic() < deadline:
            root.update()
            pumps += 1
            if app.samples:
                observed.append(app.metrics['current'].get())
                if stop_after and len(app.samples) >= stop_after and not stopped:
                    if close_on_stop:
                        app.close()
                    else:
                        app.stop_button.invoke()
                    stopped = True
            if failures:
                raise AssertionError(failures)
            time.sleep(0.01)
        assert not app.active, 'GUI worker did not finish before deadline'
        if not app.closed:
            root.update()
        outcome = app.last_outcome
        assert outcome is not None
        if expected == 'COMPLETE':
            assert outcome.summary['verdict'] in ('PASS', 'LOW'), outcome.summary
        else:
            assert outcome.summary['verdict'] == expected, outcome.summary
        if close_on_stop:
            assert app.closed, 'Closing during measurement did not close the window'
            app.worker.join(timeout=2)
            assert not app.worker.is_alive(), 'Worker remained after closing'
        else:
            assert not app.start_button.instate(['disabled'])
            assert app.stop_button.instate(['disabled'])
        assert outcome.output is not None and outcome.output.is_dir()
        for filename in ['iperf.log', 'samples.csv', 'summary.json', 'low_events.csv', 'run.json', 'throughput.png']:
            assert (outcome.output / filename).is_file(), filename
        if outcome.samples:
            assert pumps > 50, 'Tk event loop did not remain responsive'
            assert any(value not in ('—', '') for value in observed), 'No live metric was displayed'
            assert len(app.ax.lines) >= 2, 'No live throughput curve'
        if duration == 0 and stop_after and stop_after > warmup:
            assert len(outcome.samples) >= stop_after
            assert outcome.summary['low_samples'] >= 3, 'Warm-up never finished in continuous mode'
            assert outcome.summary['events'][0]['start'] >= warmup
            assert all(s['status'] == 'WARMUP' for s in outcome.samples if s['start'] < warmup)
        if expected == 'LOW':
            assert outcome.summary['low_samples'] >= 3
            assert outcome.summary['events'][0]['start'] >= warmup
            assert app.tree.get_children(), 'Low event table did not update'
        print(json.dumps({'case': name, 'output': str(outcome.output), 'ui_event_pumps': pumps,
                          'summary': outcome.summary}, ensure_ascii=True), flush=True)
        assert not failures, failures
        return outcome
    finally:
        app.stop()
        cleanup_deadline = time.monotonic() + 10
        while app.active and time.monotonic() < cleanup_deadline:
            root.update()
            time.sleep(0.02)
        if not app.closed:
            app.close()
        if not app.active:
            assert not root.tk.call('after', 'info'), 'Closing left stale Tk callbacks'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iperf', required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--close-only', action='store_true')
    parser.add_argument('--continuous', action='store_true')
    parser.add_argument('--udp', action='store_true')
    args = parser.parse_args()
    if args.live:
        exercise(args.iperf, 'nuc-udp-download' if args.udp else 'nuc-download',
                 '192.168.137.57', 4477, 24 if args.udp else 60, reverse=True,
                 expected='LOW' if args.udp else 'COMPLETE', protocol='UDP' if args.udp else 'TCP',
                 udp_mbps=25, parallel=2 if args.udp else 1,
                 output=Path(__file__).resolve().parent / 'gui-results')
        return
    command = RunConfig.command
    if args.udp:
        cases = [('udp-download', 24, 'LOW', None)]
    elif args.continuous:
        cases = [('continuous', 0, 'INTERRUPTED', 25)]
    else:
        cases = [('close', 60, 'INTERRUPTED', 2)] if args.close_only else [('low', 24, 'LOW', None), ('stop', 60, 'INTERRUPTED', 2)]
    for name, duration, expected, stop_after in cases:
        port = available_port()
        server = subprocess.Popen([args.iperf, '-s', '-1', '-B', '127.0.0.1', '-p', str(port)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            time.sleep(0.5)
            assert server.poll() is None, 'Loopback server did not start'
            # Throttle only the controlled loopback fixture; record the actual command.
            with patch.object(RunConfig, 'command', lambda self: command(self) + ([] if self.protocol == 'UDP' else ['-b', '50M'])):
                exercise(args.iperf, name, '127.0.0.1', port, duration, expected=expected,
                         stop_after=stop_after, close_on_stop=args.close_only,
                         protocol='UDP' if args.udp else 'TCP', udp_mbps=25,
                         parallel=1, reverse=args.udp)
        finally:
            if server.poll() is None:
                server.terminate()
            server.wait(timeout=5)
    if not args.close_only and not args.continuous and not args.udp:
        exercise(args.iperf, 'connection-error', '127.0.0.1', port, 21, expected='ERROR')


if __name__ == '__main__':
    main()

"""Run iperf3 3.16, flag low throughput after warm-up, and save a PNG report."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime


INTERVAL = re.compile(
    r'^\[\s*(?P<stream>\d+|SUM)\s*\]\s+'
    r'(?P<start>\d+(?:\.\d+)?)\s*-\s*(?P<end>\d+(?:\.\d+)?)\s+sec\s+'
    r'\S+\s+[KMGT]?Bytes\s+(?P<rate>\d+(?:\.\d+)?)\s+(?P<unit>[KMGT]?)bits/sec\b'
)
FACTORS = {'': 1e-6, 'K': 1e-3, 'M': 1, 'G': 1000, 'T': 1e6}


def parse_interval(line: str, parallel: int) -> dict | None:
    """Read local periodic reports only; never count end-of-test summaries twice."""
    if re.search(r'\b(sender|receiver)\s*$', line):
        return None
    match = INTERVAL.match(line.strip())
    if not match:
        return None
    data = match.groupdict()
    if (data['stream'] == 'SUM') != (parallel > 1):
        return None
    start, end = float(data['start']), float(data['end'])
    # iperf may print a zero-length final interval due to rounding to 0.01 s.
    if end == start:
        return None
    return {'start': start, 'end': end,
            'mbps': float(data['rate']) * FACTORS[data['unit']]}


def classify(start: float, end: float, mbps: float, warmup: float, threshold: float) -> str:
    if not all(math.isfinite(x) for x in (start, end, mbps, warmup, threshold)):
        raise ValueError('Non-finite measurement or setting')
    if start < 0 or end <= start or mbps < 0 or warmup < 0 or threshold <= 0:
        raise ValueError('Invalid measurement interval or setting')
    # A crossing interval contains warm-up data; do not pretend to split its mean.
    if start < warmup:
        return 'WARMUP'
    return 'LOW' if mbps < threshold else 'OK'


def summarize(samples: list[dict], state: str, error: str | None) -> dict:
    measured = [s for s in samples if s['status'] != 'WARMUP']
    lows = [s for s in measured if s['status'] == 'LOW']
    seconds = sum(s['end'] - s['start'] for s in measured)
    events = []
    previous_low = False
    for sample in samples:
        if sample['status'] != 'LOW':
            previous_low = False
            continue
        if previous_low and abs(events[-1]['end'] - sample['start']) < 0.011:
            events[-1]['end'] = sample['end']
            events[-1]['min_mbps'] = min(events[-1]['min_mbps'], sample['mbps'])
        else:
            events.append({k: sample[k] for k in ('start', 'end')})
            events[-1]['min_mbps'] = sample['mbps']
        previous_low = True
    for event in events:
        event['seconds'] = event['end'] - event['start']
    verdict = state if state != 'COMPLETE' else ('NO_DATA' if not measured else ('LOW' if lows else 'PASS'))
    return {'verdict': verdict, 'error': error, 'sample_count': len(samples),
            'measured_samples': len(measured), 'measured_seconds': seconds,
            'low_samples': len(lows), 'low_seconds': sum(s['end'] - s['start'] for s in lows),
            'min_mbps': min((s['mbps'] for s in measured), default=None),
            'average_mbps': sum(s['mbps'] * (s['end'] - s['start']) for s in measured) / seconds if seconds else None,
            'events': events}


def draw_plot(samples: list[dict], summary: dict, args: argparse.Namespace, output: Path) -> None:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    # An isolated renderer must not switch the backend of an active Tk window.
    fig = Figure(figsize=(12, 5.5), layout='constrained')
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    if samples:
        # Each horizontal segment is an interval mean, not an instantaneous reading.
        x, y = [], []
        for s in samples:
            x.extend([s['start'], s['end'], float('nan')])
            y.extend([s['mbps'], s['mbps'], float('nan')])
        ax.plot(x, y, color='#2563eb', linewidth=1.5, label='Interval throughput')
        lows = [s for s in samples if s['status'] == 'LOW']
        ax.scatter([(s['start'] + s['end']) / 2 for s in lows], [s['mbps'] for s in lows],
                   color='#dc2626', s=22, zorder=4, label='Below threshold')
        for event in summary['events']:
            ax.axvspan(event['start'], event['end'], color='#ef4444', alpha=0.12)
    else:
        ax.text(0.5, 0.5, 'No throughput samples collected', transform=ax.transAxes, ha='center')
    ax.axvspan(0, args.warmup, color='#94a3b8', alpha=0.25, label=f'Warm-up: {args.warmup:g}s (ignored)')
    ax.axhline(args.threshold, color='#dc2626', linestyle='--', linewidth=1,
               label=f'Threshold: {args.threshold:g} Mbps')
    ax.axvline(args.warmup, color='#64748b', linestyle=':', linewidth=1)
    max_time = max([args.warmup + 1] + [s['end'] for s in samples])
    ax.set_xlim(0, max_time)
    ax.set_ylim(bottom=0)
    ax.set_xlabel('Seconds since traffic started')
    ax.set_ylabel('Throughput (Mbps)')
    direction = 'Download / local receiver' if args.reverse else 'Upload / local sender'
    minimum = f"{summary['min_mbps']:.3f}" if summary['min_mbps'] is not None else 'N/A'
    average = f"{summary['average_mbps']:.3f}" if summary['average_mbps'] is not None else 'N/A'
    ax.set_title(f"{summary['verdict']} | {args.server}:{args.port} | {direction}\n"
                 f"After warm-up: min {minimum} Mbps | mean {average} Mbps | "
                 f"low {summary['low_seconds']:.2f}s / {len(summary['events'])} events", loc='left')
    ax.grid(alpha=0.2)
    ax.legend(loc='upper right', fontsize=8)
    fig.savefig(output / 'throughput.png', dpi=160)


def save_summary(samples: list[dict], state: str, error: str | None, output: Path) -> dict:
    summary = summarize(samples, state, error)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with (output / 'low_events.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['start', 'end', 'min_mbps', 'seconds'])
        writer.writeheader()
        writer.writerows(summary['events'])
    return summary


def collect(command: list[str], args: argparse.Namespace, output: Path, *,
            stop_event: threading.Event | None = None, on_sample=None, on_line=None,
            quiet: bool = False) -> tuple[list[dict], str, str | None]:
    """Drain output on a thread so a silent or hung iperf cannot block the deadline."""
    samples, state, error = [], 'COMPLETE', None
    messages: queue.Queue = queue.Queue()
    process = None
    reader = None
    completed = False
    cancelled = False
    # iperf3 -t 0 disables its test timer; do not impose our finite-run watchdog.
    deadline = None if args.duration == 0 else time.monotonic() + args.duration + 20
    with (output / 'iperf.log').open('w', encoding='utf-8') as log, \
            (output / 'samples.csv').open('w', encoding='utf-8', newline='') as table:
        writer = csv.DictWriter(table, fieldnames=['start', 'end', 'mbps', 'status'])
        writer.writeheader()
        try:
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError('Stopped by user; report contains partial data')
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace',
                                       env={**os.environ, 'LC_ALL': 'C'},
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

            def read_output():
                try:
                    for line in process.stdout:
                        messages.put(line)
                except Exception as exc:
                    messages.put(f'iperf3: error - output reader failed: {exc}\n')
                finally:
                    messages.put(None)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            while True:
                if stop_event is not None and stop_event.is_set() and not cancelled:
                    cancelled = True
                    state, error = 'INTERRUPTED', 'Stopped by user; report contains partial data'
                    # Stop traffic first, then persist every line already in the pipe/queue.
                    if process.poll() is None:
                        process.kill()
                    deadline = time.monotonic() + 5
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError('Timed out draining stopped iperf3 output' if cancelled else
                                       'iperf3 exceeded duration + 20 seconds; partial data saved')
                try:
                    line = messages.get(timeout=0.2)
                except queue.Empty:
                    continue
                if line is None:
                    break
                log.write(line)
                log.flush()
                if on_line is not None:
                    on_line(line)
                if 'iperf3: error' in line.lower():
                    error = line.strip()
                if line.strip() == 'iperf Done.':
                    completed = True
                sample = parse_interval(line, args.parallel)
                if sample:
                    sample['status'] = classify(**sample, warmup=args.warmup, threshold=args.threshold)
                    if samples and abs(samples[-1]['end'] - sample['start']) > 0.011:
                        raise ValueError('Overlapping or missing measurement intervals; see iperf.log')
                    samples.append(sample)
                    writer.writerow(sample)
                    table.flush()
                    if on_sample is not None:
                        on_sample(sample.copy())
                    if not quiet:
                        print(f"[{sample['status']:6}] {sample['start']:8.2f}-{sample['end']:8.2f}s "
                              f"{sample['mbps']:12.3f} Mbps", flush=True)
            code = process.wait(timeout=5)
            if cancelled:
                state = 'INTERRUPTED'
            elif code != 0 or error:
                state, error = 'ERROR', error or f'iperf3 exited with code {code}'
            elif args.duration == 0:
                state, error = 'ERROR', 'Continuous test ended unexpectedly without a stop request'
            elif not completed or not samples or samples[0]['start'] > 0.011 or samples[-1]['end'] < args.duration - 0.1:
                state, error = 'ERROR', 'Incomplete test or missing interval data; see iperf.log'
        except (KeyboardInterrupt, InterruptedError):
            state, error = 'INTERRUPTED', 'Stopped by user; report contains partial data'
        except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
            state, error = 'ERROR', str(exc)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                if reader is not None:
                    reader.join(timeout=2)
                if process.stdout:
                    process.stdout.close()
    return samples, state, error


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iperf', default=r'D:\iperf3.16_64\iperf3.exe')
    parser.add_argument('--server', default='192.168.137.57')
    parser.add_argument('--port', type=int, default=4477)
    parser.add_argument('--duration', type=int, default=60, help='Total traffic seconds including warm-up; 0 runs until stopped')
    parser.add_argument('--warmup', type=float, default=20)
    parser.add_argument('--threshold', type=float, default=100, help='Mbps; strict less-than')
    parser.add_argument('--parallel', type=int, default=1)
    direction = parser.add_mutually_exclusive_group()
    direction.add_argument('-R', '--reverse', dest='reverse', action='store_true', default=False,
                           help='Reverse direction: server sends, local client receives')
    direction.add_argument('--upload', dest='reverse', action='store_false',
                           help='Local client sends, server receives (default)')
    parser.add_argument('--bitrate', type=float, default=0, help='TCP cap in Mbps per stream; 0 = unlimited')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'results')
    args = parser.parse_args()
    if not all(math.isfinite(v) for v in (args.warmup, args.threshold, args.bitrate)):
        parser.error('warmup, threshold and bitrate must be finite')
    if args.warmup < 0 or args.duration < 0 or (args.duration != 0 and args.duration < math.ceil(args.warmup) + 1):
        parser.error('duration must be 0 (continuous), or allow at least one full second after warmup')
    if args.threshold <= 0 or args.parallel < 1 or args.bitrate < 0 or not 1 <= args.port <= 65535:
        parser.error('threshold/parallel must be positive, bitrate >= 0, port 1..65535')
    if args.bitrate > 0 and (not math.isfinite(args.bitrate * 1_000_000) or round(args.bitrate * 1_000_000) < 1):
        parser.error('positive bitrate must round to at least 1 bit/s and remain finite')
    executable = shutil.which(args.iperf)
    if not executable:
        parser.error(f'iperf3 executable not found: {args.iperf}')
    args.iperf = executable
    return args


def main() -> int:
    args = arguments()
    try:
        import matplotlib  # Check before starting a network test.
    except ImportError:
        print('ERROR: Install plotting dependency: python -m pip install -r requirements.txt', file=sys.stderr)
        return 2
    output = args.output.resolve() / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    command = [args.iperf, '-c', args.server, '-p', str(args.port), '-t', str(args.duration),
               '-i', '1', '-f', 'k', '-P', str(args.parallel), '--forceflush', '--connect-timeout', '5000']
    if args.reverse:
        command.append('-R')
    if args.bitrate:
        command.extend(['-b', str(round(args.bitrate * 1_000_000))])
    try:
        output.mkdir(parents=True, exist_ok=False)
        metadata = {**vars(args), 'output': str(output), 'command': command,
                    'started_at': datetime.now().astimezone().isoformat()}
        (output / 'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        print(f'Command: {subprocess.list2cmdline(command)}\nOutput: {output}', flush=True)
        samples, state, error = collect(command, args, output)
        summary = save_summary(samples, state, error, output)
        draw_plot(samples, summary, args, output)
        print(f"\nResult: {summary['verdict']} | Low: {summary['low_samples']} intervals, "
              f"{summary['low_seconds']:.2f}s | Events: {len(summary['events'])}")
        print(f"Graph: {output / 'throughput.png'}")
        if error:
            print(f'ERROR: {error}', file=sys.stderr)
        return {'PASS': 0, 'LOW': 1, 'INTERRUPTED': 130}.get(summary['verdict'], 2)
    except Exception as exc:
        print(f'ERROR: {exc}\nAvailable artifacts: {output}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

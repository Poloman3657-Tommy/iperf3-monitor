"""Desktop measurement worker. This module never accesses Tk or a GUI widget."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import shutil
import sys
import threading

import monitor


def app_directory() -> Path:
    """User-facing files live beside the EXE, not in PyInstaller's internal runtime."""
    return Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent


def find_iperf() -> str:
    """Prefer a bundled executable, then PATH; the GUI also provides a file picker."""
    name = 'iperf3.exe' if os.name == 'nt' else 'iperf3'
    base = app_directory()
    return (shutil.which(str(base / 'iperf3' / name)) or
            shutil.which(str(base / name)) or shutil.which(name) or '')


@dataclass(frozen=True)
class RunConfig:
    iperf: str
    server: str = '192.168.137.57'
    port: int = 4477
    duration: int = 60
    warmup: float = 20
    threshold: float = 100
    parallel: int = 1
    reverse: bool = False
    output: Path = field(default_factory=lambda: app_directory() / 'gui-results')

    def validated(self) -> RunConfig:
        server = self.server.strip()
        try:
            ipaddress.ip_address(server)
        except ValueError as exc:
            raise ValueError('IP 位址不合法，請輸入 IPv4 或 IPv6。') from exc
        for name, value, minimum, maximum in (
            ('Port', self.port, 1, 65535), ('測試秒數', self.duration, 0, 86400),
            ('連線數', self.parallel, 1, 128),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f'{name} 必須是 {minimum}–{maximum} 的整數。')
        if (not math.isfinite(self.warmup) or self.warmup < 0 or
                (self.duration != 0 and self.duration < math.ceil(self.warmup) + 1)):
            raise ValueError('忽略秒數須大於或等於 0，且至少保留暖機後 1 秒。')
        if not math.isfinite(self.threshold) or not 0 < self.threshold <= 1_000_000:
            raise ValueError('門檻須大於 0，最多 1,000,000 Mbps。')
        executable = shutil.which(str(Path(self.iperf.strip()).expanduser())) if self.iperf.strip() else None
        if not executable:
            raise ValueError('找不到可執行的 iperf3，請用「瀏覽」選擇本機執行檔。')
        return replace(self, server=server, iperf=str(Path(executable).resolve()),
                       output=Path(self.output).expanduser().resolve())

    def command(self) -> list[str]:
        args = [self.iperf, '-c', self.server, '-p', str(self.port), '-t', str(self.duration),
                '-i', '1', '-f', 'k', '-P', str(self.parallel), '--forceflush', '--connect-timeout', '5000']
        return args + (['-R'] if self.reverse else [])


@dataclass
class RunOutcome:
    config: RunConfig
    output: Path | None
    samples: list[dict]
    summary: dict


def run_test(config: RunConfig, stop: threading.Event, events: queue.Queue) -> None:
    """Always publish one finished event, even if opening the output directory fails."""
    output, samples = None, []
    state, error = 'ERROR', None
    summary = None
    try:
        config = config.validated()
        output = config.output / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        output.mkdir(parents=True, exist_ok=False)
        metadata = asdict(config) | {'output': str(output), 'command': config.command(),
                                     'started_at': datetime.now().astimezone().isoformat()}
        (output / 'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        events.put(('started', output))
        samples, state, error = monitor.collect(
            config.command(), config, output, stop_event=stop, quiet=True,
            on_sample=lambda sample: events.put(('sample', sample)),
            on_line=lambda line: events.put(('line', line)),
        )
        summary = monitor.save_summary(samples, state, error, output)
    except Exception as exc:
        state, error = 'ERROR', str(exc)
        summary = monitor.summarize(samples, state, error)
        if output is not None and output.is_dir():
            try:
                monitor.save_summary(samples, state, error, output)
            except OSError as save_error:
                summary['error'] += f'; saving report also failed: {save_error}'
    finally:
        if summary is None:
            summary = monitor.summarize(samples, state, error or 'Worker ended without a result')
        events.put(('finished', RunOutcome(config, output, samples, summary)))

"""Single-file, offline measurement reports. No credentials or external resources."""
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from charting import TIME_UNITS


def station_records(output):
    path = Path(output) / 'mcs-events.jsonl'
    records = {}
    if path.exists():
        with path.open(encoding='utf-8') as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    event_id = record['event_id']
                    if type(event_id) is not int or event_id < 0:
                        raise ValueError('invalid event id')
                    records[str(event_id)] = record
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f'Station 紀錄第 {number} 行格式錯誤，無法完成 HTML 報告。') from exc
    return records


def save_report(samples, summary, config, output, time_unit=None):
    """Called after the collector/SSH writers stop; replace only a complete report."""
    output = Path(output)
    unit = time_unit or config.time_unit
    if unit not in TIME_UNITS:
        raise ValueError('Invalid HTML report time unit')
    # Explicitly select public measurement parameters; never serialize the entire app.
    settings = {key: getattr(config, key) for key in
                ('server', 'port', 'protocol', 'reverse', 'duration', 'warmup', 'threshold', 'parallel', 'udp_mbps')}
    settings['time_unit'] = unit
    settings['ssh_enabled'] = config.ssh.active
    payload = dict(version=1, generated_at=datetime.now().astimezone().isoformat(), config=settings,
                   summary=summary, station=station_records(output),
                   sample_columns=['start', 'end', 'mbps', 'status', 'observed_at'],
                   samples=[[s['start'], s['end'], s['mbps'], s['status'], s.get('observed_at', '')] for s in samples])
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    # JSON lives in a script data element: a remote </script> must never end that element.
    for char, escaped in [('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026'),
                          ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
        serialized = serialized.replace(char, escaped)
    assets = Path(__file__).resolve().parent / 'report_assets'
    page = (assets / 'report.html').read_text(encoding='utf-8')
    for marker, value in [('/* REPORT_CSS */', (assets / 'report.css').read_text(encoding='utf-8')),
                           ('/* REPORT_JS */', (assets / 'report.js').read_text(encoding='utf-8')),
                           ('/* REPORT_DATA */', serialized)]:
        if page.count(marker) != 1:
            raise ValueError(f'Missing or duplicated report marker: {marker}')
        page = page.replace(marker, value)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output,
                                         prefix='.report-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(page)
        target = output / 'report.html'
        os.replace(temporary, target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

"""Versioned JSON preferences with explicit validation and atomic replacement."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from gui_runner import RunConfig


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'設定欄位重複：{key}')
        result[key] = value
    return result


def load_config(path: Path) -> RunConfig:
    """Missing files use defaults; malformed files raise and are never overwritten."""
    path = Path(path).resolve()
    values = asdict(RunConfig(iperf='', output=path.parent / 'gui-results'))
    if not path.exists():
        return RunConfig(**values).validated(check_executable=False)
    if path.stat().st_size > 65536:
        raise ValueError('設定檔超過 64 KiB。')
    data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique_object)
    if not isinstance(data, dict):
        raise ValueError('設定檔最外層必須是 JSON object。')
    version = data.pop('version', 1)
    if type(version) is not int or version != 1:
        raise ValueError('不支援的設定檔版本。')
    unknown = data.keys() - values.keys()
    if unknown:
        raise ValueError('未知設定欄位：' + ', '.join(sorted(unknown)))
    for key in ('iperf', 'output'):
        if key in data and (not isinstance(data[key], str) or (key == 'output' and not data[key].strip())):
            raise ValueError(f'{key} 必須是有效路徑文字。')
    values.update(data)
    for key in ('iperf', 'output'):
        value = str(values[key]).strip()
        if value:
            candidate = Path(value).expanduser()
            # Bare executable names may resolve through PATH. All other relative paths
            # are relative to the config file, so moving the app folder keeps them valid.
            if not candidate.is_absolute() and (key == 'output' or '/' in value or '\\' in value):
                candidate = path.parent / candidate
            values[key] = str(candidate) if key == 'iperf' else candidate
    return RunConfig(**values).validated(check_executable=False)


def save_config(config: RunConfig, path: Path) -> None:
    """Validate first, write beside the destination, then atomically replace it."""
    path = Path(path).resolve()
    values = asdict(config.validated(check_executable=False))
    for key in ('iperf', 'output'):
        value = str(values[key])
        candidate = Path(value)
        if value and candidate.is_absolute() and candidate.is_relative_to(path.parent):
            value = candidate.relative_to(path.parent).as_posix()
            if key == 'iperf' and '/' not in value:
                value = './' + value  # Preserve a sibling executable as a path, not a PATH lookup.
        values[key] = value
    content = json.dumps({'version': 1, **values}, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, prefix=f'.{path.name}.', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

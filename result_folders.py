"""Label completed result directories without moving files while writers are active."""
import json
import os
import stat
from pathlib import Path
import tempfile


def mark_low_folder(output, summary, output_root):
    output = Path(output)
    if not summary.get('events'):
        return output
    # is_symlink alone misses Windows junctions. lstat keeps the check on the link,
    # before resolve could turn it into a different directory to be renamed.
    attributes = getattr(output.lstat(), 'st_file_attributes', 0)
    if output.is_symlink() or attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
        raise ValueError('Cannot rename a linked result directory')
    source, root = output.resolve(), Path(output_root).resolve()
    if source.parent != root:
        raise ValueError('Result directory is outside the configured output root')
    if source.name.endswith('_LOW'):
        return source
    destination = source.with_name(source.name + '_LOW')
    if destination.parent != root:
        raise ValueError('LOW destination is outside the configured output root')
    if destination.exists():
        raise FileExistsError(f'低速標記資料夾已存在，不覆寫：{destination}')
    source.rename(destination)
    return destination


def update_run_path(output):
    """Keep optional run metadata consistent after a successful directory rename."""
    path = Path(output) / 'run.json'
    if not path.exists():
        return
    metadata = json.loads(path.read_text(encoding='utf-8'))
    metadata['output'] = str(Path(output).resolve())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                         prefix='.run-',delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(metadata,handle,ensure_ascii=False,indent=2,allow_nan=False)
        os.replace(temporary,path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

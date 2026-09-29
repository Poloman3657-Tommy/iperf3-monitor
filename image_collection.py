"""Copy completed PNGs into one collection while retaining all original reports."""
from pathlib import Path
import shutil
import stat


def is_link(path):
    """Reject symlinks and Windows junction/reparse paths before following them."""
    try:
        attributes = getattr(path.lstat(), 'st_file_attributes', 0)
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def collect_image(output, image_root):
    output, root = Path(output), Path(image_root).resolve()
    source = output / 'throughput.png'
    if is_link(output) or is_link(source) or not source.resolve().is_relative_to(root):
        raise ValueError('PNG source must be a regular file inside the configured result root')
    archive = root / 'throughput-images'
    if is_link(archive):
        raise ValueError('圖檔彙整資料夾不可為符號連結或 Windows junction。')
    archive.mkdir(exist_ok=True)
    if is_link(archive) or archive.resolve().parent != root:
        raise ValueError('Image collection is outside the configured result root')
    destination = archive / (output.name + '.png')
    created = False
    try:
        with source.open('rb') as reader, destination.open('xb') as writer:
            # Exclusive creation prevents overwriting an earlier round with the same name.
            created = True
            shutil.copyfileobj(reader, writer)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)  # Only remove this call's incomplete copy.
        raise
    return destination

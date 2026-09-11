"""Archive the complete Windows runtime bundle and publish its SHA-256."""
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent
bundle = root / 'build-windows' / 'dist' / 'IperfMonitor'
required = ['IperfMonitor.exe', '_internal/python312.dll', 'iperf3/iperf3.exe',
            'iperf3/cygwin1.dll', 'README.md', 'config.json', 'build-manifest.json']
for name in required:
    if not (bundle / name).is_file():
        raise RuntimeError(f'Incomplete runtime bundle: {name}')
output = root / 'portable' / 'iperf-monitor-windows-x64.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
    for item in sorted(bundle.rglob('*')):
        if item.is_file():
            archive.write(item, arcname=Path('IperfMonitor') / item.relative_to(bundle))
with ZipFile(output) as archive:
    bad = archive.testzip()
    if bad:
        raise RuntimeError(f'ZIP verification failed: {bad}')
digest = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
print(f'{output}\nBytes: {output.stat().st_size}\nSHA256: {digest}')

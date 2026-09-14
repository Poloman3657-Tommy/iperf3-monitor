"""Build a versioned Windows ZIP and matching SHA-256; never overwrite a version."""
import argparse
import hashlib
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

REQUIRED_FILES = ['IperfMonitor.exe', '_internal/python312.dll', 'iperf3/iperf3.exe',
                  'iperf3/cygwin1.dll', 'README.md', 'config.json', 'build-manifest.json']


def normalize_version(value):
    if not re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?', value):
        raise ValueError('Version must look like v1.3.0 or v1.4.0-rc.1')
    return value if value.startswith('v') else 'v' + value


def build_archive(bundle, output_dir, version):
    version = normalize_version(version)
    bundle, output_dir = Path(bundle).resolve(), Path(output_dir).resolve()
    if output_dir.is_relative_to(bundle):
        raise ValueError('Output directory must be outside the runtime bundle')
    for name in REQUIRED_FILES:
        if not (bundle / name).is_file():
            raise RuntimeError(f'Incomplete runtime bundle: {name}')
    output = output_dir / f'iperf-monitor-windows-x64-{version}.zip'
    checksum = Path(str(output) + '.sha256')
    if output.exists() or checksum.exists():
        raise FileExistsError(f'Version already packaged: {output}')
    output_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'x', compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(bundle.rglob('*')):
            if item.is_file():
                archive.write(item, arcname=Path(f'IperfMonitor-{version}') / item.relative_to(bundle))
    with ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f'ZIP verification failed: {bad}')
    with output.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    with checksum.open('x', encoding='ascii') as handle:
        handle.write(f'{digest}  {output.name}\n')
    return output


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, help='Release version, e.g. v1.3.0')
    parser.add_argument('--bundle', type=Path, default=root / 'build-windows' / 'dist' / 'IperfMonitor')
    parser.add_argument('--output-dir', type=Path, default=root / 'portable')
    args = parser.parse_args()
    output = build_archive(args.bundle, args.output_dir, args.version)
    print(f'{output}\nBytes: {output.stat().st_size}')


if __name__ == '__main__':
    main()

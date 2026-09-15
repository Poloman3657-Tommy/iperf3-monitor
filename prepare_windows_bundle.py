"""Add user-provided iperf3, dependency notices, and a manifest to the Windows bundle."""
from datetime import datetime
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import shutil
import sys
from urllib.request import urlopen

root = Path(__file__).resolve().parent
bundle = root / 'build-windows' / 'dist' / 'IperfMonitor'
if not (bundle / 'IperfMonitor.exe').is_file():
    raise RuntimeError('Build build-windows.spec with PyInstaller first')
vendor = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r'D:\iperf3.16_64')
target = bundle / 'iperf3'
target.mkdir(exist_ok=True)
vendor_names = ['iperf3.exe', 'cygwin1.dll', 'cygcrypto-3.dll', 'cygz.dll']
for name in vendor_names:
    shutil.copy2(vendor / name, target / name)
shutil.copy2(root / 'Windows-README.md', bundle / 'README.md')
shutil.copy2(root / 'config.example.json', bundle / 'config.json')
licenses = bundle / 'licenses'
licenses.mkdir(exist_ok=True)
versions = {}
packages = ['matplotlib', 'numpy', 'pillow', 'contourpy', 'cycler', 'fonttools',
            'kiwisolver', 'packaging', 'pyparsing', 'python-dateutil', 'six', 'PyInstaller',
            'paramiko', 'bcrypt', 'cryptography', 'invoke', 'pynacl', 'cffi', 'pycparser']
for name in packages:
    dist = distribution(name)
    versions[name] = dist.version
    for item in dist.files or []:
        if '.dist-info' not in str(item):
            continue
        if 'license' not in str(item).lower() and not Path(item).name.lower().startswith(('copying', 'notice')):
            continue
        source = Path(dist.locate_file(item))
        if source.is_file():
            destination = licenses / name / Path(*Path(item).parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
for source in (Path(sys.base_prefix) / 'tcl').rglob('license.terms'):
    destination = licenses / ('TclTk-' + source.parent.name + '-license.terms')
    shutil.copy2(source, destination)
remote = {
    'iperf3-LICENSE.txt': 'https://raw.githubusercontent.com/esnet/iperf/3.16/LICENSE',
    'OpenSSL-LICENSE.txt': 'https://raw.githubusercontent.com/openssl/openssl/openssl-3.0.12/LICENSE.txt',
    'zlib-LICENSE.html': 'https://www.zlib.net/zlib_license.html',
    'Cygwin-LICENSING.html': 'https://cygwin.com/licensing.html',
    'LGPL-3.0.txt': 'https://www.gnu.org/licenses/lgpl-3.0.txt',
    'GPL-3.0.txt': 'https://www.gnu.org/licenses/gpl-3.0.txt',
}
cache = root / 'packaging-licenses'
cache.mkdir(exist_ok=True)
for name, url in remote.items():
    cached = cache / name
    if not cached.exists():
        with urlopen(url, timeout=30) as response:
            cached.write_bytes(response.read())
    shutil.copy2(cached, licenses / name)
    print('License:', name)
sources = ['desktop_entry.py', 'package_check.py', 'gui.py', 'gui_runner.py', 'config_store.py',
           'html_report.py', 'report_assets/report.html', 'report_assets/report.css', 'report_assets/report.js',
           'config.example.json', 'charting.py', 'viewport.py', 'monitor.py', 'mcs.py', 'mcs_dialog.py', 'build-windows.spec']
manifest = {
    'built_at': datetime.now().astimezone().isoformat(), 'platform': 'Windows x64',
    'python': sys.version, 'dependencies': versions,
    'source_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sources},
    'iperf3_sha256': {name: hashlib.sha256((target / name).read_bytes()).hexdigest() for name in vendor_names},
}
(bundle / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
notice = ['# Third-party components', '', f'Python: {sys.version.split()[0]}', '',
          'Runtime components retain their upstream licenses in licenses/ and _internal/.',
          'iperf3.exe and its three Cygwin DLLs were copied unchanged from the user-provided iperf3 3.16 directory.',
          'iperf3 source: https://github.com/esnet/iperf/tree/3.16',
          'Cygwin 3.4.10 source: https://github.com/cygwin/cygwin/tree/cygwin-3_4_10-release',
          'Cygwin licensing: https://cygwin.com/licensing.html',
          'OpenSSL source: https://github.com/openssl/openssl',
          'zlib source: https://github.com/madler/zlib', '', '## Python packages', '']
notice.extend(f'- {name}: {version}' for name, version in versions.items())
(bundle / 'THIRD-PARTY-NOTICES.md').write_text('\n'.join(notice) + '\n', encoding='utf-8')
print('Prepared:', bundle)

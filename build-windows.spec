# PyInstaller recipe. Build on Windows using the project's Python environment.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'desktop_entry.py')],
    pathex=[str(root)],
    binaries=[], datas=[], hiddenimports=[], hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['TkAgg', 'Agg']}},
    runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='IperfMonitor',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='IperfMonitor')

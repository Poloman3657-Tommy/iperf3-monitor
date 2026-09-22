"""Bundle portable desktop source without machine-specific environments or test data."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent
files = ['gui.py', 'gui_runner.py', 'repeat_schedule.py', 'html_report.py', 'report_assets/report.html', 'report_assets/report.css', 'report_assets/report.js', 'mcs.py', 'mcs_dialog.py', 'charting.py', 'viewport.py', 'config_store.py', 'config.example.json', 'monitor.py', 'requirements.txt',
         'run-gui.cmd', 'run-gui.sh', 'GUI-README.md', 'Windows-README.md']
output = root / 'portable' / 'iperf-monitor-python-gui.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(root / name, arcname=f'iperf-monitor-gui/{name}')
    archive.write(root / 'config.example.json', arcname='iperf-monitor-gui/config.json')
with ZipFile(output) as archive:
    if archive.testzip() is not None or len(archive.namelist()) != len(files) + 1:
        raise RuntimeError('Package verification failed')
print(output)

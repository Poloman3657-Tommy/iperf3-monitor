"""Verify actual Tk settings controls without touching the user's config.json."""
import argparse
import json
from pathlib import Path
import tempfile
import tkinter as tk

from gui import MonitorApp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iperf', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='iperf-config-gui-') as folder:
        path = Path(folder) / 'config.json'
        root = tk.Tk(); root.withdraw()
        app = MonitorApp(root, args.iperf, settings_path=path)
        assert app.udp_entry.instate(['disabled'])
        for key, value in {'server': '10.0.0.2', 'port': 5201, 'duration': 0, 'parallel': 2,
                           'protocol': 'UDP', 'udp_mbps': 25, 'direction': '下載：server → 本機',
                           'output': Path(folder) / 'results', 'time_unit': '天'}.items():
            app.vars[key].set(str(value))
        assert not app.udp_entry.instate(['disabled'])
        app.save_button.invoke()
        assert path.is_file(), app.status.get()
        assert json.loads(path.read_text(encoding='utf-8'))['protocol'] == 'UDP'
        app.close()

        root = tk.Tk(); root.withdraw()
        app = MonitorApp(root, settings_path=path)
        loaded = app.read_config()
        assert loaded.server == '10.0.0.2' and loaded.port == 5201
        assert loaded.protocol == 'UDP' and loaded.udp_mbps == 25 and loaded.parallel == 2
        assert loaded.duration == 0 and loaded.reverse
        assert loaded.time_unit == 'days'
        assert not app.udp_entry.instate(['disabled'])
        app.vars['protocol'].set('TCP')
        assert app.udp_entry.instate(['disabled'])
        app.close()

        path.write_text('{broken json', encoding='utf-8')
        root = tk.Tk(); root.withdraw()
        app = MonitorApp(root, args.iperf, settings_path=path)
        assert '載入失敗' in app.status.get()
        assert path.read_text(encoding='utf-8') == '{broken json'
        app.close()
    print('PASS: save button, restart/load, UDP control state, and invalid JSON preservation.')


if __name__ == '__main__':
    main()

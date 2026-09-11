"""Persistent settings must survive relocation and failed saves without data loss."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gui_runner import RunConfig


class ConfigStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('config_store'), 'Settings storage is not implemented')
        import config_store
        self.store = config_store

    def test_missing_file_and_partial_settings_have_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            config = self.store.load_config(path)
            self.assertEqual(config.protocol, 'TCP')
            self.assertEqual(config.port, 4477)
            self.assertFalse(path.exists())
            path.write_text('{"server":"10.0.0.2","port":5201,"protocol":"udp","duration":0}', encoding='utf-8')
            config = self.store.load_config(path)
            self.assertEqual(config.server, '10.0.0.2')
            self.assertEqual(config.protocol, 'UDP')
            self.assertEqual(config.duration, 0)
            self.assertEqual(config.warmup, 20)

    def test_saved_paths_stay_relative_and_relocatable(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            one, two = base / 'first', base / 'relocated'
            one.mkdir(); two.mkdir()
            cfg = RunConfig(iperf=str(one / 'iperf3' / 'iperf3.exe'), output=one / 'gui-results',
                            protocol='UDP', udp_mbps=25, reverse=True, parallel=2, duration=0)
            self.store.save_config(cfg, one / 'config.json')
            raw = (one / 'config.json').read_text(encoding='utf-8')
            data = json.loads(raw)
            self.assertEqual(data['iperf'], 'iperf3/iperf3.exe')
            self.assertEqual(data['output'], 'gui-results')
            (two / 'config.json').write_text(raw, encoding='utf-8')
            loaded = self.store.load_config(two / 'config.json')
            self.assertEqual(Path(loaded.iperf), two / 'iperf3' / 'iperf3.exe')
            self.assertEqual(loaded.output, two / 'gui-results')
            self.assertEqual(loaded.udp_mbps, 25)
            self.assertTrue(loaded.reverse)

    def test_bad_settings_are_rejected_without_overwriting_them(self):
        examples = ['{', '[]', '{"reverse":"false"}', '{"port":true}',
                    '{"protocol":"SCTP"}', '{"udp_mbps":0}', '{"udp_mbps":NaN}',
                    '{"version":2}', '{"typo":1}', '{"port":4477,"port":5201}']
        examples.extend(json.dumps({key: 10 ** 400}) for key in ('threshold', 'warmup', 'udp_mbps'))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            for text in examples:
                with self.subTest(text=text):
                    path.write_text(text, encoding='utf-8')
                    with self.assertRaises(ValueError):
                        self.store.load_config(path)
                    self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_executable_beside_config_keeps_explicit_relative_path(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            self.store.save_config(RunConfig(iperf=str(base / 'iperf3.exe')), base / 'config.json')
            self.assertEqual(json.loads((base / 'config.json').read_text())['iperf'], './iperf3.exe')
            self.assertEqual(Path(self.store.load_config(base / 'config.json').iperf), base / 'iperf3.exe')

    def test_failed_atomic_save_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            cfg = self.store.load_config(path)
            self.store.save_config(cfg, path)
            previous = path.read_bytes()
            with patch('config_store.os.replace', side_effect=PermissionError('read only')):
                with self.assertRaises(OSError):
                    self.store.save_config(replace(cfg, port=5201), path)
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual([p.name for p in path.parent.iterdir()], ['config.json'])


if __name__ == '__main__':
    unittest.main()

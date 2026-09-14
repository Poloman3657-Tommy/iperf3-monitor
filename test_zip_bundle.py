"""Versioned packages keep their payload and checksum names consistent."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile


class VersionedBundleTests(unittest.TestCase):
    def test_version_normalization_rejects_paths_and_ambiguous_names(self):
        import zip_windows_bundle as bundle
        self.assertEqual(bundle.normalize_version('1.3.0'), 'v1.3.0')
        self.assertEqual(bundle.normalize_version('v1.4.0-rc.1'), 'v1.4.0-rc.1')
        for bad in ['../1.3.0', 'v1', 'v01.3.0', '1.3.0/other']:
            with self.assertRaises(ValueError):
                bundle.normalize_version(bad)

    def test_archive_root_filename_and_checksum_include_version(self):
        import zip_windows_bundle as bundle
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'app'
            for name in bundle.REQUIRED_FILES:
                item = source / name
                item.parent.mkdir(parents=True, exist_ok=True)
                item.write_bytes(('payload:' + name).encode())
            output = bundle.build_archive(source, root / 'out', 'v1.3.0')
            self.assertEqual(output.name, 'iperf-monitor-windows-x64-v1.3.0.zip')
            with ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                for name in bundle.REQUIRED_FILES:
                    self.assertEqual(archive.read('IperfMonitor-v1.3.0/' + name), (source / name).read_bytes())
            expected = hashlib.sha256(output.read_bytes()).hexdigest()
            self.assertEqual(Path(str(output) + '.sha256').read_text().strip(), expected + '  ' + output.name)
            with self.assertRaises(FileExistsError):
                bundle.build_archive(source, root / 'out', 'v1.3.0')


if __name__ == '__main__':
    unittest.main()

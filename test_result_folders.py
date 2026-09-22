"""Low-event labels preserve data and cannot rename outside a run's output root."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class ResultFolderTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('result_folders'), 'Folder marking missing')
        import result_folders
        self.module = result_folders

    def test_low_events_mark_even_interrupted_runs_and_update_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root/'20260922-123000-123456'
            original.mkdir()
            (original/'run.json').write_text(json.dumps(dict(output=str(original),server='192.0.2.1')),encoding='utf-8')
            (original/'samples.csv').write_bytes(b'unchanged data')
            marked = self.module.mark_low_folder(original, dict(verdict='INTERRUPTED',events=[dict(start=20,end=21)]),root)
            self.assertEqual(marked.name,original.name+'_LOW')
            self.assertFalse(original.exists())
            self.assertEqual((marked/'samples.csv').read_bytes(),b'unchanged data')
            self.module.update_run_path(marked)
            self.assertEqual(json.loads((marked/'run.json').read_text())['output'],str(marked))
            self.assertEqual(self.module.mark_low_folder(marked,dict(events=[{}]),root),marked)

    def test_no_low_does_not_mark_and_collision_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); original=root/'run'; original.mkdir()
            self.assertEqual(self.module.mark_low_folder(original,dict(events=[]),root),original)
            existing=root/'run_LOW'; existing.mkdir(); (existing/'keep').write_text('keep')
            with self.assertRaises(FileExistsError):
                self.module.mark_low_folder(original,dict(events=[{}]),root)
            self.assertTrue(original.exists())
            self.assertEqual((existing/'keep').read_text(),'keep')

    def test_wrong_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); output=root/'elsewhere'; output.mkdir()
            with self.assertRaises(ValueError):
                self.module.mark_low_folder(output,dict(events=[{}]),root/'expected')
            self.assertTrue(output.exists())

    def test_windows_reparse_directory_is_rejected_before_resolving_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); output=root/'run'; output.mkdir()
            with patch.object(Path,'is_symlink',return_value=False), patch.object(Path,'lstat',return_value=SimpleNamespace(st_file_attributes=0x400)):
                with self.assertRaises(ValueError):
                    self.module.mark_low_folder(output,dict(events=[{}]),root)
            self.assertTrue(output.exists())


if __name__ == '__main__':
    unittest.main()

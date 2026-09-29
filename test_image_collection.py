"""Image collection is additive, uses final folder names and never overwrites data."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class ImageCollectionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('image_collection'), 'Image collector missing')
        import image_collection
        self.module = image_collection

    def test_scheduled_and_single_rounds_share_root_collection_with_final_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for relative in ('20260929-120000_LOW', 'schedule-20260929/20260929-121000'):
                output=root/relative; output.mkdir(parents=True)
                source=output/'throughput.png'; source.write_bytes(b'original PNG data')
                result=self.module.collect_image(output,root)
                self.assertEqual(result,root/'throughput-images'/(output.name+'.png'))
                self.assertEqual(result.read_bytes(),source.read_bytes())
                self.assertTrue(source.exists(),'The original must be retained')

    def test_collision_keeps_previous_image_and_missing_source_fails_loudly(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); output=root/'run'; output.mkdir()
            with self.assertRaises(FileNotFoundError):
                self.module.collect_image(output,root)
            (output/'throughput.png').write_bytes(b'first')
            target=self.module.collect_image(output,root)
            (output/'throughput.png').write_bytes(b'second')
            with self.assertRaises(FileExistsError):
                self.module.collect_image(output,root)
            self.assertEqual(target.read_bytes(),b'first')

    def test_copy_failure_removes_only_incomplete_copy_and_retains_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); output=root/'run'; output.mkdir()
            source=output/'throughput.png'; source.write_bytes(b'original')
            def disk_full(reader,writer):
                writer.write(b'partial')
                raise OSError('disk full')
            with patch('image_collection.shutil.copyfileobj',side_effect=disk_full):
                with self.assertRaisesRegex(OSError,'disk full'):
                    self.module.collect_image(output,root)
            self.assertFalse((root/'throughput-images'/'run.png').exists())
            self.assertEqual(source.read_bytes(),b'original')

    def test_archive_directory_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); output=root/'run'; output.mkdir()
            (output/'throughput.png').write_bytes(b'original')
            with patch('image_collection.is_link',side_effect=lambda p:p.name=='throughput-images'):
                with self.assertRaises(ValueError):
                    self.module.collect_image(output,root)


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis import qa_smoke_test as qa


class LiveExitCodes(unittest.TestCase):
    def test_missing_runtime_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(qa.run_live_test(root / 'missing.exe', root, 1), 2)

    def test_missing_assets_are_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / 'runtime.exe'
            exe.touch()
            with patch.object(qa, 'GAME_DUMP_LOCAL', root / 'fallback'):
                self.assertEqual(qa.run_live_test(exe, root / 'dump', 1), 2)


if __name__ == '__main__':
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.environment import load_environment


class EnvironmentTests(unittest.TestCase):
    def test_root_env_precedes_legacy_server_env_and_is_cwd_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "server").mkdir()
            (root / ".env").write_text("HENRIK_API_KEY=root-key\nHENRIK_ML_API_KEY=ml-key\n", encoding="utf-8")
            (root / "server" / ".env").write_text("HENRIK_API_KEY=legacy-key\nDB_NAME=legacy-db\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                load_environment(root)
                self.assertEqual(os.environ["HENRIK_API_KEY"], "root-key")
                self.assertEqual(os.environ["HENRIK_ML_API_KEY"], "ml-key")
                self.assertEqual(os.environ["DB_NAME"], "legacy-db")
                load_environment(root)
                self.assertEqual(os.environ["HENRIK_API_KEY"], "root-key")

    def test_process_environment_has_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".env").write_text("HENRIK_API_KEY=root-key\n", encoding="utf-8")
            with patch.dict(os.environ, {"HENRIK_API_KEY": "process-key"}, clear=True):
                load_environment(root)
                self.assertEqual(os.environ["HENRIK_API_KEY"], "process-key")

    def test_existing_server_env_still_works_without_root_env(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "server").mkdir()
            (root / "server" / ".env").write_text("HENRIK_API_KEY=legacy-key\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                load_environment(root)
                self.assertEqual(os.environ["HENRIK_API_KEY"], "legacy-key")


if __name__ == "__main__":
    unittest.main()

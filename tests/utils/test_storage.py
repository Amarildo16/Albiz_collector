from __future__ import annotations

import os
import unittest
from pathlib import Path

from albiz_collector.utils.storage import read_storage_bytes, resolve_storage_path
from tests.support import fixture_path, isolated_db_environment


class StorageResolutionTests(unittest.TestCase):
    def test_resolve_storage_path_recovers_project_relative_paths_outside_repo_cwd(self) -> None:
        original_cwd = Path.cwd()

        with isolated_db_environment() as (temp_dir, _, _):
            try:
                os.chdir(temp_dir)
                resolved = resolve_storage_path("tests/fixtures/normalization/app_procurement_rows.csv")
                content = read_storage_bytes("tests/fixtures/normalization/app_procurement_rows.csv")
            finally:
                os.chdir(original_cwd)

        fixture = fixture_path("normalization", "app_procurement_rows.csv").resolve()
        self.assertEqual(resolved, fixture)
        self.assertEqual(content, fixture.read_bytes())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import ast
import importlib.util
import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from shutil import copy2, rmtree
from unittest.mock import patch
from uuid import uuid4

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "src" / "albiz_collector" / "config.py"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
TMP_ROOT = PROJECT_ROOT / "tests" / ".tmp" / "config"
ENV_HELPERS = {
    "_env_bool",
    "_env_csv_ints",
    "_env_database_url",
    "_env_int",
    "_env_path",
}


@contextmanager
def _workspace_temp_dir(prefix: str):
    path = TMP_ROOT / f"{prefix}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path.resolve()
    finally:
        rmtree(path, ignore_errors=True)


@contextmanager
def _temporary_cwd(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


@contextmanager
def _loaded_config_from_project_copy(project_root: Path):
    config_dir = project_root / "src" / "albiz_collector"
    config_dir.mkdir(parents=True, exist_ok=True)
    copied_config = config_dir / "config.py"
    copy2(CONFIG_PATH, copied_config)

    module_name = f"_config_under_test_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, copied_config)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load copied config module")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(module_name, None)


def _env_names_read_by_config() -> set[str]:
    tree = ast.parse(CONFIG_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue

        first_arg = node.args[0]
        if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
            continue

        if isinstance(node.func, ast.Attribute) and node.func.attr == "getenv":
            names.add(first_arg.value)
        elif isinstance(node.func, ast.Name) and node.func.id in ENV_HELPERS:
            names.add(first_arg.value)

    return names


class ConfigEnvironmentTests(unittest.TestCase):
    def test_config_imports_without_dotenv_file(self) -> None:
        with _workspace_temp_dir("project") as project_root:
            with patch.dict(os.environ, {}, clear=True):
                with _loaded_config_from_project_copy(project_root) as config:
                    self.assertEqual(config.PROJECT_ROOT, project_root)
                    self.assertEqual(config.settings.app_env, "development")
                    self.assertEqual(
                        config.settings.database_url,
                        "mysql+pymysql://root@localhost/albiz_collector",
                    )
                    self.assertEqual(
                        config.settings.raw_storage_dir,
                        project_root / "data" / "raw",
                    )

    def test_config_loads_project_root_dotenv_from_outside_cwd(self) -> None:
        with _workspace_temp_dir("project") as project_root:
            with _workspace_temp_dir("outside-cwd") as outside_cwd:
                (project_root / ".env").write_text(
                    "\n".join(
                        [
                            "APP_ENV=test-env",
                            "DATABASE_URL=sqlite:///./relative.sqlite3",
                            "RAW_STORAGE_DIR=relative/raw",
                            "HTTP_TIMEOUT_SECONDS=7",
                            "APP_EXPORT_YEARS=2024,2025",
                            "QKB_SEARCH_NIPT_SELECTOR=.nipt",
                        ]
                    ),
                    encoding="utf-8",
                )

                with patch.dict(os.environ, {}, clear=True):
                    with _temporary_cwd(outside_cwd):
                        with _loaded_config_from_project_copy(project_root) as config:
                            expected_db_path = (
                                project_root / "relative.sqlite3"
                            ).as_posix()

                            self.assertEqual(config.settings.app_env, "test-env")
                            self.assertEqual(
                                config.settings.database_url,
                                f"sqlite:///{expected_db_path}",
                            )
                            self.assertEqual(
                                config.settings.raw_storage_dir,
                                project_root / "relative" / "raw",
                            )
                            self.assertEqual(config.settings.http_timeout_seconds, 7)
                            self.assertEqual(config.settings.app_export_years, [2024, 2025])
                            self.assertEqual(config.settings.qkb_search_nipt_selector, ".nipt")

    def test_env_example_matches_config_env_usage(self) -> None:
        env_names = _env_names_read_by_config()
        example_values = dotenv_values(ENV_EXAMPLE_PATH, encoding="utf-8")
        example_names = set(example_values)

        self.assertEqual(env_names, example_names)
        self.assertNotIn("password", (example_values["DATABASE_URL"] or "").lower())

    def test_env_example_can_be_loaded_as_project_dotenv(self) -> None:
        with _workspace_temp_dir("project") as project_root:
            copy2(ENV_EXAMPLE_PATH, project_root / ".env")

            with patch.dict(os.environ, {}, clear=True):
                with _loaded_config_from_project_copy(project_root) as config:
                    self.assertEqual(config.settings.database_url, config.DEFAULT_DATABASE_URL)
                    self.assertEqual(
                        config.settings.raw_storage_dir,
                        project_root / "data" / "raw",
                    )
                    self.assertEqual(config.settings.http_timeout_seconds, 30)


if __name__ == "__main__":
    unittest.main()

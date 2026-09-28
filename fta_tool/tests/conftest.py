"""Shared pytest configuration.

* The app's database engine is bound to a temporary directory. app/database.py
  uses the relative URL sqlite:///./fta_tool.db, which SQLAlchemy turns into
  an absolute path when the engine is created (at import), and TestClient
  runs the app's startup (create_all, migrations) on it. Importing
  app.database here, with a temporary working directory, keeps a test run
  started from fta_tool/ away from the user's database file. The working
  directory is restored right away.
* Options, markers and hooks for the real-browser tests in tests/e2e
  (J-26, plan 5.9.6). See tests/e2e/README.md:
    pytest                                  normal run (E2E skipped if the
                                            browser is not installed)
    pytest -m e2e --e2e-required            required acceptance run
      [--e2e-env LABEL] [--e2e-report PATH] (FTA_E2E_REQUIRED=1 also works)
"""

import importlib
import os
import shutil
import sys
import tempfile
import warnings

import pytest

from tests.e2e import acceptance


def _bind_app_database_to_temporary_directory():
    if "app.database" in sys.modules:
        warnings.warn("app.database was imported before tests/conftest.py; the test database is not isolated")
        return None
    previous = os.getcwd()
    workdir = tempfile.mkdtemp(prefix="fta-pytest-db-")
    os.chdir(workdir)
    try:
        importlib.import_module("app.database")  # the engine resolves ./fta_tool.db here
    finally:
        os.chdir(previous)
    return workdir


_TEST_DB_DIR = _bind_app_database_to_temporary_directory()


def pytest_unconfigure(config):
    if _TEST_DB_DIR:
        import app.database

        app.database.engine.dispose()
        shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


def pytest_addoption(parser):
    group = parser.getgroup("fta-e2e", "FTA: 実ブラウザテスト（UI改修の受入検証）")
    group.addoption(
        "--e2e-required",
        action="store_true",
        default=False,
        help="UI改修の必須受入検証として実行する。E2E のスキップを失敗として扱い、"
        "必須の受入項目が未実施なら失敗にする（環境変数 FTA_E2E_REQUIRED=1 でも同じ）。",
    )
    group.addoption(
        "--e2e-report",
        default=None,
        metavar="PATH",
        help="E2E の実行記録（Markdown）を書き出すパス。",
    )
    group.addoption(
        "--e2e-env",
        default=None,
        metavar="LABEL",
        help="記録に残す実行環境の区分（例：開発環境、検証環境、CI）。環境変数 FTA_E2E_ENV でも指定できる。",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: 実ブラウザ（Playwright・Chromium）で画面を操作するテスト")
    config.addinivalue_line(
        "markers", "acceptance(*ids): 受入確認の項目ID（計画 第8.9節の E-xx、または PR1-xx）"
    )
    acceptance.configure(config)


def pytest_collection_modifyitems(config, items):
    acceptance.on_collection_modifyitems(config, items)


def pytest_deselected(items):
    if items:
        acceptance.on_deselected(items[0].config, items)


def pytest_collection_finish(session):
    acceptance.on_collection_finish(session)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    acceptance.on_report(item, outcome.get_result())


def pytest_sessionfinish(session, exitstatus):
    acceptance.on_session_finish(session)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    acceptance.terminal_summary(terminalreporter, config)

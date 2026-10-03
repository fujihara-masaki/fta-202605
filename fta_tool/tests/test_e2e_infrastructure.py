"""The real-browser test infrastructure without a browser (tests/e2e;
the check in Google Chrome of 2026-10-03, see tests/e2e/README.md).

* the preflight (--e2e-preflight): only PREFLIGHT_TESTS run, the others are
  left out (not 未実施); a skip, no test or a missing preflight test is a
  failure; it cannot be combined with the required run;
* the record (e2e-report.md): start and end, the channel asked for and the
  browser actually started (or why it did not start), the code-side .env,
  the test server, where a failure's evidence goes;
* the launch message names the channel and never asks to install Chromium
  for it;
* the test servers never take the ports of the user's own servers, and are
  reached without a proxy;
* the evidence folder of a failed test stays short on Windows (MAX_PATH).
"""

from __future__ import annotations

import pathlib
import re
import types

import pytest

from tests.e2e import acceptance, support
from tests.e2e.conftest import launch_failure_message


class FakeItem:
    def __init__(self, nodeid: str, e2e: bool = True, ids: tuple = ()):
        self.nodeid = nodeid
        self._e2e = e2e
        self._ids = ids

    def get_closest_marker(self, name):
        return object() if name == "e2e" and self._e2e else None

    def iter_markers(self, name):
        if name == "acceptance" and self._ids:
            yield types.SimpleNamespace(args=self._ids)

    def add_marker(self, marker):  # without Playwright the E2E tests get a skip marker
        pass


class FakeConfig:
    def __init__(self, **options):
        self.stash = pytest.Stash()
        self._options = options
        self.deselected: list = []
        self.hook = types.SimpleNamespace(pytest_deselected=lambda items: self.deselected.extend(items))
        self.invocation_params = types.SimpleNamespace(args=("-m", "e2e"), dir=pathlib.Path.cwd())

    def getoption(self, name, default=None):
        return self._options.get(name, default)


@pytest.fixture(autouse=True)
def _no_required_env(monkeypatch):
    monkeypatch.delenv(acceptance.REQUIRED_ENV, raising=False)
    monkeypatch.delenv(acceptance.ENV_LABEL_ENV, raising=False)


def configured(**options) -> FakeConfig:
    config = FakeConfig(**options)
    acceptance.configure(config)
    return config


def preflight_items() -> list[FakeItem]:
    items = []
    for name in acceptance.PREFLIGHT_TESTS:
        items += [FakeItem(f"{name}[1280x800]", ids=("E-E01",)), FakeItem(f"{name}[1440x900]", ids=("E-E01",))]
    return items


# ----- the preflight -------------------------------------------------------------

def test_preflight_keeps_only_the_preflight_tests():
    config = configured(e2e_preflight=True)
    others = [FakeItem("tests/e2e/test_list_page.py::test_E_L01_open[1280x800]", ids=("E-L01",)),
              FakeItem("tests/test_export_service.py::test_csv", e2e=False)]
    items = preflight_items() + others
    acceptance.on_collection_modifyitems(config, items)
    assert [item.nodeid for item in items] == [item.nodeid for item in preflight_items()]
    assert config.deselected == others
    acceptance.on_deselected(config, config.deselected)
    run = acceptance.state(config)
    assert run.deselected == {} and run.preflight_missing == []


def test_preflight_verdict_needs_tests_and_every_one_passed():
    config = configured(e2e_preflight=True)
    run = acceptance.state(config)
    acceptance.summarize(run)
    assert run.verdict == "失敗"  # no test at all

    for item in preflight_items():
        run.records[item.nodeid] = acceptance.TestRecord(item.nodeid, ["E-E01"], "passed")
    acceptance.summarize(run)
    assert run.verdict == "成功" and acceptance.passed(run)
    assert list(run.id_results) == ["E-E01"]  # only what the preflight ran

    next(iter(run.records.values())).outcome = "failed"
    acceptance.summarize(run)
    assert run.verdict == "失敗" and not acceptance.passed(run)


def test_a_missing_preflight_test_is_a_failure():
    config = configured(e2e_preflight=True)
    items = preflight_items()[2:]  # the first preflight test is gone (e.g. renamed)
    acceptance.on_collection_modifyitems(config, items)
    run = acceptance.state(config)
    assert run.preflight_missing == [acceptance.PREFLIGHT_TESTS[0]]
    for item in items:
        run.records[item.nodeid] = acceptance.TestRecord(item.nodeid, ["E-E01"], "passed")
    acceptance.summarize(run)
    assert run.verdict == "失敗"


def test_a_skip_is_a_failure_in_the_preflight():
    config = configured(e2e_preflight=True)
    run = acceptance.state(config)
    item = types.SimpleNamespace(nodeid="tests/e2e/x.py::test_x[1280x800]", config=config)
    run.records[item.nodeid] = acceptance.TestRecord(item.nodeid, [])
    report = types.SimpleNamespace(skipped=True, failed=False, when="setup", outcome="skipped",
                                   longrepr=("x.py", 1, "Skipped: ブラウザを起動できません"))
    acceptance.on_report(item, report)
    assert report.outcome == "failed"
    assert report.longrepr.startswith("[準備確認] スキップは失敗として扱います")
    assert run.records[item.nodeid].outcome == "failed"


def test_preflight_and_required_run_cannot_be_combined(monkeypatch):
    with pytest.raises(pytest.UsageError):
        configured(e2e_preflight=True, e2e_required=True)
    monkeypatch.setenv(acceptance.REQUIRED_ENV, "1")
    with pytest.raises(pytest.UsageError):
        configured(e2e_preflight=True)


def test_the_required_run_is_unchanged():
    config = configured(e2e_required=True)
    run = acceptance.state(config)
    acceptance.on_deselected(config, [FakeItem("tests/e2e/test_list_page.py::test_E_L01_open[1280x800]", ids=("E-L01",))])
    for name in acceptance.REQUIRED_IDS:
        run.records[name] = acceptance.TestRecord(name, [name], "passed")
    acceptance.summarize(run)
    assert run.verdict == "不合格"  # a deselected test is 未実施
    run.deselected.clear()
    acceptance.summarize(run)
    assert run.verdict == "合格" and acceptance.passed(run)


# ----- the record -----------------------------------------------------------------

def test_the_record_names_the_channel_the_started_browser_and_the_evidence(tmp_path):
    config = configured(e2e_preflight=True, browser_channel="chrome", headed=True, slowmo=0,
                        output=str(tmp_path / "failures"), screenshot="only-on-failure", tracing="retain-on-failure")
    run = acceptance.state(config)
    run.browser = {"name": "chromium", "version": "154.0.7000.1", "mode": "headed"}
    run.launch = {"headless": False, "product": "Google LLC 154.0.7000.1 (Official Build) (64-bit)",
                  "executable": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  "profile": r"C:\Temp\playwright_chromiumdev_profile-AbC\Default"}
    run.server = {"url": "http://127.0.0.1:50123", "workdir": str(tmp_path / "e2e-server0"),
                  "log": str(tmp_path / "e2e-server0" / "server.log")}
    for item in preflight_items():
        run.records[item.nodeid] = acceptance.TestRecord(item.nodeid, ["E-E01"], "passed")
    session = types.SimpleNamespace(config=config, exitstatus=pytest.ExitCode.OK)
    acceptance.on_session_finish(session)
    text = acceptance.render_markdown(config, run)
    assert "準備確認の記録です" in text
    assert "| ブラウザの channel（指定） | chrome |" in text
    assert "| 起動したブラウザ | Google LLC 154.0.7000.1 (Official Build) (64-bit) |" in text
    assert r"| ブラウザの実行ファイル | C:\Program Files\Google\Chrome\Application\chrome.exe |" in text
    assert "| 起動の設定 | headed（画面を表示）、slowmo なし |" in text
    assert re.search(r"\| 開始・終了（ローカル時刻） \| \d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4} 〜 .+（所要 \d+分\d\d秒） \|", text)
    assert "| コード側の .env | " in text
    assert "| テスト用サーバー | AI: e2e-stub" in text and "http://127.0.0.1:50123" in text
    assert f"保存先 {tmp_path / 'failures'}" in text
    assert "| 判定 | 成功（準備確認。全必須 E2E の合格ではありません） |" in text
    assert session.exitstatus == pytest.ExitCode.OK


def test_the_record_says_why_the_browser_did_not_start():
    config = configured(e2e_required=True, browser_channel="chrome")
    run = acceptance.state(config)
    run.launch = {"headless": False, "error": "Chromium distribution 'chrome' is not found at C:\\x\\chrome.exe"}
    session = types.SimpleNamespace(config=config, exitstatus=pytest.ExitCode.OK)
    acceptance.on_session_finish(session)
    text = acceptance.render_markdown(config, run)
    assert "| 起動したブラウザ | 未起動（起動できませんでした：Chromium distribution 'chrome' is not found" in text
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED  # required run without the browser


def test_launch_failure_message_names_the_channel():
    plain = launch_failure_message(None, "Executable doesn't exist")
    assert "python -m playwright install chromium" in plain
    chrome = launch_failure_message("chrome", "Chromium distribution 'chrome' is not found")
    assert "--browser-channel chrome" in chrome and "切り替えません" in chrome
    assert "playwright install" not in chrome


# ----- ports and evidence folders ---------------------------------------------------

def test_free_port_never_takes_a_port_of_the_user(monkeypatch):
    ports = iter([8001, 8002, 8000, 54321])

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def bind(self, address):
            self.port = next(ports)

        def getsockname(self):
            return ("127.0.0.1", self.port)

    monkeypatch.setattr(support.socket, "socket", FakeSocket)
    assert support.free_port() == 54321


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def test_evidence_folder_is_short_on_windows_only():
    nodeid = ("tests/e2e/test_edit_integrity.py::"
              "test_additional_generation_and_manual_add_below_inconsistent_parents_are_refused[1440x900]")
    name = nodeid.split("::")[1]
    assert support.evidence_folder_name(nodeid, name, _slugify, windows=False) == _slugify(nodeid)
    short = support.evidence_folder_name(nodeid, name, _slugify, windows=True)
    assert len(short) <= support.WINDOWS_EVIDENCE_NAME + 8 < len(_slugify(nodeid))
    other = support.evidence_folder_name(nodeid.replace("test_edit_integrity", "test_other"), name, _slugify, windows=True)
    assert short != other  # one folder per test
    very_long = "tests/e2e/x.py::test_" + "a" * 300
    assert len(support.evidence_folder_name(very_long, "test_x", _slugify, windows=False)) == 100 + 1 + 7 + 1 + 100


def test_the_test_server_is_reached_without_a_proxy(tmp_path, monkeypatch):
    # Windows takes the system proxy from the registry when no variable is set;
    # the test server on this PC must never be asked through a proxy.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    server = support.E2EServer("http://127.0.0.1:1", tmp_path, process=None, log_path=tmp_path / "server.log")
    try:
        assert server.http.trust_env is False
    finally:
        server.http.close()

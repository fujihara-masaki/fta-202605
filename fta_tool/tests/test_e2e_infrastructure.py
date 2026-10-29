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
* the evidence folder of a failed test stays short on Windows (MAX_PATH);
* the record of a failed test's evidence lists the files actually left
  (the options are only what pytest-playwright tries to keep) and says why
  the page could not be taken, which pytest-playwright does not;
* no console error is let through: the favicon 404 the user let through on
  2026-10-03 is gone since PR-7 gave the app its icon; a 404 of
  /favicon.ico, of the icon or of anything else fails, and the record says
  that there is no exception;
* PR3-LAYOUT's display area (the user's instruction of 2026-10-06): a
  difference from the requested size is tolerated only for chrome-1905x945,
  up to +1 CSS px on each axis, when the browser had it before the app and
  no layout boundary lies between; a difference that appears after the app,
  a larger or smaller one, one across a boundary (1280px, where a pane stops
  growing) or one in another case is not; the requested and measured sizes
  are recorded; and the boundaries follow the edit page's stylesheets.
"""

from __future__ import annotations

import datetime
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


def test_a_failure_records_when_its_phase_ran():
    config = configured(e2e_required=True)
    run = acceptance.state(config)
    item = types.SimpleNamespace(nodeid="tests/e2e/x.py::test_x[1280x800]", config=config)
    run.records[item.nodeid] = acceptance.TestRecord(item.nodeid, [])
    start = datetime.datetime(2026, 10, 14, 8, 5, 11).timestamp()
    report = types.SimpleNamespace(skipped=False, failed=True, when="call", outcome="failed", start=start,
                                   stop=start + 10.4, longreprtext="E   AssertionError: コンソールのエラー")
    acceptance.on_report(item, report)
    assert run.records[item.nodeid].reason == "call（08:05:11〜08:05:21）: AssertionError: コンソールのエラー"
    # Without the times (e.g. an older pytest) the record is as before.
    del report.start
    acceptance.on_report(item, report)
    assert run.records[item.nodeid].reason == "call: AssertionError: コンソールのエラー"


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


def test_the_test_server_is_asked_on_a_new_connection_each_time(tmp_path):
    """PR-7: no connection is kept for the next request, so none is reused
    just when uvicorn closes it as idle (5 s), which lost a request once in
    the run of every test at every size ("Server disconnected without
    sending a response")."""
    server = support.E2EServer("http://127.0.0.1:1", tmp_path, process=None, log_path=tmp_path / "server.log")
    try:
        assert server.http._transport._pool._max_keepalive_connections == 0
    finally:
        server.http.close()


# ----- no console error is let through (PR-7 removed the favicon exception) ------

ORIGIN = "http://127.0.0.1:43210"
FAVICON = ORIGIN + "/favicon.ico"


class FakeBrowserPage:
    """What PageWatcher uses of a page."""

    def __init__(self):
        self.handlers = {}
        self.context = types.SimpleNamespace(on=lambda name, handler: None)

    def on(self, name, handler):
        self.handlers[name] = handler


def watched():
    page = FakeBrowserPage()
    return support.PageWatcher(page, ORIGIN), page


def console_error(page, text: str, url: str = "") -> None:
    page.handlers["console"](types.SimpleNamespace(type="error", text=text, location={"url": url} if url else {}))


@pytest.mark.parametrize("path", [
    "/favicon.ico", "/static/favicon.svg", "/static/js/pages/edit.js", "/static/css/edit.css", "/analyses/1/nodes",
    "/favicon.ico?v=1",
])
def test_a_404_fails_whatever_it_is_of(path):
    watcher, page = watched()
    console_error(page, support.NOT_FOUND_TEXT, ORIGIN + path)
    assert watcher.problems() == [f"コンソールのエラー: ['{support.NOT_FOUND_TEXT}（{ORIGIN}{path}）']"]


def test_the_favicon_exception_is_gone():
    """The names of the exception (FAVICON_404_TEXT, the CDP records of it)
    are gone; the watcher has nothing that could let an error through."""
    for name in ("FAVICON_404_TEXT", "FAVICON_PATH", "FAVICON_RESOURCE_TYPE"):
        assert not hasattr(support, name), name
    watcher, page = watched()
    for attribute in ("known", "network_log", "responses", "cdp_error"):
        assert not hasattr(watcher, attribute), attribute
    assert not hasattr(acceptance, "add_known_console")


def test_only_a_tests_own_allowance_lets_its_error_through():
    watcher, page = watched()
    watcher.allow_console_error(r"status of 500")
    console_error(page, "Failed to load resource: the server responded with a status of 500 (Internal Server Error)",
                  ORIGIN + "/nodes/1/update")
    console_error(page, support.NOT_FOUND_TEXT, FAVICON)
    page.handlers["pageerror"](RuntimeError("TypeError: x is undefined"))
    assert watcher.problems() == [
        f"コンソールのエラー: ['{support.NOT_FOUND_TEXT}（{FAVICON}）']",
        "ページのエラー（例外）: ['TypeError: x is undefined']",
    ]


def test_the_record_says_there_is_no_console_exception():
    config = configured(e2e_required=True)
    text = acceptance.render_markdown(config, acceptance.state(config))
    assert f"| {acceptance.CONSOLE_EXCEPTION_ROW} | {acceptance.CONSOLE_EXCEPTION_TEXT} |" in text
    assert "既知の例外" not in text.replace(acceptance.CONSOLE_EXCEPTION_TEXT, "")


def test_every_screen_declares_the_icon_the_app_serves():
    """The icon is declared once, in base.html, so the browser asks for it
    and never for /favicon.ico (which the app does not answer: no route was
    added for it)."""
    from fastapi.testclient import TestClient

    from app.main import app

    templates = support.FTA_TOOL_DIR / "app" / "templates"
    declared = [str(path.relative_to(templates)) for path in sorted(templates.rglob("*.html"))
                if re.search(r"""rel\s*=\s*["'][^"']*\bicon\b""", path.read_text(encoding="utf-8"), re.IGNORECASE)]
    assert declared == ["base.html"]
    with TestClient(app) as client:
        icon = client.get(support.FAVICON_URL)
        assert icon.status_code == 200 and icon.headers["content-type"] == "image/svg+xml"
        assert icon.headers["cache-control"] == "no-cache" and icon.headers["etag"]  # PR-C's revalidation
        assert icon.content.startswith(b"<svg") and b"http" not in icon.content.replace(b"http://www.w3.org/2000/svg", b"")
        assert client.get("/favicon.ico").status_code == 404


# ----- the evidence a failed test actually left -------------------------------------------

class FakeShotPage:
    """page.screenshot as the page fixture calls it: writes the file, raises, or does neither."""

    def __init__(self, error: Exception | None = None, write: bool = True):
        self.error, self.write, self.calls = error, write, []

    def screenshot(self, path, timeout):
        self.calls.append((path, timeout))
        if self.error is not None:
            raise self.error
        if self.write:
            pathlib.Path(path).write_bytes(b"\x89PNG fake")


def test_the_failure_screenshot_is_saved_or_says_why(tmp_path):
    page = FakeShotPage()
    shot = support.save_screenshot(page, tmp_path / "folder" / support.FAILURE_SCREENSHOT)
    assert shot == {"file": "page-at-failure.png", "bytes": 9}
    assert page.calls[0][1] == 5000  # as pytest-playwright's own
    error = TimeoutError("Page.screenshot: Timeout 5000ms exceeded.\nCall log:\n  - taking page screenshot")
    shot = support.save_screenshot(FakeShotPage(error=error), tmp_path / "pending.png")
    assert shot == {"file": None, "reason": "TimeoutError: Page.screenshot: Timeout 5000ms exceeded."}
    shot = support.save_screenshot(FakeShotPage(write=False), tmp_path / "none.png")
    assert shot == {"file": None, "reason": "保存の呼び出しは終わったが、ファイルがない"}


def test_the_page_is_taken_when_the_test_failed_as_pytest_playwright_decides():
    from tests.e2e.conftest import _test_failed

    assert _test_failed(types.SimpleNamespace(rep_call=types.SimpleNamespace(failed=True)))
    assert not _test_failed(types.SimpleNamespace(rep_call=types.SimpleNamespace(failed=False)))
    assert _test_failed(types.SimpleNamespace())  # no call phase: as pytest-playwright, a failure


class FakeTerminal:
    def __init__(self):
        self.lines: list[str] = []

    def section(self, title):
        self.lines.append(f"== {title}")

    def line(self, text="", **markup):
        self.lines.append(text)


def test_the_record_lists_the_files_a_failed_test_actually_left(tmp_path):
    output = tmp_path / "failures"
    config = configured(e2e_preflight=True, output=str(output), screenshot="only-on-failure",
                        tracing="retain-on-failure")
    run = acceptance.state(config)
    items = {name: FakeItem(f"tests/e2e/test_edit_page.py::test_{name}[1280x800]")
             for name in ("loaded", "pending", "own_browser", "gone", "passed")}
    for name, item in items.items():
        item.config = config
        run.records[item.nodeid] = acceptance.TestRecord(item.nodeid, ["E-E01"], "passed" if name == "passed" else "failed")
        if name != "own_browser":  # a test that opens its own browser has no pytest-playwright folder
            acceptance.add_evidence_folder(item, output / f"test-{name}")
    loaded = output / "test-loaded"
    loaded.mkdir(parents=True)
    for name, data in (("trace.zip", b"PK1234"), ("test-failed-1.png", b"PNG1"), ("page-at-failure.png", b"PNG")):
        (loaded / name).write_bytes(data)
    acceptance.add_failure_screenshot(items["loaded"], {"file": "page-at-failure.png", "bytes": 3})
    (output / "test-pending").mkdir()
    (output / "test-pending" / "trace.zip").write_bytes(b"PK12")
    acceptance.add_failure_screenshot(items["pending"], {
        "file": None, "reason": "TimeoutError: Page.screenshot: Timeout 5000ms exceeded."})

    text = acceptance.render_markdown(config, run)
    assert ("| 失敗時の証跡の設定（pytest-playwright） | スクリーンショット only-on-failure、trace retain-on-failure、"
            f"保存先 {output}（設定です。実際に残ったファイルは下の「失敗したテストの証跡（実際にあるファイル）」） |") in text
    assert "| 失敗時の証跡（pytest-playwright） |" not in text
    section = text.split("### 失敗したテストの証跡（実際にあるファイル）")[1].split("###")[0]
    assert support.FAILURE_SCREENSHOT in section and "ファイルが残ったことは示しません" in section
    assert ("| `tests/e2e/test_edit_page.py::test_loaded[1280x800]` | test-loaded | page-at-failure.png（3 バイト、"
            "この記録の画面）、test-failed-1.png（4 バイト、pytest-playwright の画面）、trace.zip（6 バイト、"
            "pytest-playwright の trace） | page-at-failure.png（3 バイト） |") in section
    assert ("| `tests/e2e/test_edit_page.py::test_pending[1280x800]` | test-pending | trace.zip（4 バイト、"
            "pytest-playwright の trace） | 保存できなかった：TimeoutError: Page.screenshot: Timeout 5000ms exceeded. |") in section
    assert ("| `tests/e2e/test_edit_page.py::test_own_browser[1280x800]` | - | 保存先なし（pytest-playwright の画面・trace の対象外"
            in section)
    assert ("| `tests/e2e/test_edit_page.py::test_gone[1280x800]` | test-gone | なし（保存先のフォルダがない） "
            "| 撮っていない（ページの終了処理まで進まなかった） |") in section
    assert "test_passed" not in section

    acceptance.summarize(run)
    terminal = FakeTerminal()
    acceptance.terminal_summary(terminal, config)
    assert ("失敗したテストの証跡（実際にあるファイル）: 4 件中、trace あり 2 件・画面あり 1 件"
            "（画面を撮れなかったもの 1 件。理由は e2e-report.md）") in terminal.lines


def test_the_record_says_when_no_test_failed(tmp_path):
    config = configured(e2e_required=True, output=str(tmp_path / "failures"))
    text = acceptance.render_markdown(config, acceptance.state(config))
    assert "### 失敗したテストの証跡（実際にあるファイル）" in text and "失敗したテストはありません。" in text


# ----- PR3-LAYOUT: the display area ----------------------------------------------

def measured(client, visual=None, ratio=1) -> dict:
    """What support.measure_viewport returns."""
    return {"client": list(client), "inner": list(client), "devicePixelRatio": ratio,
            "visualViewport": [*(visual or client), 1], "scroll": list(client)}


# What the Windows Chrome preflight of 2026-10-06 measured for 1905x945
# (about:blank and the edit page alike), as Chromium does at a display scale
# of 1.25 (reproduced on Linux with --force-device-scale-factor=1.25).
WINDOWS_CHROME = measured((1906, 946), (1905.5999755859375, 945.5999755859375), 1.0000000149011612)


def test_the_measured_size_is_used_only_where_the_difference_may_be_tolerated():
    assert acceptance.VIEWPORT_ALLOWED == {"chrome-1905x945": 1}  # the one case (2026-10-06)
    result = support.judge_viewport((1905, 945), WINDOWS_CHROME, WINDOWS_CHROME, 1)
    assert result == {"size": (1906, 946), "verdict": "許容した差",
                      "reason": "幅 +1・高さ +1 CSS px。アプリの表示前（about:blank）から同じで、レイアウトの境界を跨がない"}
    exact = measured((1905, 945))
    assert support.judge_viewport((1905, 945), exact, exact, 1) == {"size": (1905, 945), "verdict": "一致", "reason": ""}
    # Only the width or only the height differs.
    assert support.judge_viewport((1905, 945), measured((1906, 945)), measured((1906, 945)), 1)["verdict"] == "許容した差"
    assert support.judge_viewport((1905, 945), measured((1905, 946)), measured((1905, 946)), 1)["verdict"] == "許容した差"
    # The same difference where the case does not allow it (1280x800, edge-1912x914).
    assert support.judge_viewport((1905, 945), WINDOWS_CHROME, WINDOWS_CHROME, 0) == {
        "size": (1906, 946), "verdict": "許容しない差", "reason": "この寸法では差を許容しない"}


@pytest.mark.parametrize("requested, before, after, reason", [
    # A difference that appears with the app, or changes with it.
    ((1905, 945), measured((1905, 945)), measured((1906, 946)), "アプリの表示後に寸法が変わった（表示前 1905×945）"),
    ((1905, 945), measured((1906, 946)), measured((1906, 945)), "アプリの表示後に寸法が変わった（表示前 1906×946）"),
    ((1905, 945), None, measured((1906, 946)), "アプリの表示前に測っていない"),
    # Larger than +1, or smaller.
    ((1905, 945), measured((1907, 946)), measured((1907, 946)), "幅の差 +2 が許容（0〜+1 CSS px）の外"),
    ((1905, 945), measured((1906, 947)), measured((1906, 947)), "高さの差 +2 が許容（0〜+1 CSS px）の外"),
    ((1905, 945), measured((1904, 945)), measured((1904, 945)), "幅の差 -1 が許容（0〜+1 CSS px）の外"),
    ((1905, 945), measured((1905, 944)), measured((1905, 944)), "高さの差 -1 が許容（0〜+1 CSS px）の外"),
    ((1905, 945), measured((1890, 945)), measured((1890, 945)), "幅の差 -15 が許容（0〜+1 CSS px）の外"),
    # Across a layout boundary, or on one: PR-3's base and where the
    # inspector column stops growing (440px at 23vw).
    ((1280, 800), measured((1281, 800)), measured((1281, 800)), "要求と実測の間にレイアウトの境界がある（幅 1280 px）"),
    ((1279, 800), measured((1280, 800)), measured((1280, 800)), "要求と実測の間にレイアウトの境界がある（幅 1280 px）"),
    ((1913, 914), measured((1914, 914)), measured((1914, 914)), "要求と実測の間にレイアウトの境界がある（幅 1913.0435 px）"),
    # The fractional display area past the boundary, the whole number not.
    ((1912, 914), measured((1913, 914), (1913.2, 914)), measured((1913, 914), (1913.2, 914)), "（幅 1913.0435 px）"),
])
def test_differences_that_are_not_tolerated(requested, before, after, reason):
    result = support.judge_viewport(requested, before, after, 1)
    assert result["verdict"] == "許容しない差"
    assert reason in result["reason"]
    assert result["size"] == tuple(after["client"])  # recorded as measured


def test_a_boundary_of_the_height_is_not_crossed_either():
    boundaries = {"width": (), "height": (945.5,)}
    result = support.judge_viewport((1905, 945), WINDOWS_CHROME, WINDOWS_CHROME, 1, boundaries)
    assert result["verdict"] == "許容しない差" and "（高さ 945.5 px）" in result["reason"]
    assert support.judge_viewport((1905, 945), WINDOWS_CHROME, WINDOWS_CHROME, 1,
                                  {"width": (1907,), "height": (944.9,)})["verdict"] == "許容した差"


# The edit page's stylesheets (base.html and analysis_detail.html) and their
# rules that depend on the display area, from which
# support.LAYOUT_BOUNDARIES was derived.
EDIT_PAGE_TEMPLATES = ("base.html", "analysis_detail.html")
VIEWPORT_RULES = {
    "base.css": ("height: 100vh",),
    "components.css": ("width: min(520px, calc(100vw - 32px))", "max-height: calc(100vh - 32px)",
                       "max-width: calc(100vw - 16px)", "max-height: 30vh", "max-height: 25vh"),
    "edit.css": ("height: calc(100vh - var(--header-height))",
                 "grid-template-columns: clamp(240px, 17vw, 320px) minmax(0, 1fr) clamp(340px, 23vw, 440px)"),
}
# The display-area conditions (PR-7, J-20): the edit page's widths and the
# notifications' height (components.css, since the fix of 2026-10-29).
MEDIA_RULES = {"css/components.css": ["@media (height < 700px)"],
               "css/edit.css": ["@media (width < 1280px)", "@media (width < 1024px)"]}
VIEWPORT_UNIT = re.compile(r"[\w-]+\s*:[^;{}]*\b\d*\.?\d+(?:[dsl])?v(?:w|h|min|max|i|b)\b[^;{}]*")


def test_the_layout_boundaries_follow_the_edit_pages_stylesheets():
    app = pathlib.Path(acceptance.FTA_TOOL_DIR) / "app"
    sheets = sorted({name for template in EDIT_PAGE_TEMPLATES
                     for name in re.findall(r'href="/static/([^"]+\.css)"',
                                            (app / "templates" / template).read_text(encoding="utf-8"))})
    assert sheets == ["css/base.css", "css/components.css", "css/edit.css", "css/tokens.css"]
    found, media = {}, {}
    for sheet in sheets:
        text = re.sub(r"/\*.*?\*/", "", (app / "static" / sheet).read_text(encoding="utf-8"), flags=re.S)
        assert not re.search(r"@container\b", text), sheet
        conditions = [" ".join(m.split()) for m in re.findall(r"@media[^{]*", text)]
        if conditions:
            media[sheet] = [c.strip() for c in conditions]
        rules = tuple(" ".join(rule.split()) for rule in VIEWPORT_UNIT.findall(text))
        if rules:
            found[pathlib.Path(sheet).name] = rules
        if sheet == "css/edit.css":
            # No minimum width of the whole page any more (1100px until PR-7).
            assert not re.search(r"\.edit-page\s*\{[^}]*min-width", text)
            assert re.search(r"@media \(width < 1280px\)\s*\{\s*\.edit-layout\s*\{\s*grid-template-columns: minmax\(0, 1fr\) 340px;", text)
            assert re.search(r"@media \(width < 1024px\)\s*\{\s*\.edit-center \.edit-view\s*\{\s*min-width: 684px;", text)
    assert media == MEDIA_RULES, "表示領域の条件が変わった（LAYOUT_BOUNDARIES を見直す）"
    assert found == VIEWPORT_RULES, "表示領域に依存する規則が変わった：support.LAYOUT_BOUNDARIES を見直す"
    assert set(support.LAYOUT_BOUNDARIES["width"]) == {
        1280, 1024, 240 / 0.17, 320 / 0.17, 340 / 0.23, 440 / 0.23, 520 + 32, 340 + 16}
    assert support.LAYOUT_BOUNDARIES["height"] == (700,)
    # chrome-1905x945 and its measured 1906x946 are between two of them.
    assert not [b for b in support.LAYOUT_BOUNDARIES["width"] if 1905 <= b <= 1906]


def viewport_run(tmp_path):
    config = configured(e2e_preflight=True, output=str(tmp_path / "failures"))
    run = acceptance.state(config)
    cases = {"1280x800": ((1280, 800), 0, measured((1280, 800)), measured((1280, 800))),
             "chrome-1905x945": ((1905, 945), 1, WINDOWS_CHROME, WINDOWS_CHROME),
             "edge-1912x914": ((1912, 914), 0, measured((1912, 914)), None)}
    for case, (requested, allowed, before, after) in cases.items():
        item = FakeItem(f"tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[{case}]",
                        ids=("PR3-LAYOUT",))
        item.config = config
        run.records[item.nodeid] = acceptance.TestRecord(item.nodeid, ["PR3-LAYOUT"], "passed" if after else "failed")
        acceptance.record_viewport(item, requested=requested, allowed=allowed, before=before)
        if after:  # edge-1912x914 ends before the edit page is shown
            acceptance.record_viewport(item, after=after, **support.judge_viewport(requested, before, after, allowed))
    return config, run


def test_the_record_lists_the_requested_and_the_measured_display_area(tmp_path):
    config, run = viewport_run(tmp_path)
    text = acceptance.render_markdown(config, run)
    assert ("| 画面寸法の要求と実測（PR3-LAYOUT） | 一致 1・許容した差 1・許容しない差 0・判定前に終了 1"
            "（下の「画面寸法の要求と実測（PR3-LAYOUT）」） |") in text
    section = text.split("### 画面寸法の要求と実測（PR3-LAYOUT）")[1].split("###")[0]
    assert "chrome-1905x945（各軸 +1 CSS px まで）だけ" in section and "検証条件の限定変更" in section
    assert "実測の寸法を基準に最後まで行います" in section and "1280×800 と edge-1912x914）は一致が必要" in section
    windows = ("client 1906×946、inner 1906×946、visualViewport 1905.6×945.6（scale 1）、"
               "devicePixelRatio 1.0000000149011612、scroll 1906×946")
    assert (f"| `tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[chrome-1905x945]` "
            f"| 1905×945（差の許容 +1） | {windows} | {windows} | 許容した差：幅 +1・高さ +1 CSS px。"
            "アプリの表示前（about:blank）から同じで、レイアウトの境界を跨がない。後続の検査は 1906×946 を基準に実施 |") in section
    assert ("| `tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[1280x800]` "
            "| 1280×800 | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、"
            "scroll 1280×800 | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、"
            "scroll 1280×800 | 一致 |") in section
    assert "| 測っていない | 判定前に終了（編集画面の表示か測定の前に失敗） |" in section

    acceptance.summarize(run)
    terminal = FakeTerminal()
    acceptance.terminal_summary(terminal, config)
    assert ("画面寸法の要求と実測（PR3-LAYOUT）: 一致 1 件・許容した差 1 件・許容しない差 0 件"
            "（chrome-1905x945：要求 1905×945 → 実測 1906×946）") in terminal.lines


def test_a_refused_difference_is_recorded_as_such(tmp_path):
    config = configured(e2e_preflight=True)
    run = acceptance.state(config)
    item = FakeItem("tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[chrome-1905x945]")
    item.config = config
    before, after = measured((1905, 945)), measured((1906, 946))
    acceptance.record_viewport(item, requested=(1905, 945), allowed=1, before=before)
    acceptance.record_viewport(item, after=after, **support.judge_viewport((1905, 945), before, after, 1))
    text = acceptance.render_markdown(config, run)
    assert "| 許容しない差：アプリの表示後に寸法が変わった（表示前 1905×945） |" in text
    assert "一致 0・許容した差 0・許容しない差 1（" in text


def test_the_record_has_no_display_area_section_without_pr3_layout(tmp_path):
    config = configured(e2e_preflight=True)
    text = acceptance.render_markdown(config, acceptance.state(config))
    assert "画面寸法の要求と実測" not in text


# ----- the required acceptance IDs (PR-7: 68 → 75) ------------------------------------

PR7_IDS = ("E-K01", "E-K02", "E-K03", "E-V01", "E-V02", "E-V03", "E-F01")


def test_the_required_ids_are_75_without_duplicates_and_each_is_tested():
    import ast

    source = (pathlib.Path(acceptance.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    keys = next(node.value.keys for node in ast.walk(tree)
                if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "REQUIRED_IDS")
    written = [key.value for key in keys]
    assert len(written) == len(set(written)), sorted({k for k in written if written.count(k) > 1})
    assert len(acceptance.REQUIRED_IDS) == 75
    assert list(acceptance.REQUIRED_IDS)[-7:] == list(PR7_IDS)
    # PR-C's 68 are kept as they were, before PR-7's.
    assert list(acceptance.REQUIRED_IDS)[60:68] == [f"C-0{n}" for n in range(8)]
    e2e = pathlib.Path(acceptance.FTA_TOOL_DIR) / "tests" / "e2e"
    marked = set()
    for path in e2e.glob("test_*.py"):
        # acceptance("E-xx", …), or the ids given to a helper that marks some
        # parameters (test_pr7_viewports.py: cases(small_ids=("E-V03",))).
        for args in re.findall(r"(?:acceptance|small_ids=)\(([^)]*)\)", path.read_text(encoding="utf-8")):
            marked.update(re.findall(r'"([A-Z0-9-]+)"', args))
    assert set(acceptance.REQUIRED_IDS) - marked == set(), "必須 ID を付けたテストがない"
    assert all(acceptance.REQUIRED_IDS[i] for i in PR7_IDS)


def test_the_pr7_display_cases():
    labels = [case.label for case in acceptance.PR7_CASES]
    assert len(labels) == len(set(labels)) == 12
    sizes = {case.label: (case.size, case.dpr) for case in acceptance.PR7_CASES}
    # The assumed sizes of plan 5.9.4 …
    for label in ("1920x1080", "1536x730", "1280x620", "1366x650", "1093x500", "1024x683", "900x600"):
        assert sizes[label] == ((int(label.split("x")[0]), int(label.split("x")[1])), None)
    # … and the display areas measured on 2026-10-28, with their devicePixelRatio.
    assert sizes["chrome150-1280x630"] == ((1280, 630), 1.5) and sizes["edge150-1275x609"] == ((1275, 609), 1.5)
    assert sizes["chrome125-1536x756"] == ((1536, 756), 1.25) and sizes["edge125-1530x731"] == ((1530, 731), 1.25)
    assert sizes["chrome100-1920x945"] == ((1920, 945), 1.0)
    assert [case.size for case in acceptance.BASE_CASES] == [(1280, 800), (1440, 900)]
    assert acceptance.VIEWPORT_SETS["pr7"] == acceptance.BASE_CASES + acceptance.PR7_CASES
    config = configured(e2e_viewport_set="pr7")
    assert acceptance.state(config).viewport_set == "pr7"
    text = acceptance.render_markdown(config, acceptance.state(config))
    assert "| 寸法の組（--e2e-viewport-set） | pr7：" in text
    text = acceptance.render_markdown(configured(), acceptance.state(configured()))
    assert "全テストの全寸法での実行は、この記録では未実施" in text


def test_the_record_tells_how_each_control_was_reached_and_names_a_covering_notification():
    from tests.e2e import layout_checks

    config = configured(e2e_preflight=True)
    run = acceptance.state(config)
    item = FakeItem("tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1093x500]")
    item.config = config

    def entry(name, how, required=False, covered=()):
        return {"name": name, "how": how, "no_scroll_required": required, "client": [1093, 500],
                "box": [41, 305.4, 228.5, 36], "first_misses": list(covered), "covered_by_notifications": list(covered),
                "notifications": [{"kind": "success", "text": "二次要因の通常生成：3件作成しました",
                                   "box": [16, 422, 560, 54]}] if covered else []}
    for value in (entry("保存（入力の前）", layout_checks.REACHED_AS_SHOWN, required=True),
                  entry("生成中の状態表示", layout_checks.REACHED_AS_SHOWN),
                  entry("インスペクタの削除", layout_checks.REACHED_BY_PANE_SCROLL),
                  entry("操作バーの生成（生成後）", layout_checks.NOT_REACHED,
                        covered=[{"x": 75, "y": 358, "over": "div.ui-toast.ui-toast--success"}])):
        acceptance.record_reach(item, value)
    text = acceptance.render_markdown(config, run)
    section = text.split("### 主要な操作への到達")[1]
    assert f"| `{item.nodeid}` | 4 | 2（1） | 1 | 1 |" in section
    assert "通知に覆われていた操作は、スクロールの有無にかかわらず失敗にします" in section
    assert "| インスペクタの削除 | 1093×500 |" in section
    assert (f"| `{item.nodeid}` | 操作バーの生成（生成後） | 1093×500 | 41, 305.4, 228.5×36 | (75, 358) "
            "| success「二次要因の通常生成：3件作成しました」16,422 560×54 |") in section


def test_the_record_has_no_reach_section_without_reach():
    config = configured(e2e_preflight=True)
    assert "### 主要な操作への到達" not in acceptance.render_markdown(config, acceptance.state(config))

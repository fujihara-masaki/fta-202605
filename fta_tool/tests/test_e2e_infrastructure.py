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
* the known favicon 404 (the user's decision of 2026-10-03, PR-7 removes
  it): only the browser's own 404 for /favicon.ico of the test's server,
  matched with the browser's records, is let through; the same message of
  another resource, origin, status, type or without its origin or records
  fails; another error next to it fails the test; each one is recorded
  once; and the exception ends as soon as the app has an icon;
* PR3-LAYOUT's display area (the user's instruction of 2026-10-06): a
  difference from the requested size is tolerated only for chrome-1905x945,
  up to +1 CSS px on each axis, when the browser had it before the app and
  no layout boundary lies between; a difference that appears after the app,
  a larger or smaller one, one across a boundary (1280px, where a pane stops
  growing) or one in another case is not; the requested and measured sizes
  are recorded; and the boundaries follow the edit page's stylesheets.
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


# ----- the known favicon 404 (the user's decision of 2026-10-03) ------------------

ORIGIN = "http://127.0.0.1:43210"
FAVICON = ORIGIN + "/favicon.ico"
REASONS = {404: "Not Found", 500: "Internal Server Error"}


class FakeCDP:
    def __init__(self):
        self.handlers = {}

    def on(self, name, handler):
        self.handlers[name] = handler

    def send(self, method, params=None):
        return {}


class FakeBrowserPage:
    """What PageWatcher uses of a page; cdp None: no CDP session (not Chromium)."""

    def __init__(self, cdp):
        self.handlers = {}
        self.cdp = cdp
        self.waits = 0
        self.on_wait = None
        self.context = types.SimpleNamespace(on=lambda name, handler: None, new_cdp_session=self._cdp_session)

    def _cdp_session(self, page):
        if self.cdp is None:
            raise RuntimeError("CDP session is only available in Chromium")
        return self.cdp

    def on(self, name, handler):
        self.handlers[name] = handler

    def wait_for_timeout(self, milliseconds):
        self.waits += 1
        if self.on_wait:
            self.on_wait()


@pytest.fixture(autouse=True)
def _no_watcher_left():
    yield
    support.PageWatcher.take_made()  # the fakes never reach a report of the E2E tests


def watched(cdp: bool = True):
    page = FakeBrowserPage(FakeCDP() if cdp else None)
    return support.PageWatcher(page, ORIGIN), page


def console_error(page, text: str, url: str = "") -> None:
    page.handlers["console"](types.SimpleNamespace(type="error", text=text, location={"url": url} if url else {}))


def failed_load(page, url: str, *, status: int = 404, kind: str = "Other", request_id: str = "7.1",
                console: bool = True, log: bool = True, response: bool = True) -> None:
    """What the browser reports for a resource that failed to load, as
    Chromium 141 and Edge 154 did (the response, its log entry, the console)."""
    text = f"Failed to load resource: the server responded with a status of {status} ({REASONS[status]})"
    if response and page.cdp:
        page.cdp.handlers["Network.responseReceived"](
            {"requestId": request_id, "type": kind, "response": {"url": url, "status": status}})
    if log and page.cdp:
        page.cdp.handlers["Log.entryAdded"]({"entry": {
            "source": "network", "level": "error", "text": text, "url": url, "networkRequestId": request_id}})
    if console:
        console_error(page, text, url)


def test_the_browsers_own_favicon_404_of_the_tests_server_is_let_through():
    watcher, page = watched()
    failed_load(page, FAVICON)
    assert watcher.problems() == []
    assert watcher.known == {0: {"url": FAVICON, "text": support.FAVICON_404_TEXT, "status": 404,
                                 "type": "Other", "request_id": "7.1"}}


@pytest.mark.parametrize("path", [
    "/static/js/pages/edit.js", "/static/css/edit.css", "/analyses/1/nodes", "/favicon.ico?v=1",
    "/favicon.ico/", "/static/favicon.ico", "/Favicon.ico", "/favicon.png",
])
def test_the_same_404_of_another_resource_fails(path):
    watcher, page = watched()
    failed_load(page, ORIGIN + path)
    assert watcher.problems() == [f"コンソールのエラー: ['{support.FAVICON_404_TEXT}（{ORIGIN}{path}）']"]
    assert watcher.known == {}
    assert watcher.responses == {}  # only the response of <origin>/favicon.ico is kept


def test_another_message_of_the_favicon_fails():
    watcher, page = watched()  # e.g. a 404 without its reason phrase: not the known message
    text = "Failed to load resource: the server responded with a status of 404 ()"
    page.cdp.handlers["Network.responseReceived"](
        {"requestId": "7.1", "type": "Other", "response": {"url": FAVICON, "status": 404}})
    page.cdp.handlers["Log.entryAdded"]({"entry": {"source": "network", "level": "error", "text": text,
                                                   "url": FAVICON, "networkRequestId": "7.1"}})
    console_error(page, text, FAVICON)
    assert len(watcher.problems()) == 1 and watcher.known == {}


@pytest.mark.parametrize("kind", ["Fetch", "Image", "Script", "XHR"])
def test_the_favicon_loaded_by_the_page_fails(kind):
    watcher, page = watched()
    failed_load(page, FAVICON, kind=kind)
    assert len(watcher.problems()) == 1 and watcher.known == {}


@pytest.mark.parametrize("url", ["http://127.0.0.1:43211/favicon.ico", "http://localhost:43210/favicon.ico",
                                 "https://127.0.0.1:43210/favicon.ico", "http://example.com/favicon.ico"])
def test_a_favicon_of_another_origin_fails(url):
    watcher, page = watched()
    failed_load(page, url)
    assert len(watcher.problems()) == 1 and watcher.known == {}


def test_a_favicon_500_a_failed_connection_or_another_answer_fails():
    watcher, page = watched()
    failed_load(page, FAVICON, status=500, request_id="7.1")
    refused = "Failed to load resource: net::ERR_CONNECTION_REFUSED"  # no response at all
    page.cdp.handlers["Log.entryAdded"]({"entry": {"source": "network", "level": "error", "text": refused,
                                                   "url": FAVICON, "networkRequestId": "7.2"}})
    console_error(page, refused, FAVICON)
    # The console says 404 while the browser's record of the response says 500.
    page.cdp.handlers["Network.responseReceived"](
        {"requestId": "7.3", "type": "Other", "response": {"url": FAVICON, "status": 500}})
    page.cdp.handlers["Log.entryAdded"]({"entry": {"source": "network", "level": "error",
                                                   "text": support.FAVICON_404_TEXT, "url": FAVICON,
                                                   "networkRequestId": "7.3"}})
    console_error(page, support.FAVICON_404_TEXT, FAVICON)
    problems = watcher.problems()
    assert len(problems) == 1 and problems[0].count(f"（{FAVICON}）") == 3
    assert watcher.known == {}


def test_without_its_origin_or_the_browsers_records_the_404_fails():
    watcher, page = watched()
    console_error(page, support.FAVICON_404_TEXT)  # where it came from is not known
    assert watcher.problems() == [f"コンソールのエラー: ['{support.FAVICON_404_TEXT}']"] and watcher.known == {}
    for missing in ({"log": False}, {"response": False}):
        watcher, page = watched()
        failed_load(page, FAVICON, **missing)
        assert len(watcher.problems()) == 1 and watcher.known == {}
        assert page.waits == 20  # waited 2 seconds for the browser's records, then failed
    watcher, page = watched(cdp=False)
    failed_load(page, FAVICON)
    assert len(watcher.problems()) == 1 and watcher.known == {}
    assert "Chromium" in watcher.cdp_error and page.waits == 0


def test_the_browsers_records_coming_a_moment_later_are_waited_for():
    watcher, page = watched()
    failed_load(page, FAVICON, log=False, response=False)  # the console message comes first

    def records_arrive():
        if page.waits == 3:
            failed_load(page, FAVICON, console=False)

    page.on_wait = records_arrive
    assert watcher.problems() == [] and list(watcher.known) == [0] and page.waits == 3


def test_each_console_error_is_paired_with_the_browsers_log_in_order():
    watcher, page = watched()  # the page fetches /favicon.ico, then the browser asks for its icon
    failed_load(page, FAVICON, kind="Fetch", request_id="7.1")
    failed_load(page, FAVICON, kind="Other", request_id="7.2")
    assert len(watcher.problems()) == 1 and list(watcher.known) == [1] and watcher.known[1]["request_id"] == "7.2"
    watcher, page = watched()  # the other way round
    failed_load(page, FAVICON, kind="Other", request_id="7.1")
    failed_load(page, FAVICON, kind="Fetch", request_id="7.2")
    assert len(watcher.problems()) == 1 and list(watcher.known) == [0]
    watcher, page = watched()  # two console errors, one log entry: one is let through
    failed_load(page, FAVICON, request_id="7.1")
    console_error(page, support.FAVICON_404_TEXT, FAVICON)
    assert len(watcher.problems()) == 1 and list(watcher.known) == [0]


def test_the_known_favicon_next_to_another_error_fails_by_the_other():
    watcher, page = watched()
    failed_load(page, FAVICON, request_id="7.1")
    failed_load(page, ORIGIN + "/static/js/pages/edit.js", kind="Script", request_id="7.2")
    page.handlers["pageerror"](RuntimeError("TypeError: x is undefined"))
    assert watcher.problems() == [
        f"コンソールのエラー: ['{support.FAVICON_404_TEXT}（{ORIGIN}/static/js/pages/edit.js）']",
        "ページのエラー（例外）: ['TypeError: x is undefined']",
    ]
    assert list(watcher.known) == [0]


def test_each_known_exception_is_recorded_once():
    config = configured(e2e_required=True)
    item = types.SimpleNamespace(nodeid="tests/e2e/test_x.py::test_x[1280x800]", config=config)
    watcher, page = watched()
    watcher.allow_console_error(r"status of 404")  # a test's own allowance does not hide it from the record
    failed_load(page, FAVICON, request_id="7.1")
    checked = watcher.mark()
    assert watcher.problems(support.PageWatcher.START, checked) == []  # at the end of the test
    failed_load(page, FAVICON, request_id="7.2")  # one more, later
    assert watcher.problems(checked) == []  # at its teardown
    assert watcher.problems() == [] and watcher.problems() == []  # checked again
    tab, tab_page = watched()  # another page of the same test
    failed_load(tab_page, FAVICON, request_id="8.1")
    failed_load(tab_page, ORIGIN + "/static/app.js", kind="Script", request_id="8.2")
    assert len(tab.problems()) == 1  # the test fails by the other error ...
    with pytest.raises(AssertionError):  # ... (here: in its teardown) and still records its known one
        teardown_of(item, error=AssertionError("コンソールのエラー"))
    teardown_of(item)  # the next test's teardown: nothing of this test again
    run = acceptance.state(config)
    assert [(e["nodeid"], e["request_id"]) for e in run.known_console] == [
        (item.nodeid, "7.1"), (item.nodeid, "7.2"), (item.nodeid, "8.1")]


def teardown_of(item, error=None) -> None:
    """tests/e2e/conftest.py's pytest_runtest_teardown, around a teardown
    that went well (error None) or raised `error`."""
    from tests.e2e import conftest

    hook = conftest.pytest_runtest_teardown(item, None)
    next(hook)
    try:
        if error is None:
            hook.send(None)
        else:
            hook.throw(error)
    except StopIteration:
        pass


def test_the_record_lists_each_known_exception():
    config = configured(e2e_required=True)
    run = acceptance.state(config)
    text = acceptance.render_markdown(config, run)
    assert "| 既知の例外（favicon の 404） | 0 件" in text and "件数：0" in text
    run.known_console.append({"nodeid": "tests/e2e/test_x.py::test_x[1280x800]", "url": FAVICON,
                              "text": support.FAVICON_404_TEXT, "status": 404, "type": "Other", "request_id": "7.1"})
    run.cdp_unavailable.append("tests/e2e/test_y.py::test_y[1280x800]：CDP session is only available in Chromium")
    text = acceptance.render_markdown(config, run)
    assert "| 既知の例外（favicon の 404） | 1 件" in text and "件数：1" in text
    assert (f"| `tests/e2e/test_x.py::test_x[1280x800]` | `{FAVICON}` | {support.FAVICON_404_TEXT} "
            "| 404、種類 Other（要求 7.1） |") in text
    assert "検証条件の限定変更" in text and "直したものではありません" in text and "PR-7" in text
    assert "ブラウザの記録（CDP）を読めなかったページが 1 件" in text


def test_the_favicon_exception_lasts_only_while_the_app_has_no_icon():
    """PR-7 adds the icon and removes the exception (tests/e2e/support.py).
    As soon as the app declares an icon or answers /favicon.ico this fails,
    so that a 404 of an icon the app has is never let through."""
    from fastapi.testclient import TestClient

    from app.main import app

    templates = support.FTA_TOOL_DIR / "app" / "templates"
    declared = [str(path.relative_to(templates)) for path in sorted(templates.rglob("*.html"))
                if re.search(r"""rel\s*=\s*["'][^"']*\bicon\b""", path.read_text(encoding="utf-8"), re.IGNORECASE)]
    with TestClient(app) as client:
        status = client.get("/favicon.ico").status_code
    assert declared == [] and status == 404, (
        "アプリに favicon ができました。tests/e2e/support.py の favicon の 404 の例外（FAVICON_404_TEXT など）と"
        f"この確認を削除してください（宣言：{declared}、/favicon.ico：{status}）")


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
    "components.css": ("width: min(520px, calc(100vw - 32px))", "max-height: calc(100vh - 32px)",
                       "max-width: calc(100vw - 16px)", "width: min(560px, calc(100vw - 32px))"),
    "edit.css": ("height: calc(100vh - var(--header-height))",
                 "grid-template-columns: clamp(240px, 17vw, 320px) minmax(0, 1fr) clamp(340px, 23vw, 440px)",
                 "width: clamp(220px, calc((100vw - 560px) / 2 - 2 * var(--space-4)), 360px)"),
    "style.css": ("max-height: 85vh",),
}
VIEWPORT_UNIT = re.compile(r"[\w-]+\s*:[^;{}]*\b\d*\.?\d+(?:[dsl])?v(?:w|h|min|max|i|b)\b[^;{}]*")


def test_the_layout_boundaries_follow_the_edit_pages_stylesheets():
    app = pathlib.Path(acceptance.FTA_TOOL_DIR) / "app"
    sheets = sorted({name for template in EDIT_PAGE_TEMPLATES
                     for name in re.findall(r'href="/static/([^"]+\.css)"',
                                            (app / "templates" / template).read_text(encoding="utf-8"))})
    assert sheets == ["css/base.css", "css/components.css", "css/edit.css", "css/tokens.css", "style.css"]
    found = {}
    for sheet in sheets:
        text = re.sub(r"/\*.*?\*/", "", (app / "static" / sheet).read_text(encoding="utf-8"), flags=re.S)
        assert not re.search(r"@(media|container)\b", text), f"{sheet}：表示領域の条件が加わった（LAYOUT_BOUNDARIES を見直す）"
        rules = tuple(" ".join(rule.split()) for rule in VIEWPORT_UNIT.findall(text))
        if rules:
            found[pathlib.Path(sheet).name] = rules
        if sheet == "css/edit.css":
            assert re.search(r"\.edit-page\s*\{[^}]*min-width:\s*1100px", text)
    assert found == VIEWPORT_RULES, "表示領域に依存する規則が変わった：support.LAYOUT_BOUNDARIES を見直す"
    assert set(support.LAYOUT_BOUNDARIES["width"]) == {
        1280, 1100, 240 / 0.17, 320 / 0.17, 340 / 0.23, 440 / 0.23, 560 + 2 * (220 + 32), 560 + 2 * (360 + 32),
        520 + 32, 560 + 32, 340 + 16}
    assert support.LAYOUT_BOUNDARIES["height"] == ()
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

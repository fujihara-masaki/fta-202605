"""Fixtures for the real-browser tests (Playwright + Chromium, J-26).

* e2e_server (session): the real app, started by stub_server.py in a
  temporary working directory (separate database, stub AI provider, no real
  LLM, outbound HTTP blocked).
* Every test starts with an empty database and the default stub mode, and
  fails if the stub guard recorded a violation.
* page: pytest-playwright's page, run at the plan's base viewports
  (1280x800 and 1440x900; plan 8.0). A console error, an uncaught page error
  or a request to another origin fails the test (E-X01 is checked on every
  test as well as in its own test). The one exception is the browser's own
  404 for /favicon.ico of the test's server, matched with the browser's
  records (tests/e2e/support.py); each one is listed in the report.
* browser: skipped with an explanation when the browser cannot be started
  (a failure in the required run and the preflight, see
  tests/e2e/acceptance.py). With --browser-channel (chrome, msedge) Playwright
  starts the installed browser and never falls back to its own Chromium; the
  record names the channel and what was actually started (its
  chrome://version: maker, version, executable, the temporary profile),
  since browser_type.name is "chromium" for every one of them.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from tests.e2e import acceptance
from tests.e2e.support import PageWatcher, evidence_folder_name, free_port, start_server

VIEWPORTS = [(1280, 800), (1440, 900)]

WATCHER_KEY = pytest.StashKey[PageWatcher]()
CHECKED_KEY = pytest.StashKey[tuple]()  # how far the page was checked at the end of the test

# Element ids of the chrome://version page (Chromium, Google Chrome, Edge).
DESCRIBE_BROWSER = """() => {
  const text = (id) => { const el = document.getElementById(id); return el ? el.textContent.trim() : ''; };
  return { company: text('company'), version: text('version'),
           executable: text('executable_path'), profile: text('profile_path') };
}"""


def launch_failure_message(channel, detail: str) -> str:
    if not channel:
        return ("Chromium を起動できないため実ブラウザのテストを実行できません"
                f"（{detail}）。python -m playwright install chromium を実行してください")
    return (f"ブラウザ（--browser-channel {channel}）を起動できないため実ブラウザのテストを実行できません（{detail}）。"
            "インストール済みのブラウザと、企業のポリシーによる制限を確認してください。"
            "Playwright 同梱の Chromium には切り替えません（ブラウザの導入・更新もしません）")


def describe_browser(browser, channel, headless: bool) -> dict:
    """What was started: from chrome://version, which Chromium's headless
    shell (no channel, headless) does not have."""
    if not channel and headless:
        return {"product": f"Playwright 同梱の Chromium（headless shell）{browser.version}"}
    context = None
    try:
        context = browser.new_context()
        page = context.new_page()
        page.goto("chrome://version", timeout=10000)
        info = page.evaluate(DESCRIBE_BROWSER)
    except Exception as error:  # noqa: BLE001 - informational only (e.g. blocked by a policy)
        detail = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        return {"product": f"{browser.version}（chrome://version を読めませんでした：{detail}）"}
    finally:
        if context is not None:
            context.close()
    version = " ".join(info["version"].split())
    return {
        "product": f"{info['company']} {version}".strip() or browser.version,
        "executable": info["executable"],
        "profile": info["profile"],
    }


@pytest.fixture(scope="session")
def e2e_server(tmp_path_factory, pytestconfig):
    workdir = tmp_path_factory.mktemp("e2e-server")
    server = start_server(workdir, free_port())
    acceptance.state(pytestconfig).server = {
        "url": server.url, "workdir": str(workdir), "log": str(server.log_path)}
    try:
        yield server
    finally:
        server.close()


@pytest.fixture(autouse=True)
def _fresh_server_state(e2e_server):
    e2e_server.reset()
    yield
    violations = e2e_server.violations()
    assert not violations, f"スタブ以外の生成・外部通信が試みられました: {violations}"


@pytest.fixture(scope="session")
def browser(launch_browser, browser_type_launch_args, pytestconfig):
    run = acceptance.state(pytestconfig)
    channel = pytestconfig.getoption("--browser-channel")
    headless = browser_type_launch_args.get("headless", True)
    run.launch = {"headless": headless}
    try:
        launched = launch_browser()
    except Exception as error:  # noqa: BLE001 - e.g. the browser is not installed
        first_line = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        run.launch["error"] = first_line
        pytest.skip(launch_failure_message(channel, first_line))
    run.browser = {
        "name": launched.browser_type.name,  # "chromium" for Chrome and Edge as well
        "version": launched.version,
        "mode": "headless" if headless else "headed",
    }
    run.launch.update(describe_browser(launched, channel, headless))
    yield launched
    launched.close()


@pytest.fixture
def output_path(pytestconfig, request) -> str:
    """Where pytest-playwright keeps a failed test's screenshot and trace
    (--screenshot only-on-failure, --tracing retain-on-failure): its own
    folder name, shortened on Windows (tests/e2e/support.py)."""
    from slugify import slugify  # pytest-playwright's dependency

    output_dir = pathlib.Path(pytestconfig.getoption("--output")).absolute()
    name = evidence_folder_name(request.node.nodeid, request.node.name, slugify, sys.platform == "win32")
    return str(output_dir / name)


@pytest.fixture(params=VIEWPORTS, ids=[f"{w}x{h}" for w, h in VIEWPORTS])
def viewport(request):
    width, height = request.param
    label = f"{width}×{height}"
    run = acceptance.state(request.config)
    if label not in run.viewports:
        run.viewports.append(label)
    return {"width": width, "height": height}


@pytest.fixture
def browser_context_args(browser_context_args, viewport, e2e_server):
    return {
        **browser_context_args,
        "viewport": viewport,
        "locale": "ja-JP",
        "timezone_id": "Asia/Tokyo",
        "base_url": e2e_server.url,
        "accept_downloads": True,
    }


@pytest.fixture
def page(page, viewport, e2e_server, request):
    # `viewport` is requested here (not only through browser_context_args) so
    # that pytest sees the parametrized fixture when it collects the test.
    watcher = PageWatcher(page, e2e_server.url)
    request.node.stash[WATCHER_KEY] = watcher
    page.set_default_timeout(10000)
    yield page
    # What came after the check at the end of the test (pytest_runtest_call).
    problems = watcher.problems(request.node.stash.get(CHECKED_KEY, PageWatcher.START))
    assert not problems, " / ".join(problems)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Check the page at the end of the test itself, so that a console error,
    an uncaught page error or a request to another origin fails the test, not
    only its teardown: pytest-playwright keeps the screenshot and the trace of
    a failed test only. The page fixture checks what comes later."""
    result = yield  # a test that failed already is reported as it is
    watcher = item.stash.get(WATCHER_KEY, None)
    if watcher is not None:
        checked = watcher.mark()  # before the check, which may wait for the browser's records
        problems = watcher.problems(PageWatcher.START, checked)
        item.stash[CHECKED_KEY] = checked
        assert not problems, " / ".join(problems)
    return result


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    """After every fixture's check: the known favicon 404s the test's pages
    let through (tests/e2e/support.py), each once, go to the report."""
    try:
        return (yield)
    finally:
        acceptance.add_known_console(item, PageWatcher.take_made())


@pytest.fixture
def page_watch(page, request) -> PageWatcher:
    return request.node.stash[WATCHER_KEY]

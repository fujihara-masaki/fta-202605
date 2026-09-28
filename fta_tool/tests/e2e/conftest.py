"""Fixtures for the real-browser tests (Playwright + Chromium, J-26).

* e2e_server (session): the real app, started by stub_server.py in a
  temporary working directory (separate database, stub AI provider, no real
  LLM, outbound HTTP blocked).
* Every test starts with an empty database and the default stub mode, and
  fails if the stub guard recorded a violation.
* page: pytest-playwright's page, run at the plan's base viewports
  (1280x800 and 1440x900; plan 8.0). A console error, an uncaught page error
  or a request to another origin fails the test (E-X01 is checked on every
  test as well as in its own test).
* browser: skipped with an explanation when Chromium cannot be started
  (a failure in the required run, see tests/e2e/acceptance.py).
"""

from __future__ import annotations

import socket

import pytest

from tests.e2e import acceptance
from tests.e2e.support import PageWatcher, start_server

VIEWPORTS = [(1280, 800), (1440, 900)]

WATCHER_KEY = pytest.StashKey[PageWatcher]()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def e2e_server(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("e2e-server")
    server = start_server(workdir, _free_port())
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
def browser(launch_browser, pytestconfig):
    try:
        launched = launch_browser()
    except Exception as error:  # noqa: BLE001 - e.g. the browser is not installed
        first_line = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        pytest.skip(
            "Chromium を起動できないため実ブラウザのテストを実行できません"
            f"（{first_line}）。python -m playwright install chromium を実行してください"
        )
    acceptance.state(pytestconfig).browser = {
        "name": launched.browser_type.name,
        "version": launched.version,
        "mode": "headed" if pytestconfig.getoption("--headed") else "headless",
    }
    yield launched
    launched.close()


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
    problems = watcher.problems()
    assert not problems, " / ".join(problems)


@pytest.fixture
def page_watch(page, request) -> PageWatcher:
    return request.node.stash[WATCHER_KEY]

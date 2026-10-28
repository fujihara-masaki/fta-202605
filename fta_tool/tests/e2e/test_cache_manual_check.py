"""Self-check of tests/e2e/cache_manual_check.py (W-02's tool): a browser
driven by Playwright plays the user, so the tool's preparation, version
changes, restarts on the same port, collection and judgement are checked
here. The key presses are simulated (CDP's reload that ignores the cache for
Ctrl+F5, page.reload for F5): this is not W-02 itself, which needs the real
keys in the user's everyday profile (docs/manual-check-pr-c.md).

Each scenario keeps one browser context and one origin (the tool's port)
from start to end; nothing is cleared and no forced reload is used before
the tool asks for Ctrl+F5:
* a profile that has never seen the origin;
* a profile that already holds the origin's files stored the old way,
  without the tool's markers (an earlier installation on that port): the
  tool must see the pages although the cached modules report nothing
  (PR #24 review, discussion_r4377212727);
* the tool run twice in a row in the same profile: the second run must not
  take the first run's reports or markers for its own;
* F5 replaced by a forced reload: NG.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import threading
import time

import pytest

from tests.e2e import cache_manual_check
from tests.e2e.static_assets import APP_STATIC
from tests.e2e.support import free_port, start_server

pytestmark = [pytest.mark.e2e]

TEN_DAYS = 10 * 24 * 3600


def wait_state(out: pathlib.Path, phase: str, waiting_for: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = json.loads((out / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if state.get("phase") == phase and state.get("waiting_for") == waiting_for:
            return state
        time.sleep(0.2)
    raise AssertionError(f"the tool did not reach {phase} / {waiting_for}")


def ctrl_f5(page) -> None:
    session = page.context.new_cdp_session(page)
    try:
        with page.expect_navigation():
            session.send("Page.reload", {"ignoreCache": True})
    finally:
        session.detach()


def settle(page) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(400)  # the page's report goes at its load event


def open_three(page, base: str, analysis_id) -> None:
    """What the user does in step 1: the list, the form, the list, the edit screen."""
    page.goto(base + "/")
    settle(page)
    page.locator('.app-header__nav a[href="/analyses/new"]').click()
    settle(page)
    page.locator('.app-header__nav a[href="/"]').click()
    settle(page)
    page.locator(f'a[data-edit-link][href="/analyses/{analysis_id}"]').click()
    settle(page)


def play(page, out: pathlib.Path, port: int, last_reload) -> tuple[int, dict]:
    """Run the tool on `port` and do what its instructions ask, in `page`."""
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault(
        "code", cache_manual_check.main(["--out", str(out), "--port", str(port), "--timeout-minutes", "2"])))
    thread.start()
    try:
        state = wait_state(out, "A", "3画面を通常に開く")
        base = f"http://127.0.0.1:{port}"
        edit = f'a[data-edit-link][href="/analyses/{state["analysis_id"]}"]'
        open_three(page, base, state["analysis_id"])
        wait_state(out, "B", "3画面で Ctrl+F5")
        for link in ('.app-header__nav a[href="/"]', '.app-header__nav a[href="/analyses/new"]'):
            page.locator(link).click()
            settle(page)
            ctrl_f5(page)
            settle(page)
        page.locator('.app-header__nav a[href="/"]').click()
        settle(page)
        page.locator(edit).click()
        settle(page)
        ctrl_f5(page)
        settle(page)
        wait_state(out, "C", "編集画面で F5")
        last_reload(page)
        settle(page)
    finally:
        thread.join(timeout=180)
    return result.get("code"), json.loads((out / "result.json").read_text(encoding="utf-8"))


def phase_a_requests(out: pathlib.Path) -> list[dict]:
    """The browser's static requests before the first restart (phase A)."""
    rows = [json.loads(line) for line in (out / "static-requests.jsonl").read_text(encoding="utf-8").splitlines()]
    first_policy_app = next((i for i, r in enumerate(rows) if r.get("policy") == "app"), len(rows))
    return [r for r in rows[:first_policy_app] if r.get("client") == "browser" and r["path"].startswith("/static/")]


@pytest.fixture
def context(browser):
    context = browser.new_context()
    try:
        yield context
    finally:
        context.close()


def test_the_w02_tool_judges_a_correct_run_ok(context, tmp_path):
    page = context.new_page()
    code, result = play(page, tmp_path / "record", free_port(), lambda p: p.reload())
    assert code == 0, result
    assert result["verdict"] == "OK" and result["preparation"]["coverage"] == "すべて"
    names = [r["item"] for r in result["results"]]
    assert all(r["ok"] for r in result["results"]), result["results"]
    assert "手順3：変更していない31件がそれぞれ 304" in names
    assert "手順3：編集画面の34件がそれぞれ要求された（ファイルの一致）" in names
    assert [r["operated_by"] for r in result["results"]].count("利用者の実操作") == 4
    assert not (tmp_path / "record" / "work").exists()  # the copy and the test database are removed
    assert (tmp_path / "record" / "w02-output.log").exists() and (tmp_path / "record" / "server.log").exists()


def test_the_w02_tool_starts_from_files_cached_without_its_markers(context, tmp_path):
    """The origin's files were stored the old way by another server on the
    same port, without the tool's markers; the tool sees the three pages
    although those cached modules report nothing, and goes on to step 2."""
    port = free_port()
    workdir = tmp_path / "earlier"
    workdir.mkdir()
    static = workdir / "static"
    shutil.copytree(APP_STATIC, static)
    old = time.time() - TEN_DAYS
    for path in static.rglob("*"):
        if path.is_file():
            os.utime(path, (old, old))
    (workdir / "static_control.json").write_text('{"policy": "baseline"}', encoding="utf-8")
    earlier = start_server(workdir, port, {"FTA_E2E_STATIC_DIR": str(static)})
    page = context.new_page()
    try:
        analysis_id = earlier.create_analysis("以前の分析", top_event="頂上")
        open_three(page, earlier.url, analysis_id)
    finally:
        earlier.close()
    assert page.evaluate("() => globalThis.__ftaCacheProbe === undefined")  # no marker in those files

    out = tmp_path / "record"
    code, result = play(page, out, port, lambda p: p.reload())
    assert code == 0, result
    # Step 1 fetched no static file again (the old, unmarked dom.js and the
    # rest were used from the cache) and the pages were still seen.
    assert phase_a_requests(out) == []
    states = set(result["preparation"] and result["observed"]["A"]["states"].values())
    assert states == {"要求なし（保存済みを検証なしで使用。旧方式の保存）"}
    seen = result["observed"]["A"]["probes"]
    assert {p["path"] for p in seen} >= {"/", "/analyses/new"} and all(p["css"] == "" and p["js"] == {} for p in seen)
    assert all(r["ok"] for r in result["results"]), result["results"]


def test_the_w02_tool_twice_in_the_same_profile(context, tmp_path):
    """Run 1 leaves no-cache responses (Last-Modified 2001-01-01); run 2 still
    prepares the old way, and takes only its own reports and markers."""
    port = free_port()
    page = context.new_page()
    first_code, first = play(page, tmp_path / "first", port, lambda p: p.reload())
    assert first_code == 0, first
    second_code, second = play(page, tmp_path / "second", port, lambda p: p.reload())
    assert second_code == 0, second
    assert first["run"] != second["run"]
    # Run 2's step 1: every file was confirmed with run 1's stored response and
    # sent again without Cache-Control (stored the old way again).
    assert set(second["observed"]["A"]["states"].values()) == {"200・Cache-Control なし（旧方式で保存）"}
    for phase in ("A", "B"):
        assert all(p["run"] == second["run"] for p in second["observed"][phase]["probes"])
    probe = second["observed"]["C"]["probe"]
    assert probe["css"] == f"{second['run']}-w2" and all(v == f"{second['run']}-w2" for v in probe["js"].values())
    # Run 1's reports stay in run 1's record only.
    assert all(json.loads(line)["data"]["run"] == second["run"]
               for line in (tmp_path / "second" / "probe.jsonl").read_text(encoding="utf-8").splitlines())


def test_the_w02_tool_refuses_a_reload_that_bypasses_the_cache(context, tmp_path):
    page = context.new_page()
    code, result = play(page, tmp_path / "record", free_port(), ctrl_f5)
    assert code == 1
    failed = [r["item"] for r in result["results"] if not r["ok"]]
    assert "手順3：F5 が通常の再読み込み" in failed, failed

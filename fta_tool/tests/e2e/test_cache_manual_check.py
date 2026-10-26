"""Self-check of tests/e2e/cache_manual_check.py (W-02's tool): a browser
driven by Playwright plays the user, so the tool's preparation, version
changes, restarts on the same port, collection and judgement are checked
here. The key presses are simulated (CDP's reload that ignores the cache for
Ctrl+F5, page.reload for F5): this is not W-02 itself, which needs the real
keys in the user's everyday profile (docs/manual-check-pr-c.md).
"""

from __future__ import annotations

import json
import pathlib
import threading
import time

import pytest

from tests.e2e import cache_manual_check
from tests.e2e.support import free_port

pytestmark = [pytest.mark.e2e]


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
    page.wait_for_timeout(300)  # the page's report goes at its load event


def play(browser, tmp_path, last_reload) -> tuple[int, dict]:
    out = tmp_path / "record"
    port = free_port()
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault(
        "code", cache_manual_check.main(["--out", str(out), "--port", str(port), "--timeout-minutes", "2"])))
    thread.start()
    context = browser.new_context()
    page = context.new_page()
    try:
        state = wait_state(out, "A", "3画面を通常に開く")
        base = f"http://127.0.0.1:{port}"
        edit = f'a[data-edit-link][href="/analyses/{state["analysis_id"]}"]'
        page.goto(base + "/")
        settle(page)
        page.locator('.app-header__nav a[href="/analyses/new"]').click()
        settle(page)
        page.locator('.app-header__nav a[href="/"]').click()
        settle(page)
        page.locator(edit).click()
        settle(page)
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
        context.close()
    return result.get("code"), json.loads((out / "result.json").read_text(encoding="utf-8"))


def test_the_w02_tool_judges_a_correct_run_ok(browser, tmp_path):
    code, result = play(browser, tmp_path, lambda page: page.reload())
    assert code == 0, result["results"]
    assert result["verdict"] == "OK"
    items = {r["item"]: r for r in result["results"]}
    assert any("38件" in name and r["ok"] for name, r in items.items())
    assert [r["operated_by"] for r in result["results"]].count("利用者の実操作") == 4
    assert not (tmp_path / "record" / "work").exists()  # the copy and the test database are removed


def test_the_w02_tool_refuses_a_reload_that_bypasses_the_cache(browser, tmp_path):
    code, result = play(browser, tmp_path, ctrl_f5)
    assert code == 1
    failed = [r["item"] for r in result["results"] if not r["ok"]]
    assert "手順3：F5（利用者の実操作）が通常の再読み込みだった" in failed, failed

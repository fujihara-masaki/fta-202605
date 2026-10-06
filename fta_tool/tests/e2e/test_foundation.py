"""E2E: shared foundation (PR-1) — E-X01 and the PR1-BASE / PR1-STUB checks.

* E-X01: no request leaves the app on any screen (also checked after every
  E2E test by the page fixture), no web font is declared.
* PR1-BASE-NOTIFY: J-24 — success/warning notifications close by themselves,
  errors stay until closed; live regions for screen readers.
* PR1-BASE-STORAGE: with Web Storage unavailable the list still works and
  the safe storage helper does not throw (C-10).
* PR1-BASE-A11Y: skip link, aria-current in the header, dialog focus.
* PR1-STUB: the stub AI provider used by the E2E server, and its guard
  against real LLM calls and outbound HTTP.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from tests.e2e.support import FTA_TOOL_DIR, expect

pytestmark = pytest.mark.e2e


# ----- E-X01 ----------------------------------------------------------------

@pytest.mark.acceptance("E-X01")
def test_E_X01_no_request_leaves_the_app(page, page_watch, e2e_server):
    analysis_id = e2e_server.create_analysis(
        "外部通信の確認", top_event="頂上事象", system_context="構成", incident_context="状況")
    parent = e2e_server.add_level1(analysis_id, "一次要因")
    e2e_server.add_child(parent, "二次要因")

    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    page.locator(f'tr[data-analysis-id="{analysis_id}"] [data-ui-menu-button]').click()
    page.keyboard.press("Escape")
    page.locator(f'tr[data-analysis-id="{analysis_id}"] [data-action="delete"]').click()
    page.keyboard.press("Escape")
    page.locator(f'tr[data-analysis-id="{analysis_id}"] [data-action="rename"]').click()
    page.keyboard.press("Escape")
    fonts_on_list = page.evaluate(
        """() => [...document.styleSheets].flatMap((sheet) => {
             try { return [...sheet.cssRules]; } catch { return []; }
           }).filter((rule) => rule instanceof CSSFontFaceRule).length"""
    )
    font_family = page.evaluate("getComputedStyle(document.body).fontFamily")

    page.goto("/analyses/new")
    expect(page.locator("h1")).to_have_text("新規FTA分析を作成")
    page.locator("#sampleSelect").select_option(index=1)
    page.get_by_role("button", name="この内容を入力欄へ転記").click()
    page.locator("[data-cancel-link]").click()
    page.get_by_role("dialog", name="作成していない入力があります").get_by_role("button", name="破棄して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")

    page.goto(f"/analyses/{analysis_id}")
    expect(page.locator("#analysisTitle")).to_have_text("外部通信の確認")
    page.locator('[data-action="select"][data-role="nav"]').last.click()  # inspector reads the details
    page.locator('[data-view-tab="tree"]').click()
    page.locator('[data-view-tab="table"]').click()
    page.fill("#edit-filter-text", "二次")
    page.wait_for_load_state("networkidle")

    paths = {url.removeprefix(e2e_server.url) for url in page_watch.requests}
    for expected in ("/", "/analyses/new", f"/analyses/{analysis_id}",
                     "/static/css/tokens.css", "/static/js/common/boot.js", "/static/js/pages/list.js",
                     "/static/css/new.css", "/static/js/pages/new.js",
                     "/static/css/edit.css", "/static/js/pages/edit.js", "/static/js/pages/edit/model.js",
                     "/static/style.css", "/static/app.js"):
        assert expected in paths, f"{expected} was not requested: {sorted(paths)}"
    assert page_watch.foreign_requests == []
    assert all(url.startswith(e2e_server.url) for url in page_watch.requests)
    assert fonts_on_list == 0  # no web font (J-28)
    assert font_family.startswith('"BIZ UDPGothic"')


# ----- PR1-BASE-NOTIFY --------------------------------------------------------

@pytest.mark.acceptance("PR1-BASE-NOTIFY")
def test_notifications_success_closes_error_stays(page, page_watch, e2e_server):
    analysis_id = e2e_server.create_analysis("通知の確認")
    page.clock.install()
    page.goto("/")
    page_watch.allow_console_error(r"status of 500")
    row = page.locator(f'tr[data-analysis-id="{analysis_id}"]')

    # Success: shown, announced politely, closes after 3 s.
    row.locator('[data-action="rename"]').click()
    row.locator("[data-rename-editor] input").fill("通知の確認（保存）")
    row.locator("[data-rename-editor] input").press("Enter")
    success = page.locator(".ui-toast--success")
    expect(success).to_contain_text("タイトルを保存しました")
    expect(success.locator(".ui-toast__kind")).to_have_text("完了")
    expect(page.locator("#ui-live-status")).to_have_text("完了：タイトルを保存しました")
    page.clock.run_for(3500)
    expect(success).to_have_count(0)

    # Warning: closes after 6 s (the list itself has no warning; call the module).
    page.evaluate("async () => (await import('/static/js/common/notify.js')).notify('確認用の注意', { type: 'warning' })")
    warning = page.locator(".ui-toast--warning")
    expect(warning).to_contain_text("確認用の注意")
    page.clock.run_for(3500)
    expect(warning).to_have_count(1)
    page.clock.run_for(3000)
    expect(warning).to_have_count(0)

    # Error: stays until closed (J-24), announced assertively.
    page.route(f"**/analyses/{analysis_id}/title", lambda r: r.fulfill(status=500, json={"detail": "E2E: 通知確認用のエラー"}))
    row.locator('[data-action="rename"]').click()
    row.locator("[data-rename-editor] input").fill("失敗させる名前")
    row.locator("[data-rename-editor] input").press("Enter")
    error = page.locator(".ui-toast--error")
    expect(error).to_contain_text("E2E: 通知確認用のエラー")
    expect(error.locator(".ui-toast__kind")).to_have_text("エラー")
    expect(page.locator("#ui-live-alert")).to_contain_text("E2E: 通知確認用のエラー")
    page.clock.run_for(60000)
    expect(error).to_have_count(1)
    error.get_by_role("button", name="閉じる").click()
    expect(error).to_have_count(0)

    # Live regions are present with the expected roles.
    expect(page.locator("#ui-live-status")).to_have_attribute("role", "status")
    expect(page.locator("#ui-live-alert")).to_have_attribute("role", "alert")


@pytest.mark.acceptance("PR1-BASE-NOTIFY")
def test_notification_stack_stays_bounded(page, e2e_server):
    """Persistent errors must not pile up and cover the page (PR #16 review)."""
    page.goto("/")
    page.evaluate(
        """async () => {
             const { notify } = await import('/static/js/common/notify.js');
             for (let i = 0; i < 4; i += 1) notify('同じエラー', { type: 'error' });
           }"""
    )
    errors = page.locator(".ui-toast--error")
    expect(errors).to_have_count(1)  # the same error again updates the one shown
    expect(errors).to_contain_text("同じエラー（4回）")

    max_toasts = page.evaluate("async () => (await import('/static/js/common/notify.js')).MAX_TOASTS")
    page.evaluate(
        """async () => {
             const { notify } = await import('/static/js/common/notify.js');
             for (let i = 1; i <= 7; i += 1) notify(`別のエラー${i}`, { type: 'error' });
             notify('最新の完了', { type: 'success' });
           }"""
    )
    expect(page.locator(".ui-toast")).to_have_count(max_toasts)
    expect(page.locator(".ui-toast--success")).to_contain_text("最新の完了")  # the newest is kept
    expect(errors).to_have_text([re.compile(f"別のエラー{i}") for i in (4, 5, 6, 7)])
    expect(page.locator(".ui-toast", has_text="同じエラー")).to_have_count(0)  # oldest closed first


# ----- PR1-BASE-STORAGE -------------------------------------------------------

BLOCK_STORAGE = """
for (const name of ['localStorage', 'sessionStorage']) {
  Object.defineProperty(window, name, {
    configurable: true,
    get() { throw new DOMException('storage blocked for the test', 'SecurityError'); },
  });
}
"""


@pytest.mark.acceptance("PR1-BASE-STORAGE")
def test_list_works_without_web_storage(page, e2e_server):
    analysis_id = e2e_server.create_analysis("保存領域なし")
    page.add_init_script(BLOCK_STORAGE)
    page.goto("/")
    assert page.evaluate("() => { try { window.localStorage; return 'available'; } catch { return 'blocked'; } }") == "blocked"

    result = page.evaluate(
        """async () => {
             const { sessionStore, localStore, createSafeStorage } = await import('/static/js/common/storage.js');
             const other = createSafeStorage('sessionStorage');
             return {
               available: [sessionStore.available, localStore.available, other.available],
               get: sessionStore.getItem('x'),
               set: sessionStore.setItem('x', '1'),
               remove: localStore.removeItem('x'),
               json: localStore.getJSON('x', 'fallback'),
               setJson: localStore.setJSON('x', { a: 1 }),
             };
           }"""
    )
    assert result == {
        "available": [False, False, False],
        "get": None,
        "set": False,
        "remove": False,
        "json": "fallback",
        "setJson": False,
    }

    # The screen keeps working: rename, export menu, delete dialog.
    row = page.locator(f'tr[data-analysis-id="{analysis_id}"]')
    row.locator('[data-action="rename"]').click()
    row.locator("[data-rename-editor] input").fill("保存領域なしで改名")
    row.locator("[data-rename-editor] input").press("Enter")
    expect(row.locator("[data-title-link]")).to_have_text("保存領域なしで改名")
    row.locator("[data-ui-menu-button]").click()
    expect(page.locator(f"#export-menu-{analysis_id}")).to_be_visible()
    page.keyboard.press("Escape")
    row.locator('[data-action="delete"]').click()
    page.get_by_role("dialog", name="分析を削除しますか？").get_by_role("button", name="削除する").click()
    expect(page.locator("[data-empty-state]")).to_be_visible()


@pytest.mark.acceptance("PR1-BASE-STORAGE")
def test_safe_storage_round_trip_when_available(page, e2e_server):
    page.goto("/")
    result = page.evaluate(
        """async () => {
             const { sessionStore } = await import('/static/js/common/storage.js');
             const ok = sessionStore.setJSON('fta:test', { value: 1 });
             const back = sessionStore.getJSON('fta:test');
             sessionStore.removeItem('fta:test');
             return { available: sessionStore.available, ok, back, after: sessionStore.getItem('fta:test') };
           }"""
    )
    assert result == {"available": True, "ok": True, "back": {"value": 1}, "after": None}


# ----- PR1-BASE-A11Y ----------------------------------------------------------

@pytest.mark.acceptance("PR1-BASE-A11Y")
def test_skip_link_header_and_dialog_focus(page, e2e_server):
    analysis_id = e2e_server.create_analysis("アクセシビリティ")
    nav = page.get_by_role("navigation", name="メインメニュー")

    page.goto("/")
    page.keyboard.press("Tab")
    skip = page.get_by_role("link", name="本文へ移動")
    expect(skip).to_be_focused()
    expect(skip).to_be_in_viewport()
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"
    expect(nav.get_by_role("link", name="分析一覧")).to_have_attribute("aria-current", "page")
    expect(nav.get_by_role("link", name="新規作成")).not_to_have_attribute("aria-current", "page")

    # Dialog opened from the keyboard: safe choice focused, Esc returns focus.
    delete = page.locator(f'tr[data-analysis-id="{analysis_id}"] [data-action="delete"]')
    delete.focus()
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="分析を削除しますか？")
    expect(dialog.get_by_role("button", name="キャンセル")).to_be_focused()
    page.keyboard.press("Tab")
    expect(dialog.get_by_role("button", name="削除する")).to_be_focused()
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(delete).to_be_focused()

    page.goto("/analyses/new")
    expect(nav.get_by_role("link", name="新規作成")).to_have_attribute("aria-current", "page")
    expect(nav.get_by_role("link", name="分析一覧")).not_to_have_attribute("aria-current", "page")
    page.goto(f"/analyses/{analysis_id}")
    expect(nav.locator("[aria-current]")).to_have_count(0)


# ----- PR1-STUB ---------------------------------------------------------------

@pytest.mark.acceptance("PR1-STUB")
def test_stub_modes_through_the_generate_api(e2e_server):
    analysis_id = e2e_server.create_analysis("スタブ確認", top_event="頂上事象")

    created = e2e_server.generate(analysis_id, 1)
    assert created["success"] is True and created["created"] == 4  # FTA_PRIMARY_FACTOR_COUNT pinned to 4

    e2e_server.set_stub_mode("no_candidates")
    none = e2e_server.generate(analysis_id, 1, additional=True)
    assert none["success"] is True and none["created"] == 0
    assert none["message"] == "生成候補がありませんでした（LLMが要因を返しませんでした）。"

    e2e_server.set_stub_mode("error")
    failed = e2e_server.generate(analysis_id, 1)
    assert failed["success"] is False
    assert "E2Eスタブ：生成に失敗しました" in failed["message"]

    calls = e2e_server.stub_calls()
    assert [c["mode"] for c in calls] == ["create", "no_candidates", "error"]
    assert [c["target_level"] for c in calls] == [1, 1, 1]
    assert calls[1]["additional"] is True
    assert e2e_server.violations() == []


GUARD_PROBE = r"""
import json, os, pathlib, sys, types
sys.path.insert(0, os.environ["FTA_TOOL_DIR"])
from tests.e2e import stub_server
import httpx
from app.services import ai_provider

workdir = pathlib.Path(os.environ["PROBE_WORKDIR"])
fake_main = types.SimpleNamespace(get_ai_provider=None)
stub_server.install_guards(fake_main, workdir)
outcome = {"stub": type(fake_main.get_ai_provider()).__name__}
try:
    ai_provider.get_ai_provider()
    outcome["provider"] = "not blocked"
except RuntimeError as error:
    outcome["provider"] = str(error)
try:
    httpx.Client().get("http://example.invalid/")
    outcome["http"] = "not blocked"
except httpx.ConnectError as error:
    outcome["http"] = str(error)
print(json.dumps(outcome, ensure_ascii=False))
"""


@pytest.mark.acceptance("PR1-STUB")
def test_stub_guard_blocks_real_provider_and_outbound_http(tmp_path):
    # Runs the guard in a separate interpreter so this process stays untouched.
    env = {**os.environ, "FTA_TOOL_DIR": str(FTA_TOOL_DIR), "PROBE_WORKDIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-c", GUARD_PROBE], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=120, check=True,
    )
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    assert outcome == {
        "stub": "StubProvider",
        "provider": "E2E: 実LLMプロバイダは使用できません",
        "http": "E2E: 外部への通信は禁止されています",
    }
    recorded = [json.loads(line)["message"] for line in (pathlib.Path(tmp_path) / "violations.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(recorded) == 2
    assert "実プロバイダの取得" in recorded[0]
    assert "外部への通信を遮断しました: GET http://example.invalid/" in recorded[1]

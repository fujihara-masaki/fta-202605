"""E2E: the screens that are not migrated yet keep working (PR-1).

PR-1 changes the shared frame (base.html: header, notifications, shared
CSS/JS). The new-analysis form (migrated in PR-2) and the analysis detail
page (PR-3 to PR-6) still use app.js / style.css; these tests drive their
main operations in the browser: create, sample, cancel, title / top event /
context save, generation through the stub, judgement, detail modal, manual
add, delete, export and back to the list.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e


def _unify(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


@pytest.mark.acceptance("PR1-COMPAT-NEW")
def test_new_analysis_form_create_sample_and_cancel(page, e2e_server):
    page.goto("/analyses/new")
    nav = page.get_by_role("navigation", name="メインメニュー")
    expect(nav.get_by_role("link", name="新規作成")).to_have_attribute("aria-current", "page")

    page.fill("#title", "互換確認（新規作成）")
    page.fill("#top_event", "互換確認の頂上事象")
    page.fill("#systemContextInput", "Webサーバ2台")
    page.fill("#incidentContextInput", "9時から500エラー")
    page.get_by_role("button", name="作成して編集へ").click()
    expect(page).to_have_url(re.compile(r"/analyses/\d+$"))
    analysis_id = int(page.url.rsplit("/", 1)[1])
    expect(page.locator("#analysisTitle")).to_have_text("互換確認（新規作成）")
    stored = e2e_server.analysis(analysis_id)
    assert stored["top_event"] == "互換確認の頂上事象"
    assert json.loads(stored["analysis_context"]) == {
        "system_context": "Webサーバ2台",
        "incident_context": "9時から500エラー",
        "demo_points": "",
    }

    # Sample: preview, apply (title is not filled: J-21 / current behaviour).
    page.goto("/analyses/new")
    page.get_by_role("button", name="デモ用サンプルを利用する").click()
    select = page.locator("#sampleSelect")
    first_value = select.locator("option").nth(1).get_attribute("value")
    select.select_option(first_value)
    expect(page.locator("#samplePreview")).to_be_visible()
    page.get_by_role("button", name="このサンプルを入力").click()
    expect(page.locator("#title")).to_have_value("")
    top_event = page.input_value("#top_event")
    assert top_event and top_event == page.text_content("#samplePreviewTopEvent")
    demo_points = page.input_value("#demoPointsInput")
    assert demo_points
    page.fill("#title", "サンプルから作成")
    page.get_by_role("button", name="作成して編集へ").click()
    expect(page).to_have_url(re.compile(r"/analyses/\d+$"))
    sample_id = int(page.url.rsplit("/", 1)[1])
    exported = json.loads(e2e_server.export(sample_id, "json"))
    assert exported["top_event"] == top_event
    # Form submission sends line breaks as CRLF and the server strips the
    # value (unchanged behaviour), so compare with line endings unified.
    assert _unify(exported["analysis_context"]["demo_points"]) == _unify(demo_points)

    # Cancel goes back to the list without a confirmation (PR-2 adds one).
    dialogs = record_dialogs(page)
    page.goto("/analyses/new")
    page.fill("#title", "キャンセルする入力")
    page.get_by_role("link", name="キャンセル").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert dialogs == []


@pytest.mark.acceptance("PR1-COMPAT-EDIT")
def test_analysis_detail_legacy_operations(page, e2e_server):
    analysis_id = e2e_server.create_analysis("互換確認（編集）", top_event="最初の頂上事象")
    page.goto(f"/analyses/{analysis_id}")
    expect(page.locator(".ai-badge")).to_have_text("AI: e2e-stub")  # stub server, not a real LLM
    expect(page.get_by_role("navigation", name="メインメニュー").locator("[aria-current]")).to_have_count(0)

    # Title (contenteditable, saved on blur/Enter; the edit page names the tab).
    title = page.locator("#analysisTitle")
    title.click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("互換確認（改名）")
    page.keyboard.press("Enter")
    expect(page.locator("#toast")).to_contain_text("タイトルを保存しました")
    expect(page).to_have_title("互換確認（改名） - FTA編集")
    assert e2e_server.analysis(analysis_id)["title"] == "互換確認（改名）"

    # Top event and analysis context.
    page.fill("#topEventInput", "編集後の頂上事象")
    page.locator(".top-event-card").get_by_role("button", name="保存").click()
    expect(page.locator("#toast")).to_contain_text("頂上事象を保存しました")
    page.locator("#analysisContextDetails > summary").click()
    page.fill("#systemContextInput", "編集後のシステム構成")
    page.get_by_role("button", name="コンテキストを保存").click()
    expect(page.locator("#analysisContextStatus")).to_have_text("入力済み")
    stored = e2e_server.analysis(analysis_id)
    assert stored["top_event"] == "編集後の頂上事象"
    assert json.loads(stored["analysis_context"])["system_context"] == "編集後のシステム構成"

    # Level-1 generation through the stub (page reloads when created).
    page.get_by_role("button", name="一次要因を生成").click()
    level1 = page.locator("#col-level1 .node-card")
    expect(level1).to_have_count(4)

    # Judgement Yes, then level-2 generation for the Yes parent.
    first = level1.first
    first.get_by_role("button", name="Yes").click()
    expect(first).to_have_class(re.compile(r"\byes\b"))
    expect(page.locator("#toast")).to_contain_text("評価を更新しました")
    page.get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    level2 = page.locator("#col-level2 .node-card")
    expect(level2).to_have_count(3)
    calls = e2e_server.stub_calls()
    assert [c["target_level"] for c in calls] == [1, 2]

    # Detail modal: memo saved without touching the judgement. The legacy
    # page reloads shortly after a save; wait for that reload each time.
    first_id = int(level1.first.get_attribute("data-node-id"))
    level1.first.get_by_role("button", name="詳細編集").click()
    expect(page.locator("#nodeDetailModal")).to_be_visible()
    page.fill("#modalMemo", "互換確認のメモ")
    with page.expect_navigation():
        page.locator("#modalSaveBtn").click()
    node = e2e_server.get_node(first_id)
    assert node["memo"] == "互換確認のメモ" and node["user_judgement"] == "yes"

    # Manual add (level 1).
    page.locator(".fta-column").first.get_by_role("button", name="手動追加").click()
    page.fill("#addNodeTitle", "手動で追加した要因")
    with page.expect_navigation():
        page.locator("#addNodeModal").get_by_role("button", name="追加").click()
    expect(page.locator("#col-level1 .node-card", has_text="手動で追加した要因")).to_have_count(1)

    # Delete a level-2 factor (native confirm, accepted).
    dialogs = record_dialogs(page, action="accept")
    with page.expect_navigation():
        level2.first.get_by_role("button", name="削除").click()
    expect(page.locator("#col-level2 .node-card")).to_have_count(2)
    assert dialogs == ["confirm"]

    # Tree and table views, filter.
    page.locator("#ftaTreeDetails > summary").click()
    expect(page.locator(".fta-tree-view")).to_be_visible()
    page.locator("#ftaTableDetails > summary").click()
    expect(page.locator(".node-table-row")).to_have_count(7)
    page.fill("#nodeFilterText", "手動で追加")
    expect(page.locator("#nodeFilterCount")).to_have_text("1/7件を表示")

    # Export from the header, then back to the list.
    with page.expect_download() as download_info:
        page.get_by_role("link", name="JSON出力").click()
    assert download_info.value.suggested_filename == f"fta_{analysis_id}.json"
    with open(download_info.value.path(), "rb") as handle:
        exported = json.loads(handle.read())
    assert exported["title"] == "互換確認（改名）"
    assert len(exported["nodes"]) == 7

    page.get_by_role("link", name="一覧へ").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    expect(page.locator(f'tr[data-analysis-id="{analysis_id}"] [data-title-link]')).to_have_text("互換確認（改名）")
    expect(page.locator(f'tr[data-analysis-id="{analysis_id}"]')).to_have_attribute("data-factor-count", "7")

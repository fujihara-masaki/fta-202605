"""E2E: the screen that is not migrated yet keeps working.

PR-1 changed the shared frame (base.html: header, notifications, shared
CSS/JS). The analysis detail page (migrated in PR-3 to PR-6) still uses
app.js / style.css; this test drives its main operations in the browser:
title / top event / context save, generation through the stub, judgement,
detail modal, manual add, delete, export and back to the list.

The new-analysis form had the same check (PR1-COMPAT-NEW) until PR-2
migrated it; it is now covered by tests/e2e/test_new_analysis_page.py
(E-N01〜E-N06).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e


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

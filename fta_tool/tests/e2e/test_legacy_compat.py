"""E2E: the parts of the edit screen that still run on the old processing.

PR-3 builds the new edit screen but keeps app.js for the title and step ①
saving, generation, the detail dialog, manual add and delete (plan 7.2;
acceptance 10 of plan 8.3: UI-09〜UI-14 stay usable, and the normal
generation of 二次・三次 still includes Yes parents hidden by the filter).
PR3-LEGACY-OPS drives them from the new page.

Until PR-3 the old screen had this check as PR1-COMPAT-EDIT; the
new-analysis form had PR1-COMPAT-NEW until PR-2 (now E-N01〜E-N06).
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.edit_helpers import (
    chip,
    expect_selected,
    inspector,
    inspector_title,
    item,
    judgement_button,
    open_edit,
    select_button,
    step_button,
    step_panel,
    wait_until,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e


@pytest.mark.acceptance("PR3-LEGACY-OPS")
def test_title_step1_and_generation_from_the_new_page(page, e2e_server):
    analysis_id = e2e_server.create_analysis("互換確認（編集）", top_event="最初の頂上事象")
    open_edit(page, analysis_id)
    expect(page.locator(".ai-badge")).to_have_text("AI: e2e-stub")  # stub server, not a real LLM
    expect(page.get_by_role("navigation", name="メインメニュー").locator("[aria-current]")).to_have_count(0)

    # Title (legacy contenteditable, saved on Enter; the edit page names the tab).
    title = page.locator("#analysisTitle")
    title.click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("互換確認（改名）")
    page.keyboard.press("Enter")
    expect(page).to_have_title("互換確認（改名） - FTA編集")
    wait_until(lambda: e2e_server.analysis(analysis_id)["title"] == "互換確認（改名）")

    # Step ① keeps the ids and the save functions of the old screen.
    page.fill("#topEventInput", "編集後の頂上事象")
    step_panel(page, 1).get_by_role("button", name="保存", exact=True).click()
    expect(page.locator("#topEventInput")).to_have_attribute("data-saved", "編集後の頂上事象")
    expect(step_button(page, 1)).to_contain_text("頂上事象：入力済み")
    expect(page.locator('#edit-nav [data-select="top"]')).to_contain_text("編集後の頂上事象")
    page.fill("#systemContextInput", "編集後のシステム構成")
    page.get_by_role("button", name="コンテキストを保存").click()
    expect(page.locator("#analysisContextStatus")).to_have_text("入力済み")
    stored = e2e_server.analysis(analysis_id)
    assert stored["top_event"] == "編集後の頂上事象"
    assert json.loads(stored["analysis_context"])["system_context"] == "編集後のシステム構成"

    # 一次要因 from the operation bar of ② (the stub creates four).
    step_button(page, 2).click()
    step_panel(page, 2).get_by_role("button", name="一次要因を生成").click()
    rows = step_panel(page, 2).locator('[data-role="work-item"]')
    expect(rows).to_have_count(4)
    ids = [int(value) for value in rows.evaluate_all("els => els.map((e) => e.dataset.nodeId)")]
    titles = rows.locator(".edit-row__title").all_text_contents()

    # Two Yes parents; the filter hides the second one.
    for node_id in ids[:2]:
        judgement_button(item(page, "work", node_id), node_id, "yes").click()
        expect(chip(page.locator("#edit-nav"), node_id)).to_have_text("Yes")
    page.fill("#edit-filter-text", titles[0])
    expect(item(page, "work", ids[1])).to_be_hidden()

    # 二次要因 for every Yes parent, hidden or not (J-07), in order.
    step_button(page, 3).click()
    expect(page.locator('[data-target-count="2"]')).to_have_text("2")
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    for parent_id in ids[:2]:
        expect(page.locator(f'[data-group-parent="{parent_id}"] [data-role="work-item"]')).to_have_count(3)
    calls = e2e_server.stub_calls()
    assert [call["target_level"] for call in calls] == [1, 2, 2]
    assert [call["parent_factor"] for call in calls[1:]] == titles[:2]
    assert e2e_server.node_count(analysis_id) == 10


@pytest.mark.acceptance("PR3-LEGACY-OPS")
def test_detail_dialog_manual_add_additional_generation_delete_and_export(page, e2e_server):
    analysis_id = e2e_server.create_analysis("互換確認（詳細）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    c = e2e_server.add_child(a, "二次要因C")
    e2e_server.update_node(b, user_judgement="no")
    open_edit(page, analysis_id)
    expect_selected(page, a, "一次要因A")

    # Detail dialog from the inspector: the memo is saved, the judgement untouched.
    inspector(page).get_by_role("button", name="詳細を編集").click()
    expect(page.locator("#nodeDetailModal")).to_be_visible()
    expect(page.locator("#modalTitle")).to_have_value("一次要因A")
    page.fill("#modalMemo", "互換確認のメモ")
    page.locator("#modalSaveBtn").click()
    expect(page.locator('[data-details] [data-detail="memo"]')).to_have_text("互換確認のメモ")
    expect_selected(page, a, "一次要因A")
    node = e2e_server.get_node(a)
    assert node["memo"] == "互換確認のメモ" and node["user_judgement"] == "unknown"
    expect(item(page, "work", a)).to_contain_text("メモあり")

    # Manual add below A from the inspector: the new factor is selected.
    inspector(page).get_by_role("button", name="手動追加").click()
    expect(page.locator("#addNodeModal")).to_be_visible()
    page.fill("#addNodeTitle", "手動で追加した二次要因")
    page.locator("#addNodeModal").get_by_role("button", name="追加").click()
    expect(inspector_title(page)).to_have_text("手動で追加した二次要因")
    added = int(page.locator('#edit-nav [data-action="select"][aria-current="true"]').get_attribute("data-node-id"))
    assert e2e_server.get_node(added)["parent_id"] == a
    expect(item(page, "work", added)).to_contain_text("手動")

    # AI additional generation below the No parent B from its group heading (J-16).
    step_button(page, 3).click()
    page.locator(f'[data-group-parent="{b}"]').get_by_role("button", name="AIで追加生成").click()
    expect(page.locator(f'[data-group-parent="{b}"] [data-role="work-item"]')).to_have_count(2)
    call = e2e_server.stub_calls()[-1]
    assert (call["target_level"], call["parent_factor"], call["additional"]) == (2, "一次要因B", True)

    # Delete C from the inspector (the old confirmation): its parent is selected.
    select_button(page, "nav", c).click()
    dialogs = record_dialogs(page, action="accept")
    inspector(page).get_by_role("button", name="この要因を削除").click()
    expect(inspector_title(page)).to_have_text("一次要因A")
    assert dialogs == ["confirm"]
    wait_until(lambda: c not in e2e_server.node_ids(analysis_id))
    expect(select_button(page, "nav", c)).to_have_count(0)

    # Export: the header links and the provisional links of ⑤.
    with page.expect_download() as download_info:
        page.locator(".edit-header").get_by_role("link", name="JSON出力").click()
    assert download_info.value.suggested_filename == f"fta_{analysis_id}.json"
    exported = json.loads(open(download_info.value.path(), "rb").read())
    assert {n["title"] for n in exported["nodes"]} >= {"一次要因A", "手動で追加した二次要因"}
    step_button(page, 5).click()
    for name, suffix in (("JSON出力", "json"), ("CSV出力", "csv"), ("MD出力", "md")):
        with page.expect_download() as download_info:
            step_panel(page, 5).get_by_role("link", name=name).click()
        assert download_info.value.suggested_filename == f"fta_{analysis_id}.{suffix}"

    page.locator(".edit-header").get_by_role("link", name="一覧へ").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    expect(page.locator(f'tr[data-analysis-id="{analysis_id}"]')).to_have_attribute("data-factor-count", "5")

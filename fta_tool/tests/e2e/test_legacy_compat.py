"""E2E: the parts of the edit screen that still run on the old processing.

PR-3 builds the new edit screen but keeps app.js for the title and step ①
saving, generation, the detail dialog, manual add and delete (plan 7.2;
acceptance 10 of plan 8.3: UI-09〜UI-14 stay usable, and the normal
generation of 二次・三次 still includes Yes parents hidden by the filter).
PR3-LEGACY-OPS drives them from the new page; their results are shown by a
partial update, never by reloading the page (the page is marked and the mark
must still be there).

PR3-LEGACY-NOTIFY: app.js's messages (saving, generation, the dialogs,
delete, communication errors) appear in the shared notifications with the
same text and kind, once each, errors staying until closed (the user's
decision of 2026-09-29, 判断4; J-24 moved forward); the old #toast element
is gone. While a legacy dialog is open they never cover its buttons.

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
    toast,
    wait_until,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e


def mark_page(page) -> None:
    page.evaluate("() => { window.__pr3NoReload = 'kept'; }")


def same_page(page) -> bool:
    return page.evaluate("() => window.__pr3NoReload === 'kept'")


@pytest.mark.acceptance("PR3-LEGACY-OPS")
def test_title_step1_and_generation_from_the_new_page(page, e2e_server):
    analysis_id = e2e_server.create_analysis("互換確認（編集）", top_event="最初の頂上事象")
    open_edit(page, analysis_id)
    mark_page(page)
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
    assert same_page(page)


@pytest.mark.acceptance("PR3-LEGACY-OPS")
def test_detail_dialog_manual_add_additional_generation_delete_and_export(page, e2e_server):
    analysis_id = e2e_server.create_analysis("互換確認（詳細）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    c = e2e_server.add_child(a, "二次要因C")
    e2e_server.update_node(b, user_judgement="no")
    e2e_server.set_warning(b, "既存要因「一次要因A」に類似; 要因名が長すぎる")
    open_edit(page, analysis_id)
    mark_page(page)
    expect_selected(page, a, "一次要因A")

    # Detail dialog from the inspector: the memo is saved, the judgement untouched.
    inspector(page).get_by_role("button", name="詳細を編集").click()
    expect(page.locator("#nodeDetailModal")).to_be_visible()
    expect(page.locator("#modalTitle")).to_have_value("一次要因A")
    expect(page.locator("#modalTitle")).to_be_focused()  # app.js focuses it 50 ms after opening
    expect(page.locator("#modalWarningRow")).to_be_hidden()  # no quality warning, no empty 要確認 row
    page.fill("#modalMemo", "互換確認のメモ")
    page.locator("#modalSaveBtn").click()
    expect(page.locator('[data-details] [data-detail="memo"]')).to_have_text("互換確認のメモ")
    expect_selected(page, a, "一次要因A")
    node = e2e_server.get_node(a)
    assert node["memo"] == "互換確認のメモ" and node["user_judgement"] == "unknown"
    expect(item(page, "work", a)).to_contain_text("メモあり")

    # A factor with a quality warning keeps its 要確認 row with the full text.
    select_button(page, "nav", b).click()
    inspector(page).get_by_role("button", name="詳細を編集").click()
    expect(page.locator("#modalTitle")).to_have_value("一次要因B")
    expect(page.locator("#modalWarningRow")).to_be_visible()
    expect(page.locator("#modalWarningText")).to_have_text("既存要因「一次要因A」に類似; 要因名が長すぎる")
    page.locator("#nodeDetailModal").get_by_role("button", name="キャンセル").click()
    expect(page.locator("#nodeDetailModal")).to_be_hidden()
    select_button(page, "nav", a).click()
    expect(inspector_title(page)).to_have_text("一次要因A")

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

    assert same_page(page)
    page.locator(".edit-header").get_by_role("link", name="一覧へ").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    expect(page.locator(f'tr[data-analysis-id="{analysis_id}"]')).to_have_attribute("data-factor-count", "5")


# ----- PR3-LEGACY-NOTIFY -------------------------------------------------------

def expect_once(page, text: str, kind: str, *, exact: bool = True) -> None:
    """Shown once, in the shared stack, with this kind (and nowhere else)."""
    expect(toast(page, text, kind, exact=exact)).to_have_count(1)
    for other in ("success", "info", "warning", "error"):
        if other != kind:
            expect(toast(page, text, other, exact=exact)).to_have_count(0)


def boxes_overlap(a: dict, b: dict) -> bool:
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


def expect_dialog_uncovered(page, dialog_id: str) -> None:
    """While a legacy dialog is open the notifications cover no part of it:
    the whole stack stays clear of the dialog box, and every button of the
    dialog is what is drawn at its centre."""
    stack = page.locator("#ui-toasts").bounding_box()
    dialog = page.locator(f"#{dialog_id} .modal-content").bounding_box()
    assert stack["height"] > 0
    assert not boxes_overlap(stack, dialog), (stack, dialog)
    buttons = page.locator(f"#{dialog_id} button")
    assert buttons.count() >= 3  # ×, キャンセル and 保存 / 追加
    for index in range(buttons.count()):
        button = buttons.nth(index)
        button.scroll_into_view_if_needed()
        assert button.evaluate("""(el) => {
          const r = el.getBoundingClientRect();
          const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
          return el === hit || el.contains(hit);
        }"""), button.text_content()


def expect_normal_place(page) -> None:
    """Bottom centre, where the notifications are when no dialog is open."""
    box = page.locator("#ui-toasts").bounding_box()
    size = page.viewport_size
    assert abs(box["x"] + box["width"] / 2 - size["width"] / 2) <= 2, box
    assert 0 <= size["height"] - (box["y"] + box["height"]) <= 48, box


@pytest.mark.acceptance("PR3-LEGACY-NOTIFY")
def test_saving_dialogs_and_delete_messages_use_the_shared_notifications(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("通知の確認", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    open_edit(page, analysis_id)
    expect(page.locator("#toast")).to_have_count(0)  # the old element is gone
    expect(page.locator("#ui-toasts")).to_have_count(1)  # one place for every notification

    # Title: saved (success), empty (error, stays, announced).
    title = page.locator("#analysisTitle")
    title.click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.type("通知の確認（改名）")
    page.keyboard.press("Enter")
    expect_once(page, "タイトルを保存しました", "success")
    title.click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.press("Delete")
    page.keyboard.press("Enter")
    expect_once(page, "タイトルは必須です", "error")
    expect(page.locator("#ui-live-alert")).to_have_text("エラー：タイトルは必須です")
    expect(page.locator("#titleError")).to_have_text("タイトルは必須です")
    page.keyboard.type("通知の確認（改名）")
    page.keyboard.press("Enter")
    expect(page.locator("#titleError")).to_be_hidden()  # gone once the title is saved

    # Step ①.
    step_button(page, 1).click()
    page.fill("#topEventInput", "通知の頂上事象")
    step_panel(page, 1).get_by_role("button", name="保存", exact=True).click()
    expect_once(page, "頂上事象を保存しました", "success")
    page.fill("#incidentContextInput", "通知の確認の状況")
    page.get_by_role("button", name="コンテキストを保存").click()
    expect_once(page, "分析コンテキストを保存しました", "success")

    # Detail dialog: an empty title is refused while the dialog stays open;
    # the notifications (two errors now) cover no part of the dialog, and are
    # back in their usual place once it is closed.
    expect_normal_place(page)
    select_button(page, "nav", a).click()
    inspector(page).get_by_role("button", name="詳細を編集").click()
    expect(page.locator("#modalTitle")).to_be_focused()
    page.fill("#modalTitle", "")
    page.locator("#modalSaveBtn").click()
    expect_once(page, "要因タイトルは必須です", "error")
    expect_dialog_uncovered(page, "nodeDetailModal")
    page.fill("#modalTitle", "一次要因A（改名）")
    page.locator("#modalSaveBtn").click()
    expect_once(page, "保存しました", "success")
    expect(inspector_title(page)).to_have_text("一次要因A（改名）")
    expect(page.locator("#nodeDetailModal")).to_be_hidden()
    expect_normal_place(page)

    # A communication error (the request never reaches the server).
    page_watch.allow_console_error(r"ERR_FAILED")
    page.route(f"**/nodes/{a}/update", lambda route: route.abort())
    inspector(page).get_by_role("button", name="詳細を編集").click()
    expect(page.locator("#modalTitle")).to_be_focused()
    page.locator("#modalSaveBtn").click()
    expect_once(page, "通信エラーが発生しました", "error")
    expect_dialog_uncovered(page, "nodeDetailModal")
    page.locator("#nodeDetailModal").get_by_role("button", name="キャンセル").click()
    page.unroute(f"**/nodes/{a}/update")
    expect_normal_place(page)

    # Manual add: an empty title, then added.
    inspector(page).get_by_role("button", name="手動追加", exact=True).click()
    expect(page.locator("#addNodeTitle")).to_be_focused()
    page.locator("#addNodeModal").get_by_role("button", name="追加").click()
    expect_once(page, "タイトルを入力してください", "error")
    expect_dialog_uncovered(page, "addNodeModal")
    page.fill("#addNodeTitle", "手動の二次要因")
    page.locator("#addNodeModal").get_by_role("button", name="追加").click()
    expect_once(page, "要因を追加しました", "success")
    expect(inspector_title(page)).to_have_text("手動の二次要因")
    expect(page.locator("#addNodeModal")).to_be_hidden()
    expect_normal_place(page)

    # Delete.
    select_button(page, "nav", b).click()
    record_dialogs(page, action="accept")
    inspector(page).get_by_role("button", name="この要因を削除").click()
    expect_once(page, "削除しました", "success")

    # Errors stay until they are closed; the rest has closed by itself.
    page.wait_for_timeout(3500)
    for text in ("タイトルは必須です", "要因タイトルは必須です", "通信エラーが発生しました", "タイトルを入力してください"):
        expect(toast(page, text, "error", exact=True)).to_have_count(1)
    expect(page.locator('#ui-toasts .ui-toast[data-toast-type="success"]')).to_have_count(0)
    expect(page.locator("#toast")).to_have_count(0)
    expect(page.locator("#ui-toasts")).to_have_count(1)


@pytest.mark.acceptance("PR3-LEGACY-NOTIFY")
def test_generation_messages_keep_their_text_and_kind(page, e2e_server):
    analysis_id = e2e_server.create_analysis("通知の確認（生成）", top_event="頂上")
    open_edit(page, analysis_id)
    step_button(page, 2).click()

    step_panel(page, 2).get_by_role("button", name="一次要因を生成").click()
    expect_once(page, "4件の要因を生成しました", "success", exact=False)
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(4)

    e2e_server.set_stub_mode("no_candidates")
    step_panel(page, 2).get_by_role("button", name="一次要因を追加生成").click()
    expect_once(page, "生成候補がありませんでした（LLMが要因を返しませんでした）。", "warning")

    e2e_server.set_stub_mode("error")
    step_panel(page, 2).get_by_role("button", name="一次要因を追加生成").click()
    expect_once(page, "一部でエラーが発生しました", "error", exact=False)

    # 二次要因 without a Yes parent: refused before a request, as an error.
    step_button(page, 3).click()
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    expect_once(page, "Yes評価の要因がありません", "error")
    expect(page.locator("#toast")).to_have_count(0)

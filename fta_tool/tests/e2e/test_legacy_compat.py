"""E2E: the operations of the edit screen that ran on the old processing in
PR-3, as they are driven from the new page now.

PR-3 built the new edit screen but kept app.js for generation, the detail
dialog, manual add and delete (plan 7.2; acceptance 10 of plan 8.3: UI-09〜
UI-14 stay usable, and the normal generation of 二次・三次 still includes Yes
parents hidden by the filter). The title and step ① were rebuilt in PR-4;
the detail dialog, manual add and delete in PR-5 (the inspector's editor,
the manual-add and delete dialogs: E-E14〜E-E17 check them in full). Only
generation still runs on app.js until PR-6. PR3-LEGACY-OPS keeps checking
that every one of these operations works from the new page, what each one
guaranteed (the memo saved, the judgement untouched, the quality warning
with its full text, the added factor selected, the No parent's additional
generation, the parent selected after a delete, the exports) through the
controls that replaced the old ones, and that the results are shown by a
partial update, never by reloading the page (the page is marked and the
mark must still be there).

PR3-LEGACY-NOTIFY: the messages (saving, generation, the dialogs, delete,
communication errors) appear in the shared notifications with their kind,
once each, errors staying until closed (the user's decision of 2026-09-29,
判断4; J-24 moved forward); the old #toast element is gone. app.js's
generation messages keep their text. PR-5's messages of the factor's save,
manual add and delete are the new screen's own; a missing title is shown at
the field (the editor) or in the dialog (manual add), never as a
notification. The in-page dialogs (<dialog>, top layer) are never covered by
the notifications.

Until PR-3 the old screen had this check as PR1-COMPAT-EDIT; the
new-analysis form had PR1-COMPAT-NEW until PR-2 (now E-N01〜E-N06).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.e2e.edit_helpers import (
    add_dialog,
    add_factor,
    choose,
    chip,
    delete_dialog,
    delete_factor,
    factor_field,
    factor_message,
    factor_save,
    edit_title,
    expect_selected,
    inspector,
    inspector_title,
    item,
    judgement_button,
    open_edit,
    save_button,
    select_button,
    step_button,
    step_panel,
    title_input,
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

    # Title (rebuilt in PR-4: ✎ and Enter; the edit page names the tab).
    edit_title(page, "互換確認（改名）")
    expect(page).to_have_title("互換確認（改名） - FTA編集")
    expect(page.locator("#analysisTitle")).to_have_text("互換確認（改名）")
    wait_until(lambda: e2e_server.analysis(analysis_id)["title"] == "互換確認（改名）")

    # Step ① (rebuilt in PR-4) keeps its ids; the saved top event reaches the outlines.
    page.fill("#topEventInput", "編集後の頂上事象")
    save_button(page, "top-event").click()
    expect(page.locator("#topEventInput")).to_have_attribute("data-saved", "編集後の頂上事象")
    expect(step_button(page, 1)).to_contain_text("頂上事象：入力済み")
    expect(page.locator('#edit-nav [data-select="top"]')).to_contain_text("編集後の頂上事象")
    page.fill("#systemContextInput", "編集後のシステム構成")
    save_button(page, "context").click()
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
def test_details_manual_add_additional_generation_delete_and_export(page, e2e_server):
    """What the legacy detail dialog, manual add and delete guaranteed, through
    the controls of PR-5 that replaced them (and the legacy generation)."""
    analysis_id = e2e_server.create_analysis("互換確認（詳細）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    c = e2e_server.add_child(a, "二次要因C")
    e2e_server.update_node(b, user_judgement="no")
    e2e_server.set_warning(b, "既存要因「一次要因A」に類似; 要因名が長すぎる")
    open_edit(page, analysis_id)
    mark_page(page)
    expect_selected(page, a, "一次要因A")

    # The inspector's editor (was 詳細を編集): the memo is saved, the judgement untouched.
    expect(factor_field(page, "title")).to_have_value("一次要因A")
    expect(inspector(page).locator("[data-inspector-warning]")).to_have_count(0)  # no warning, no empty 要確認 part
    factor_field(page, "memo").fill("互換確認のメモ")
    factor_save(page).click()
    expect(toast(page, "要因を保存しました", "success", exact=True)).to_be_visible()
    expect_selected(page, a, "一次要因A")
    wait_until(lambda: e2e_server.get_node(a)["memo"] == "互換確認のメモ")
    assert e2e_server.get_node(a)["user_judgement"] == "unknown"
    expect(item(page, "work", a)).to_contain_text("メモあり")

    # A factor with a quality warning shows it in full in the inspector.
    choose(page, b)
    expect(factor_field(page, "title")).to_have_value("一次要因B")
    expect(inspector(page).locator("[data-warning-text]")).to_have_text("既存要因「一次要因A」に類似; 要因名が長すぎる")
    choose(page, a)

    # Manual add below A from the inspector (the dialog): the new factor is selected.
    add_factor(page, inspector(page).get_by_role("button", name="手動追加", exact=True), "手動で追加した二次要因")
    expect(inspector_title(page)).to_have_text("手動で追加した二次要因")
    added = int(page.locator('#edit-nav [data-action="select"][aria-current="true"]').get_attribute("data-node-id"))
    assert e2e_server.get_node(added)["parent_id"] == a
    expect(item(page, "work", added)).to_contain_text("手動")

    # AI additional generation below the No parent B from its group heading
    # (J-16; still the legacy generation of app.js until PR-6).
    step_button(page, 3).click()
    page.locator(f'[data-group-parent="{b}"]').get_by_role("button", name="AIで追加生成").click()
    expect(page.locator(f'[data-group-parent="{b}"] [data-role="work-item"]')).to_have_count(2)
    call = e2e_server.stub_calls()[-1]
    assert (call["target_level"], call["parent_factor"], call["additional"]) == (2, "一次要因B", True)

    # Delete C from the inspector (the in-page dialog, no confirm()): its parent is selected.
    select_button(page, "nav", c).click()
    dialogs = record_dialogs(page, action="accept")
    delete_factor(page)
    expect(inspector_title(page)).to_have_text("一次要因A")
    assert dialogs == []
    wait_until(lambda: c not in e2e_server.node_ids(analysis_id))
    expect(select_button(page, "nav", c)).to_have_count(0)

    # Export: the header's menu and the links of ⑤ (PR-4; E-E13 has the rest).
    page.locator(".edit-header [data-ui-menu-button]").click()
    with page.expect_download() as download_info:
        page.locator(".edit-header [data-ui-menu-panel]").get_by_role("link", name=re.compile("JSON")).click()
    assert download_info.value.suggested_filename == f"fta_{analysis_id}.json"
    exported = json.loads(open(download_info.value.path(), "rb").read())
    assert {n["title"] for n in exported["nodes"]} >= {"一次要因A", "手動で追加した二次要因"}
    step_button(page, 5).click()
    for fmt, suffix in (("json", "json"), ("csv", "csv"), ("markdown", "md")):
        with page.expect_download() as download_info:
            step_panel(page, 5).locator(f'a[data-export-format="{fmt}"]').click()
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


def expect_dialog_uncovered(page, dialog) -> None:
    """While an in-page dialog is open (PR-5: <dialog> in the top layer; the
    legacy dialogs needed the notifications moved aside) the notifications
    cover no part of it: every button of the dialog is what is drawn at its
    centre."""
    assert page.locator("#ui-toasts .ui-toast").count() > 0
    buttons = dialog.locator("button")
    assert buttons.count() >= 2
    for index in range(buttons.count()):
        button = buttons.nth(index)
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

    # Title (the new header of PR-4; E-E11 has the rest): saved (success),
    # empty (shown at the input and announced, nothing sent, stays open).
    edit_title(page, "通知の確認（改名）")
    expect_once(page, "タイトルを保存しました", "success")
    edit_title(page, "")
    expect(page.locator("[data-title-error]")).to_have_text("タイトルは必須です")
    expect(page.locator("#ui-live-alert")).to_have_text("タイトルは必須です")
    title_input(page).fill("通知の確認（改名2）")
    expect(page.locator("[data-title-error]")).to_be_hidden()  # gone once the input is valid
    title_input(page).press("Enter")
    expect_once(page, "タイトルを保存しました", "success")

    # Step ① (the new save of PR-4; E-E10 has the rest).
    step_button(page, 1).click()
    page.fill("#topEventInput", "通知の頂上事象")
    save_button(page, "top-event").click()
    expect_once(page, "頂上事象を保存しました", "success")
    page.fill("#incidentContextInput", "通知の確認の状況")
    save_button(page, "context").click()
    expect_once(page, "参考情報を保存しました", "success")

    # The inspector's editor (PR-5; was the detail dialog): an empty title
    # is refused at the field (announced, not a notification, nothing sent);
    # then saved (success).
    expect_normal_place(page)
    choose(page, a)
    factor_field(page, "title").fill("")
    factor_save(page).click()
    expect(factor_message(page)).to_have_text("保存できませんでした：要因タイトルは必須です")
    expect(page.locator("#ui-live-alert")).to_have_text("要因タイトルは必須です")
    expect(toast(page, "要因タイトルは必須です", "error")).to_have_count(0)
    factor_field(page, "title").fill("一次要因A（改名）")
    factor_save(page).click()
    expect_once(page, "要因を保存しました", "success")
    expect(inspector_title(page)).to_have_text("一次要因A（改名）")
    expect_normal_place(page)

    # A communication error (the request never reaches the server).
    page_watch.allow_console_error(r"ERR_FAILED")
    page.route(f"**/nodes/{a}/update", lambda route: route.abort())
    factor_field(page, "memo").fill("通信エラーのメモ")
    factor_save(page).click()
    expect_once(page, "要因を保存できませんでした：サーバーに接続できませんでした（通信エラー）", "error")
    page.unroute(f"**/nodes/{a}/update")
    factor_field(page, "memo").fill("")  # back to the saved value
    expect_normal_place(page)

    # Manual add: an empty title (in the dialog), then added. The errors
    # stacked meanwhile never cover the dialog.
    inspector(page).get_by_role("button", name="手動追加", exact=True).click()
    expect(page.locator("#add-factor-title")).to_be_focused()
    add_dialog(page).get_by_role("button", name="追加する").click()
    expect(add_dialog(page).locator(".ui-dialog__error")).to_have_text("要因タイトルを入力してください")
    expect(toast(page, "要因タイトルを入力してください", "error")).to_have_count(0)
    expect_dialog_uncovered(page, add_dialog(page))
    page.fill("#add-factor-title", "手動の二次要因")
    add_dialog(page).get_by_role("button", name="追加する").click()
    expect_once(page, "要因を追加しました", "success")
    expect(inspector_title(page)).to_have_text("手動の二次要因")
    expect(add_dialog(page)).to_have_count(0)
    expect_normal_place(page)

    # Delete.
    choose(page, b)
    inspector(page).get_by_role("button", name="この要因を削除").click()
    expect_dialog_uncovered(page, delete_dialog(page))
    delete_dialog(page).get_by_role("button", name="削除する").click()
    expect_once(page, "要因「一次要因B」を削除しました", "success")

    # Errors stay until they are closed; the rest has closed by itself.
    page.wait_for_timeout(3500)
    for text in ("要因を保存できませんでした：サーバーに接続できませんでした（通信エラー）",):
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

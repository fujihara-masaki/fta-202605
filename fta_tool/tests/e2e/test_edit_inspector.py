"""E2E: the inspector's editor, the delete dialog and the manual-add dialog
(PR-5) — plan 5.1, 5.2, 8.5, J-10・J-11・J-13; E-E14, E-E16, E-E17.

Everything is driven through the real inspector and dialogs of the page
(not through registered stand-ins: that is E-E20's contract test). What is
sent is recorded from the browser, what is saved is read from the test
server's database, and what is shown is read from every representation.

* E-E14  the seven fields (タイトル・説明・メモ・直接要因評価・評価コメント・
         根拠・再発防止策) are saved by one POST /nodes/{id}/update that never
         carries the judgement; afterwards the title, description, 「メモあり」
         and 「直接要因評価：…」 are the same on every representation (nav,
         work list, group heading, tree, table, breadcrumb, inspector), the
         filter finds the new text, ⑤ counts the new value. 入力中（未保存）／
         保存済み compares after the normalisation used for saving (CRLF and
         spaces stored in the DB are not unsaved; typing and restoring is
         saved again; 取消 goes back). Input typed while the save is in
         flight stays unsaved; 保存・取消 refuse meanwhile. An empty title is
         refused at the field (nothing sent); a failed save keeps the input
         and its reason; a save that succeeded but whose display update
         failed is told apart and never sent again. While the details load
         or after they failed to load nothing can be typed or saved; 再読み込み.
* E-E16  the delete dialog: the factor's name, its descendants from the
         server's walk (not from the rows shown: a filter hiding them does not
         change it) and the total, that the numbers are those of when the
         screen was shown; キャンセル / Esc / a failure keep the draft;
         「編集中の変更も破棄されます」 when the edited factor or an ancestor is
         deleted, and then only that draft is dropped; the parent (or the top
         event) is selected; deleting another factor keeps the draft; asked
         again on confirming (the data changed meanwhile: nothing is sent).
* E-E17  the manual-add dialog: the place (top event / the parent) fixed
         when it opens; a duplicate is refused in the dialog with the input
         kept; Enter adds, the Enter of an IME conversion does not; the added
         factor is selected through R-01 — with a draft, the three choices;
         編集を続ける keeps the selection and the draft, the factor stays
         added and the add is never sent again; a later choice of the user is
         never replaced by the selection.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import pytest

from tests.e2e.edit_helpers import (
    LEAVE_DIALOG,
    add_dialog,
    add_factor,
    chip,
    choose,
    delete_dialog,
    editor,
    expect_editor_ready,
    expect_selected,
    factor_cancel,
    factor_field,
    factor_message,
    factor_save,
    factor_status,
    fill_factor,
    inspector,
    inspector_title,
    item,
    leave_dialog,
    leave_link,
    open_edit,
    select_button,
    step_button,
    step_panel,
    tab,
    toast,
    wait_until,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e

SEVEN = {
    "title": "一次要因A（改名）",
    "description": "改めた説明",
    "memo": "改めたメモ",
    "direct_cause_status": "direct",
    "direct_cause_comment": "評価のコメント",
    "evidence": "根拠の文",
    "prevention_idea": "再発防止策の文",
}


def node_posts(page) -> list[tuple[str, dict]]:
    """(path, JSON body) of every POST to /nodes/… the page sends from now on."""
    sent: list[tuple[str, dict]] = []

    def record(request):
        path = urlparse(request.url).path
        if request.method == "POST" and path.startswith("/nodes/"):
            sent.append((path, request.post_data_json or {}))

    page.on("request", record)
    return sent


def detail_gets(page, node_id: int) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda r: seen.append(r.url)
            if r.method == "GET" and urlparse(r.url).path == f"/nodes/{node_id}" else None)
    return seen


def is_page_fetch(request, analysis_id: int) -> bool:
    return (request.method == "GET" and request.resource_type == "fetch"
            and urlparse(request.url).path == f"/analyses/{analysis_id}")


def mark_page(page) -> None:
    page.evaluate("() => { window.__pr5NoReload = 'kept'; }")


def same_page(page) -> bool:
    return page.evaluate("() => window.__pr5NoReload === 'kept'")


def inject_delete(page, node_id: int) -> None:
    """A delete control of another factor than the one in the inspector, as a
    stale button or another route would be (the inspector offers 削除 only for
    the factor it shows): the page's own dialog and checks take it."""
    page.evaluate("""(id) => {
      const button = document.createElement('button');
      button.type = 'button'; button.dataset.action = 'delete'; button.dataset.nodeId = String(id);
      button.id = 'e2e-delete-other'; button.textContent = '別の要因を削除';
      document.querySelector('[data-edit-page]').append(button);
    }""", node_id)
    page.locator("#e2e-delete-other").click()


def selected(page) -> str:
    return page.evaluate("() => new URLSearchParams(location.hash.slice(1)).get('sel')")


# ----- E-E14 ---------------------------------------------------------------------

@pytest.mark.acceptance("E-E14")
def test_E_E14_seven_fields_one_request_without_the_judgement_shown_everywhere(page, e2e_server):
    analysis_id = e2e_server.create_analysis("インスペクタの保存", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A", "元の説明")
    b = e2e_server.add_child(a, "二次要因B")
    e2e_server.update_node(a, user_judgement="yes")
    open_edit(page, analysis_id, f"#sel={a}&step=2&view=work")
    expect_editor_ready(page, a)
    mark_page(page)
    sent = node_posts(page)

    expect(factor_status(page)).to_have_text("保存済み")
    fill_factor(page, **SEVEN)
    expect(factor_status(page)).to_have_text("入力中（未保存）")
    factor_save(page).click()
    expect(toast(page, "要因を保存しました", "success", exact=True)).to_be_visible()
    expect(factor_status(page)).to_have_text("保存済み")

    # One request with the seven fields, never the judgement.
    assert len(sent) == 1
    path, body = sent[0]
    assert path == f"/nodes/{a}/update"
    assert body == SEVEN and "user_judgement" not in body
    stored = e2e_server.get_node(a)
    assert {key: stored[key] for key in SEVEN} == SEVEN
    assert stored["user_judgement"] == "yes"
    assert e2e_server.get_node(b)["memo"] == ""

    # Every representation shows the new values (no reload).
    expect(inspector_title(page)).to_have_text("一次要因A（改名）")
    for role in ("nav", "work", "tree", "table"):
        expect(select_button(page, role, a)).to_contain_text("一次要因A（改名）")
    expect(item(page, "work", a).locator(".edit-row__desc")).to_have_text("改めた説明")
    for scope in (item(page, "work", a), page.locator(".edit-inspector__tags")):
        expect(scope).to_contain_text("直接要因評価：直接要因")
        expect(scope).to_contain_text("メモあり")
    expect(page.locator(f'[data-role="table-item"][data-node-id="{a}"]')).to_contain_text("改めた説明")
    expect(chip(page.locator("#edit-nav"), a)).to_have_text("Yes")  # the judgement stays
    step_button(page, 3).click()
    expect(page.locator(f'[data-group-parent="{a}"] [data-role="group"]')).to_have_text("一次要因A（改名）")
    choose(page, b)
    expect(inspector(page).locator(".edit-crumbs li").nth(1)).to_have_text("一次要因A（改名）")
    # The filter finds the new text; ⑤ counts the new 直接要因.
    page.fill("#edit-filter-text", "改めた説明")
    expect(page.locator("#edit-filter-count")).to_have_text("一致 1件（全2件）")
    page.fill("#edit-filter-text", "元の説明")
    expect(page.locator("#edit-filter-count")).to_have_text("一致 0件（全2件）")
    page.fill("#edit-filter-text", "")
    step_button(page, 5).click()
    expect(page.locator('[data-summary-row="1"] [data-summary-cell="direct"]')).to_have_text("1")
    expect(page.locator('[data-summary-row="all"] [data-summary-cell="direct"]')).to_have_text("1")
    assert same_page(page)
    assert len(sent) == 1


@pytest.mark.acceptance("E-E14")
def test_E_E14_saved_status_compares_after_normalisation_and_cancel_restores(page, e2e_server):
    analysis_id = e2e_server.create_analysis("保存状態の表示", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    e2e_server.update_node(a, memo="  行1\r\n行2  ", evidence="根拠\r\n")  # stored as is (CRLF, spaces)
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    sent = node_posts(page)
    dialogs = record_dialogs(page)

    expect(factor_status(page)).to_have_attribute("data-state", "saved")  # not unsaved when it opens
    expect(factor_cancel(page)).to_be_disabled()
    factor_field(page, "memo").fill("行1\n行2 （変更）")
    expect(factor_status(page)).to_have_attribute("data-state", "dirty")
    expect(factor_cancel(page)).to_be_enabled()
    factor_field(page, "memo").fill("行1\n行2")  # back to the saved value (after normalisation)
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    factor_save(page).click()
    expect(toast(page, "この要因に保存していない変更はありません", "info")).to_be_visible()

    # 取消 goes back to the saved values; nothing sent, no question when leaving.
    factor_field(page, "title").fill("取り消すタイトル")
    factor_field(page, "direct_cause_status").select_option("likely")
    factor_cancel(page).click()
    expect(factor_field(page, "title")).to_have_value("一次要因A")
    expect(factor_field(page, "direct_cause_status")).to_have_value("unknown")
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    leave_link(page).click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert sent == [] and dialogs == []


@pytest.mark.acceptance("E-E14")
def test_E_E14_input_typed_during_the_save_stays_unsaved(page, e2e_server):
    analysis_id = e2e_server.create_analysis("保存中の入力", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    sent = node_posts(page)
    held = []
    page.route(f"**/nodes/{a}/update", lambda route: held.append(route))

    factor_field(page, "memo").fill("先に送るメモ")
    factor_save(page).click()
    wait_until(lambda: len(held) == 1)
    expect(factor_status(page)).to_have_text("保存中…")
    expect(factor_save(page)).to_have_attribute("aria-disabled", "true")
    factor_field(page, "memo").fill("先に送るメモ（追加）")  # typing is allowed meanwhile
    # aria-disabled: Playwright would wait for "enabled"; the click is forced
    # as a user's would be, and refused by the page.
    factor_save(page).click(force=True)    # refused while the save is in flight
    factor_cancel(page).click(force=True)  # likewise
    page.wait_for_timeout(300)
    assert len(sent) == 1
    expect(factor_field(page, "memo")).to_have_value("先に送るメモ（追加）")

    held[0].continue_()
    expect(toast(page, "要因を保存しました", "success", exact=True)).to_be_visible()
    wait_until(lambda: e2e_server.get_node(a)["memo"] == "先に送るメモ")
    # What was typed after sending is not taken as saved.
    expect(factor_status(page)).to_have_attribute("data-state", "dirty")
    page.unroute(f"**/nodes/{a}/update")
    factor_save(page).click()
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    wait_until(lambda: e2e_server.get_node(a)["memo"] == "先に送るメモ（追加）")
    assert [body["memo"] for _, body in sent] == ["先に送るメモ", "先に送るメモ（追加）"]


@pytest.mark.acceptance("E-E14")
def test_E_E14_empty_title_failure_and_a_failed_display_update_are_told_apart(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("保存の失敗", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    page_watch.allow_console_error(r"status of 500")
    sent = node_posts(page)
    mark_page(page)

    # An empty title: refused at the field, nothing sent.
    factor_field(page, "title").fill("   ")
    factor_save(page).click()
    expect(factor_message(page)).to_have_text("保存できませんでした：要因タイトルは必須です")
    expect(factor_field(page, "title")).to_have_attribute("aria-invalid", "true")
    expect(factor_field(page, "title")).to_be_focused()
    page.wait_for_timeout(300)
    assert sent == []

    # The server refuses: the input and the reason stay.
    route = f"**/nodes/{a}/update"
    page.route(route, lambda r: r.fulfill(status=500, json={"detail": "E2E: 要因の保存に失敗させました"}))
    factor_field(page, "title").fill("保存できないタイトル")
    factor_save(page).click()
    expect(toast(page, "要因を保存できませんでした：E2E: 要因の保存に失敗させました", "error")).to_be_visible()
    expect(factor_message(page)).to_have_text("保存できませんでした：E2E: 要因の保存に失敗させました")
    expect(factor_status(page)).to_have_attribute("data-state", "dirty")
    expect(factor_field(page, "title")).to_have_value("保存できないタイトル")
    page.wait_for_timeout(300)
    assert len(sent) == 1  # never sent again by itself
    page.unroute(route)

    # Saved, but the display update after it fails (something typed in ①,
    # so the page is not reloaded): both are told, the save is not sent again.
    page.route(f"**/analyses/{analysis_id}",
               lambda r: r.fulfill(status=500, json={"detail": "E2E: 表示の更新に失敗"})
               if is_page_fetch(r.request, analysis_id) else r.continue_())
    step_button(page, 1).click()
    page.fill("#topEventInput", "入力中の頂上事象")
    step_button(page, 2).click()
    factor_save(page).click()
    expect(toast(page, "要因を保存しました", "success", exact=True)).to_be_visible()
    expect(toast(page, "最新の表示に更新できませんでした（E2E: 表示の更新に失敗）", "error")).to_be_visible()
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    expect(inspector_title(page)).to_have_text("保存できないタイトル")  # the inspector follows the save at once
    page.wait_for_timeout(500)
    assert len(sent) == 2
    assert e2e_server.get_node(a)["title"] == "保存できないタイトル"
    assert same_page(page)


@pytest.mark.acceptance("E-E14")
def test_E_E14_nothing_can_be_typed_or_saved_before_the_details_arrived(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("詳細の読込み", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    e2e_server.update_node(a, memo="保存済みのメモ")
    page_watch.allow_console_error(r"status of 500")
    fail = {"on": True}
    page.route(f"**/nodes/{a}", lambda r: r.fulfill(status=500, json={"detail": "E2E: 詳細の取得に失敗"})
               if fail["on"] and r.request.method == "GET" else r.continue_())
    open_edit(page, analysis_id)
    sent = node_posts(page)
    dialogs = record_dialogs(page)

    expect(editor(page)).to_have_attribute("data-phase", "failed")
    expect(inspector(page).locator("[data-detail-status]")).to_contain_text("E2E: 詳細の取得に失敗")
    for key in ("title", "memo", "direct_cause_status"):
        expect(factor_field(page, key)).to_be_disabled()
        expect(factor_field(page, key)).to_have_value("" if key != "direct_cause_status" else "unknown")
    expect(factor_save(page)).to_be_disabled()
    # Nothing to protect yet: leaving asks nothing and sends nothing.
    fail["on"] = False
    inspector(page).locator("[data-factor-reload]").click()
    expect_editor_ready(page, a)
    expect(factor_field(page, "memo")).to_have_value("保存済みのメモ")
    assert sent == [] and dialogs == []


# ----- E-E16 ----------------------------------------------------------------------

def tree_abc(server, title="削除の確認"):
    """一次 A → 二次 B → 三次 C, 二次 B2; 一次 D."""
    analysis_id = server.create_analysis(title, top_event="頂上")
    a = server.add_level1(analysis_id, "一次要因A")
    b = server.add_child(a, "二次要因B")
    c = server.add_child(b, "三次要因C")
    b2 = server.add_child(a, "二次要因B2")
    d = server.add_level1(analysis_id, "一次要因D")
    return analysis_id, a, b, c, b2, d


@pytest.mark.acceptance("E-E16")
def test_E_E16_counts_from_the_server_cancel_escape_and_failure_keep_the_draft(page, e2e_server, page_watch):
    analysis_id, a, b, c, b2, d = tree_abc(e2e_server)
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    page_watch.allow_console_error(r"status of 500")
    sent = node_posts(page)
    dialogs = record_dialogs(page)
    before = e2e_server.node_ids()

    # The filter hides the descendants; the count is the server's walk.
    page.fill("#edit-filter-text", "一次要因A")
    expect(item(page, "work", a)).to_be_visible()
    expect(inspector(page).locator("[data-delete-reason]")).to_have_text(
        "子孫の要因 3件もすべて削除されます（画面を表示した時点の件数）。この操作は取り消せません。")
    factor_field(page, "memo").fill("削除の確認の下書き")
    delete = inspector(page).get_by_role("button", name="この要因を削除")
    delete.click()
    dialog = delete_dialog(page)
    expect(dialog.locator("[data-delete-title]")).to_have_text("一次要因A")
    expect(dialog).to_contain_text("（一次要因）を削除します。")
    expect(dialog.locator("[data-delete-count]")).to_have_text("この要因の子孫 3件も一緒に削除されます（合計 4件）。")
    expect(dialog.locator("[data-delete-when]")).to_contain_text("件数は画面を表示した時点の情報です。")
    expect(dialog.locator("[data-delete-draft]")).to_have_text("編集中の変更も破棄されます。")
    expect(dialog.get_by_role("button", name="キャンセル")).to_be_focused()

    dialog.get_by_role("button", name="キャンセル").click()
    expect(dialog).to_have_count(0)
    expect(delete).to_be_focused()
    delete.click()
    page.keyboard.press("Escape")
    expect(delete_dialog(page)).to_have_count(0)
    expect(factor_field(page, "memo")).to_have_value("削除の確認の下書き")

    # A failed delete: the reason in the dialog, nothing removed, the draft stays.
    page.route(f"**/nodes/{a}/delete", lambda r: r.fulfill(status=500, json={"detail": "E2E: 削除に失敗させました"}))
    delete.click()
    delete_dialog(page).get_by_role("button", name="削除する").click()
    expect(delete_dialog(page).locator(".ui-dialog__error")).to_have_text("削除できませんでした：E2E: 削除に失敗させました")
    delete_dialog(page).get_by_role("button", name="キャンセル").click()
    expect(factor_field(page, "memo")).to_have_value("削除の確認の下書き")
    expect(factor_status(page)).to_have_attribute("data-state", "dirty")
    assert e2e_server.node_ids() == before
    assert [path for path, _ in sent] == [f"/nodes/{a}/delete"]
    assert dialogs == []


@pytest.mark.acceptance("E-E16")
def test_E_E16_deleting_the_edited_factors_ancestor_drops_that_draft_and_selects_the_parent(page, e2e_server):
    analysis_id, a, b, c, b2, d = tree_abc(e2e_server, "編集中の要因の祖先の削除")
    open_edit(page, analysis_id, f"#sel={c}&step=4&view=work")
    expect_editor_ready(page, c)
    sent = node_posts(page)
    step_button(page, 1).click()
    page.fill("#topEventInput", "①の下書き")  # not affected by a delete

    # The edited factor is C (a draft); its ancestor B is deleted from a
    # control of B: the dialog says the draft goes too.
    step_button(page, 4).click()
    factor_field(page, "memo").fill("Cの下書き")
    inject_delete(page, b)
    dialog = delete_dialog(page)
    expect(dialog.locator("[data-delete-title]")).to_have_text("二次要因B")
    expect(dialog.locator("[data-delete-count]")).to_have_text("この要因の子孫 1件も一緒に削除されます（合計 2件）。")
    expect(dialog.locator("[data-delete-draft]")).to_have_text("編集中の変更も破棄されます。")
    dialog.get_by_role("button", name="削除する").click()
    expect(toast(page, "要因「二次要因B」を削除しました", "success", exact=True)).to_be_visible()

    # The parent is selected; the dropped draft asks nothing any more; ① stays.
    expect_selected(page, a, "一次要因A")
    expect_editor_ready(page, a)
    expect(step_button(page, 2)).to_have_attribute("aria-current", "step")
    assert e2e_server.node_ids(analysis_id) == {a, b2, d}
    assert e2e_server.get_node(a)["memo"] == ""
    leave_link(page).click()
    expect(leave_dialog(page)).to_be_visible()  # ① only
    expect(leave_dialog(page).locator("ul").first.locator("li")).to_have_text(["頂上事象"])
    leave_dialog(page).get_by_role("button", name="編集を続ける").click()
    expect(page.locator("#topEventInput")).to_have_value("①の下書き")
    assert [path for path, _ in sent] == [f"/nodes/{b}/delete"]


@pytest.mark.acceptance("E-E16")
def test_E_E16_deleting_another_factor_keeps_the_draft(page, e2e_server):
    analysis_id, a, b, c, b2, d = tree_abc(e2e_server, "別の要因の削除")
    open_edit(page, analysis_id)
    choose(page, a)
    factor_field(page, "memo").fill("Aの下書き")
    sent = node_posts(page)
    dialogs = record_dialogs(page)

    # A control of another factor (D): the dialog names D and does not
    # speak of the draft.
    inject_delete(page, d)
    dialog = delete_dialog(page)
    expect(dialog.locator("[data-delete-title]")).to_have_text("一次要因D")
    expect(dialog.locator("[data-delete-count]")).to_have_text("この要因に子孫の要因はありません（この要因だけを削除します。合計 1件）。")
    expect(dialog.locator("[data-delete-draft]")).to_have_count(0)
    dialog.get_by_role("button", name="削除する").click()
    expect(select_button(page, "nav", d)).to_have_count(0)

    # The draft, the selection and the editor stay.
    expect_selected(page, a, "一次要因A")
    expect(factor_field(page, "memo")).to_have_value("Aの下書き")
    expect(factor_status(page)).to_have_attribute("data-state", "dirty")
    assert [path for path, _ in sent] == [f"/nodes/{d}/delete"]
    assert dialogs == []
    factor_save(page).click()
    wait_until(lambda: e2e_server.get_node(a)["memo"] == "Aの下書き")


@pytest.mark.acceptance("E-E16")
def test_E_E16_confirming_asks_again_and_a_top_level_delete_selects_the_top_event(page, e2e_server):
    other = e2e_server.create_analysis("別の分析", top_event="別")
    analysis_id, a, b, c, b2, d = tree_abc(e2e_server, "確定時の確認")
    open_edit(page, analysis_id)
    choose(page, d)
    sent = node_posts(page)

    # The dialog was opened; meanwhile a factor of another analysis was put
    # below D and the page was updated: 削除する is refused, nothing is sent.
    inspector(page).get_by_role("button", name="この要因を削除").click()
    e2e_server.insert_node(other, 2, d, title="Dの下の別分析の要因")
    page.evaluate("() => window.ftaEditBridge.refresh({})")
    expect(inspector(page).locator("[data-delete-reason]")).to_contain_text("別の分析の要因が含まれる")
    delete_dialog(page).get_by_role("button", name="削除する").click()
    expect(delete_dialog(page).locator(".ui-dialog__error")).to_contain_text(
        "この要因の子孫に別の分析の要因が含まれるため、この画面では削除できません")
    page.wait_for_timeout(300)
    assert sent == []
    delete_dialog(page).get_by_role("button", name="キャンセル").click()

    # A 一次要因 without that: the top event is selected afterwards.
    choose(page, a)
    inspector(page).get_by_role("button", name="この要因を削除").click()
    delete_dialog(page).get_by_role("button", name="削除する").click()
    expect(inspector_title(page)).to_have_text("頂上事象")
    expect(step_button(page, 1)).to_have_attribute("aria-current", "step")
    assert re.search(r"sel=top", page.url)
    assert [path for path, _ in sent] == [f"/nodes/{a}/delete"]


# ----- E-E17 ----------------------------------------------------------------------

@pytest.mark.acceptance("E-E17")
def test_E_E17_place_shown_and_fixed_duplicate_refused_in_the_dialog(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("手動追加の確認", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    e2e_server.add_child(a, "既にある二次要因")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    page_watch.allow_console_error(r"status of 409")
    sent = node_posts(page)
    adds: list[str] = []
    page.on("request", lambda r: adds.append(urlparse(r.url).path)
            if r.method == "POST" and re.search(r"/children$|/add-level1$", urlparse(r.url).path) else None)

    # Every place names where the factor goes.
    step_panel(page, 2).get_by_role("button", name="手動追加", exact=True).click()
    expect(add_dialog(page).locator("[data-add-place]")).to_have_text("追加先：頂上事象の下の一次要因")
    add_dialog(page).get_by_role("button", name="キャンセル").click()
    step_button(page, 3).click()
    page.locator(f'[data-group-parent="{b}"]').get_by_role("button", name="手動追加（親：一次要因B）").click()
    expect(add_dialog(page).locator("[data-add-place]")).to_have_text("追加先：「一次要因B」の下の二次要因")
    page.keyboard.press("Escape")
    expect(add_dialog(page)).to_have_count(0)

    # From the inspector of A: the place is fixed when the dialog opens.
    inspector(page).get_by_role("button", name="手動追加", exact=True).click()
    dialog = add_dialog(page)
    expect(dialog.locator("[data-add-place]")).to_have_text("追加先：「一次要因A」の下の二次要因")
    expect(page.locator("#add-factor-title")).to_be_focused()
    page.fill("#add-factor-title", "既にある二次要因")
    page.fill("#add-factor-description", "重複の説明")
    page.locator("#add-factor-title").press("Enter")
    expect(dialog.locator(".ui-dialog__error")).to_have_text("追加できませんでした：同名の要因が既に存在します")
    expect(page.locator("#add-factor-title")).to_have_value("既にある二次要因")
    expect(page.locator("#add-factor-description")).to_have_value("重複の説明")
    expect(page.locator("#add-factor-title")).to_be_focused()
    # The Enter of an IME conversion does not add.
    page.fill("#add-factor-title", "変換中の名前")
    page.locator("#add-factor-title").dispatch_event("keydown", {"key": "Enter", "isComposing": True})
    page.wait_for_timeout(300)
    assert adds == [f"/nodes/{a}/children"]
    page.fill("#add-factor-title", "手動で追加した二次要因")
    dialog.get_by_role("button", name="追加する").click()
    expect(dialog).to_have_count(0)
    expect(inspector_title(page)).to_have_text("手動で追加した二次要因")
    assert adds == [f"/nodes/{a}/children", f"/nodes/{a}/children"]
    added = int(selected(page))
    node = e2e_server.get_node(added)
    assert (node["parent_id"], node["level"], node["ai_generated"], node["user_judgement"]) == (a, 2, False, "unknown")
    assert node["description"] == "重複の説明"
    assert sent == [(f"/nodes/{a}/children", {"title": "既にある二次要因", "description": "重複の説明"}),
                    (f"/nodes/{a}/children", {"title": "手動で追加した二次要因", "description": "重複の説明"})]


@pytest.mark.acceptance("E-E17")
def test_E_E17_auto_selection_asks_about_the_draft_and_never_sends_the_add_again(page, e2e_server):
    analysis_id = e2e_server.create_analysis("追加後の自動選択", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    adds: list[str] = []
    page.on("request", lambda r: adds.append(urlparse(r.url).path)
            if r.method == "POST" and re.search(r"/children$|/add-level1$", urlparse(r.url).path) else None)
    sent = node_posts(page)
    factor_field(page, "memo").fill("追加の前の下書き")

    # Added; selecting it asks about A's draft. 編集を続ける: A stays with
    # its draft, the new factor stays added, nothing is sent again.
    add_button = step_panel(page, 2).get_by_role("button", name="手動追加", exact=True)
    add_factor(page, add_button, "自動選択の確認X")
    expect(toast(page, "要因を追加しました", "success", exact=True)).to_be_visible()
    dialog = leave_dialog(page)
    expect(dialog).to_be_visible()
    expect(dialog.locator("ul").first.locator("li")).to_have_text(["要因「一次要因A」の内容"])
    dialog.get_by_role("button", name="編集を続ける").click()
    expect(dialog).to_have_count(0)
    x = e2e_server.query("SELECT id FROM nodes WHERE analysis_id = ? AND title = ?", (analysis_id, "自動選択の確認X"))[0][0]
    expect(select_button(page, "nav", x)).to_have_count(1)
    expect_selected(page, a, "一次要因A")
    expect(factor_field(page, "memo")).to_have_value("追加の前の下書き")
    assert selected(page) == str(a)
    page.wait_for_timeout(300)
    assert adds == [f"/analyses/{analysis_id}/nodes/add-level1"]

    # The next add, 保存して移動: A is saved, then the new factor is selected.
    add_factor(page, add_button, "自動選択の確認Y")
    leave_dialog(page).get_by_role("button", name="保存して移動").click()
    y = e2e_server.query("SELECT id FROM nodes WHERE analysis_id = ? AND title = ?", (analysis_id, "自動選択の確認Y"))[0][0]
    expect_selected(page, y, "自動選択の確認Y")
    expect_editor_ready(page, y)
    assert e2e_server.get_node(a)["memo"] == "追加の前の下書き"
    assert e2e_server.node_count(analysis_id) == 3
    assert adds == [f"/analyses/{analysis_id}/nodes/add-level1"] * 2
    assert [path for path, _ in sent if path.endswith("/update")] == [f"/nodes/{a}/update"]


@pytest.mark.acceptance("E-E17")
def test_E_E17_a_later_choice_is_never_replaced_by_the_selection(page, e2e_server):
    analysis_id = e2e_server.create_analysis("追加後の遅い更新", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    held = []
    page.route(f"**/analyses/{analysis_id}",
               lambda r: held.append(r) if is_page_fetch(r.request, analysis_id) and not held else r.continue_())

    add_factor(page, step_panel(page, 2).get_by_role("button", name="手動追加", exact=True), "遅れて表示される要因")
    wait_until(lambda: bool(held))
    choose(page, b)  # chosen before the update arrives
    held[0].continue_()
    added = e2e_server.query("SELECT id FROM nodes WHERE title = ?", ("遅れて表示される要因",))[0][0]
    expect(select_button(page, "nav", added)).to_have_count(1)
    page.wait_for_timeout(500)
    expect_selected(page, b, "一次要因B")
    expect_editor_ready(page, b)

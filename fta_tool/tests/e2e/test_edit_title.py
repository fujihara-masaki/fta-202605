"""E2E: the analysis title in the edit screen's header (PR-4, E-E11; plan
5.1, 5.7, 8.4-3, UI-07).

- ✎ opens an input; Enter saves, Esc and 取消 cancel, leaving the input saves.
  Moving the focus to the editor's own 保存・取消 does not save, and the blur
  and the click that caused it never send the title twice.
- The Enter / Esc of an IME conversion (isComposing, keyCode 229; composition
  events dispatched by the test — the real Microsoft IME is checked by hand)
  neither saves nor cancels.
- Required and 255 characters, counted like the list and the new-analysis
  form (code points after trimming).
- Leaving with only the title changed: no dialog, the save (also one started
  by the focus leaving the input, answered late) is awaited, then the page
  moves. Empty, too long or a failed save: the page stays with the input and
  the reason, and a failed title is not sent again unchanged. With ① changed
  as well, the title is saved first, then the three choices are asked for ①.
- A partial update that fails while the title is being edited keeps the
  input; when the analysis is gone, the title can no longer be edited or
  saved (refresh.js no longer looks for the old contenteditable title).
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.edit_helpers import (
    edit_title,
    leave_dialog,
    leave_link,
    open_edit,
    open_title_editor,
    post_paths,
    step_button,
    title_editor,
    title_input,
    toast,
    wait_until,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = [pytest.mark.e2e, pytest.mark.acceptance("E-E11")]


def title_posts(page, analysis_id):
    sent = post_paths(page)
    return lambda: [path for path in sent if path == f"/analyses/{analysis_id}/title"]


def heading(page):
    return page.locator("#analysisTitle")


def test_E_E11_enter_saves_escape_and_cancel_restore(page, e2e_server):
    analysis_id = e2e_server.create_analysis("元のタイトル")
    open_edit(page, analysis_id)
    sent = title_posts(page, analysis_id)

    field = open_title_editor(page)
    expect(field).to_have_value("元のタイトル")
    expect(page.locator("[data-title-count]")).to_have_text("6")
    field.fill("Escで取り消す")
    field.press("Escape")
    expect(title_editor(page)).to_be_hidden()
    expect(heading(page)).to_have_text("元のタイトル")
    expect(page.locator("[data-title-edit]")).to_be_focused()

    field = open_title_editor(page)
    expect(field).to_have_value("元のタイトル")  # the cancelled input is gone
    field.fill("取消で取り消す")
    title_editor(page).get_by_role("button", name="取消").click()
    expect(heading(page)).to_have_text("元のタイトル")
    assert sent() == []

    edit_title(page, "  Enterで保存したタイトル  ")
    expect(heading(page)).to_have_text("Enterで保存したタイトル")
    expect(page).to_have_title("Enterで保存したタイトル - FTA編集")
    expect(page.locator("[data-title-edit]")).to_have_attribute("aria-label", "分析タイトルを変更：Enterで保存したタイトル")
    expect(page.locator("[data-title-edit]")).to_be_focused()
    expect(toast(page, "タイトルを保存しました", "success", exact=True)).to_have_count(1)
    assert len(sent()) == 1
    assert e2e_server.analysis(analysis_id)["title"] == "Enterで保存したタイトル"

    edit_title(page, "保存ボタンで保存", key=None)
    title_editor(page).get_by_role("button", name="保存").click()
    expect(heading(page)).to_have_text("保存ボタンで保存")
    assert len(sent()) == 2  # the click on 保存 did not also save on blur

    # Unchanged + Enter: closes without a request.
    open_title_editor(page).press("Enter")
    expect(title_editor(page)).to_be_hidden()
    assert len(sent()) == 2


def test_E_E11_ime_enter_and_escape_do_nothing(page, e2e_server):
    analysis_id = e2e_server.create_analysis("変換前のタイトル")
    open_edit(page, analysis_id)
    sent = title_posts(page, analysis_id)
    field = open_title_editor(page)
    field.fill("へんかんちゅう")
    field.dispatch_event("compositionstart", {"data": ""})
    field.dispatch_event("keydown", {"key": "Enter", "code": "Enter", "isComposing": True})
    field.dispatch_event("keydown", {"key": "Escape", "code": "Escape", "isComposing": True})
    field.evaluate(
        """(input) => {
             const event = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true });
             Object.defineProperty(event, 'keyCode', { get: () => 229 });
             input.dispatchEvent(event);
           }"""
    )
    field.dispatch_event("compositionend", {"data": "変換中"})
    page.wait_for_timeout(300)
    expect(title_editor(page)).to_be_visible()
    expect(field).to_have_value("へんかんちゅう")
    assert sent() == []
    field.press("Enter")  # the Enter after the conversion saves
    expect(heading(page)).to_have_text("へんかんちゅう")
    assert len(sent()) == 1


def test_E_E11_focus_on_save_or_cancel_does_not_save_leaving_the_input_does(page, e2e_server):
    analysis_id = e2e_server.create_analysis("フォーカスの確認")
    open_edit(page, analysis_id)
    sent = title_posts(page, analysis_id)
    field = edit_title(page, "フォーカスで保存しない", key=None)
    field.press("Tab")
    expect(title_editor(page).get_by_role("button", name="保存")).to_be_focused()
    page.keyboard.press("Tab")
    expect(title_editor(page).get_by_role("button", name="取消")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Shift+Tab")
    expect(field).to_be_focused()
    page.wait_for_timeout(300)
    assert sent() == []
    title_editor(page).get_by_role("button", name="取消").click()  # focus moves to 取消, then it cancels
    expect(heading(page)).to_have_text("フォーカスの確認")
    page.wait_for_timeout(300)
    assert sent() == []

    # Leaving the input elsewhere saves (once).
    edit_title(page, "フォーカスが外れて保存", key=None)
    step_button(page, 1).click()
    expect(heading(page)).to_have_text("フォーカスが外れて保存")
    expect(title_editor(page)).to_be_hidden()
    wait_until(lambda: e2e_server.analysis(analysis_id)["title"] == "フォーカスが外れて保存")
    assert len(sent()) == 1

    # Unchanged and left: closes, nothing sent.
    open_title_editor(page)
    step_button(page, 2).click()
    expect(title_editor(page)).to_be_hidden()
    page.wait_for_timeout(300)
    assert len(sent()) == 1


@pytest.mark.parametrize("value, reason", [
    ("   ", "タイトルは必須です"),
    ("あ" * 256, "タイトルは255文字以内で入力してください"),
])
def test_E_E11_empty_or_too_long_is_not_sent_and_stops_leaving(page, e2e_server, value, reason):
    analysis_id = e2e_server.create_analysis("検査のタイトル")
    open_edit(page, analysis_id)
    sent = title_posts(page, analysis_id)
    field = edit_title(page, value)
    expect(page.locator("[data-title-error]")).to_have_text(reason)
    expect(field).to_have_attribute("aria-invalid", "true")
    expect(field).to_be_focused()

    dialogs = record_dialogs(page)
    leave_link(page).click()  # the input loses the focus, then the link is clicked
    expect(toast(page, f"分析タイトルを保存できなかったため、移動していません：{reason}", "error", exact=True)).to_be_visible()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{analysis_id}")
    expect(field).to_have_value(value)
    expect(field).to_be_focused()
    expect(page.locator("[data-title-error]")).to_have_text(reason)
    expect(leave_dialog(page)).to_have_count(0)
    assert sent() == [] and dialogs == []
    assert e2e_server.analysis(analysis_id)["title"] == "検査のタイトル"


def test_E_E11_255_characters_counted_as_code_points_are_accepted(page, e2e_server):
    analysis_id = e2e_server.create_analysis("文字数の確認")
    open_edit(page, analysis_id)
    value = "𠮷" * 255  # 255 characters, 510 UTF-16 code units
    field = edit_title(page, value, key=None)
    expect(page.locator("[data-title-count]")).to_have_text("255")
    field.press("Enter")
    expect(heading(page)).to_have_text(value)
    assert e2e_server.analysis(analysis_id)["title"] == value


def test_E_E11_leaving_waits_for_the_save_the_blur_started(page, e2e_server):
    analysis_id = e2e_server.create_analysis("移動の前に保存")
    open_edit(page, analysis_id)
    sent = title_posts(page, analysis_id)
    held = []
    page.route(f"**/analyses/{analysis_id}/title", lambda route: held.append(route))
    dialogs = record_dialogs(page)

    edit_title(page, "遅れて保存されるタイトル", key=None)
    leave_link(page).click()  # blur starts the save; the click waits for it
    wait_until(lambda: len(held) == 1)
    waiting = page.get_by_role("dialog", name="保存の完了を待っています")
    expect(waiting).to_be_visible()
    page.wait_for_timeout(500)
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{analysis_id}")
    assert len(sent()) == 1
    held[0].continue_()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert dialogs == []  # no browser confirmation either
    assert e2e_server.analysis(analysis_id)["title"] == "遅れて保存されるタイトル"
    assert len(sent()) == 1  # one save for the blur and the click


def test_E_E11_a_failed_save_stays_and_is_not_sent_again_unchanged(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("保存に失敗するタイトル")
    open_edit(page, analysis_id)
    page_watch.allow_console_error(r"status of 500")
    sent = title_posts(page, analysis_id)
    route = f"**/analyses/{analysis_id}/title"
    page.route(route, lambda r: r.fulfill(status=500, json={"detail": "E2E: タイトルの保存に失敗させました"}))

    field = edit_title(page, "失敗するタイトル", key=None)
    leave_link(page).click()
    expect(toast(page, "分析タイトルを保存できなかったため、移動していません：E2E: タイトルの保存に失敗させました",
                 "error", exact=True)).to_be_visible()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{analysis_id}")
    expect(field).to_have_value("失敗するタイトル")
    expect(page.locator("[data-title-error]")).to_have_text("E2E: タイトルの保存に失敗させました")
    assert len(sent()) == 1

    leave_link(page).click()  # the same input again: not sent again
    page.wait_for_timeout(500)
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{analysis_id}")
    assert len(sent()) == 1

    page.unroute(route)
    field.fill("直したタイトル")
    leave_link(page).click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert len(sent()) == 2
    assert e2e_server.analysis(analysis_id)["title"] == "直したタイトル"


def test_E_E11_title_and_step_1_both_changed(page, e2e_server):
    analysis_id = e2e_server.create_analysis("タイトルと①", top_event="元の頂上事象")
    open_edit(page, analysis_id)
    held = []
    page.route(f"**/analyses/{analysis_id}/title", lambda route: held.append(route))
    page.fill("#topEventInput", "変更した頂上事象")
    edit_title(page, "変更したタイトル", key=None)

    page.locator(".app-header").get_by_role("link", name="分析一覧").click()
    wait_until(lambda: len(held) == 1)
    expect(leave_dialog(page)).to_have_count(0)  # the title's save comes first
    held[0].continue_()
    dialog = leave_dialog(page)
    expect(dialog).to_be_visible()
    expect(dialog.locator("ul").first).to_have_text("頂上事象")  # ① only; the title is saved
    expect(heading(page)).to_have_text("変更したタイトル")
    dialog.get_by_role("button", name="編集を続ける").click()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{analysis_id}")
    expect(page.locator("#topEventInput")).to_have_value("変更した頂上事象")
    assert e2e_server.analysis(analysis_id)["title"] == "変更したタイトル"
    assert e2e_server.analysis(analysis_id)["top_event"] == "元の頂上事象"


def test_E_E11_failed_partial_update_keeps_the_title_input_and_gone_stops_it(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("部分更新とタイトル", top_event="頂上")
    e2e_server.add_level1(analysis_id, "一次要因A")
    open_edit(page, analysis_id)
    page.evaluate("() => { window.__pr4NoReload = 'kept'; }")
    page_watch.allow_console_error(r"status of (500|404)")

    def fail(route):
        if route.request.method == "GET" and route.request.resource_type == "fetch":
            route.fulfill(status=500, json={"detail": "E2E：部分更新の取得に失敗（検証用）"})
        else:
            route.continue_()

    page.route(f"**/analyses/{analysis_id}", fail)
    field = edit_title(page, "入力中のタイトル", key=None)
    page.evaluate("() => window.ftaEditBridge.refresh({})")
    expect(toast(page, "最新の表示に更新できませんでした（E2E：部分更新の取得に失敗（検証用））。"
                       "入力中の内容を保存してから、ページを再読み込みしてください。", "error")).to_be_visible()
    assert page.evaluate("() => window.__pr4NoReload === 'kept'")
    expect(field).to_have_value("入力中のタイトル")
    expect(field).to_be_focused()

    # The analysis is gone: the title can no longer be edited or saved.
    page.unroute(f"**/analyses/{analysis_id}")
    sent = title_posts(page, analysis_id)
    e2e_server.delete_analysis(analysis_id)
    page.evaluate("() => window.ftaEditBridge.refresh({})")
    expect(page.locator(".edit-gone")).to_be_visible()
    expect(field).to_have_value("入力中のタイトル")
    expect(field).to_have_js_property("readOnly", True)
    expect(title_editor(page).get_by_role("button", name="保存")).to_be_disabled()
    field.press("Enter")
    page.wait_for_timeout(300)
    assert sent() == []
    title_editor(page).get_by_role("button", name="取消").click()
    expect(page.locator("[data-title-edit]")).to_be_disabled()
    assert json.dumps(page.evaluate("() => window.__pr4NoReload")) == '"kept"'

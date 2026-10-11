"""E2E: analysis list (A) — plan 8.1, E-L01〜E-L08.

Runs against the real app (stub AI provider, temporary database) in
Chromium at 1280x800 and 1440x900. IME input is simulated with synthetic key
events (isComposing / keyCode 229); a real IME is a manual check.
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e

GUARD_DIALOG = "保存していない変更があります"


# ----- helpers --------------------------------------------------------------

def row(page, analysis_id):
    return page.locator(f'tr[data-analysis-id="{analysis_id}"]')


def title_link(page, analysis_id):
    return row(page, analysis_id).locator("[data-title-link]")


def rename_button(page, analysis_id):
    return row(page, analysis_id).locator('[data-action="rename"]')


def rename_input(page, analysis_id):
    return row(page, analysis_id).locator("[data-rename-editor] input")


def rename_error(page, analysis_id):
    return row(page, analysis_id).locator(".rename-editor__error")


def delete_button(page, analysis_id):
    return row(page, analysis_id).locator('[data-action="delete"]')


def export_button(page, analysis_id):
    return row(page, analysis_id).locator("[data-ui-menu-button]")


def export_panel(page, analysis_id):
    return page.locator(f"#export-menu-{analysis_id}")


def guard_dialog(page):
    return page.get_by_role("dialog", name=GUARD_DIALOG)


def open_list(page):
    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")


def start_rename(page, analysis_id, text=None):
    rename_button(page, analysis_id).click()
    field = rename_input(page, analysis_id)
    expect(field).to_be_focused()
    if text is not None:
        field.fill(text)
    return field


def title_requests(page, analysis_id):
    sent = []
    page.on("request", lambda r: sent.append(r) if r.method == "POST" and r.url.endswith(f"/analyses/{analysis_id}/title") else None)
    return sent


# ----- E-L01 ----------------------------------------------------------------

@pytest.mark.acceptance("E-L01")
def test_E_L01_order_and_open_analysis(page, e2e_server):
    a = e2e_server.create_analysis("分析A", top_event="Aの頂上事象")
    b = e2e_server.create_analysis("分析B", top_event="Bの頂上事象")
    c = e2e_server.create_analysis("分析C")
    e2e_server.rename(a, "分析A（更新）")  # A becomes the most recently updated

    open_list(page)
    titles = page.locator("tr[data-analysis-id] [data-title-link]")
    expect(titles).to_have_text(["分析A（更新）", "分析C", "分析B"])
    expect(page.locator(".list-page__meta")).to_have_text("3件・更新日時の新しい順")
    expect(page.get_by_role("navigation", name="メインメニュー").get_by_role("link", name="分析一覧")).to_have_attribute("aria-current", "page")
    for analysis_id in (a, b, c):
        expect(title_link(page, analysis_id)).to_have_attribute("href", f"/analyses/{analysis_id}")
        expect(row(page, analysis_id).locator("[data-edit-link]")).to_have_attribute("href", f"/analyses/{analysis_id}")
    expect(row(page, c).locator(".list-table__top-event")).to_have_text("（未設定）")

    title_link(page, c).click()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{c}")
    expect(page.locator("#analysisTitle")).to_have_text("分析C")

    page.go_back()
    expect(page).to_have_url(f"{e2e_server.url}/")
    row(page, b).locator("[data-edit-link]").click()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{b}")
    expect(page.locator("#analysisTitle")).to_have_text("分析B")


# ----- E-L02 ----------------------------------------------------------------

@pytest.mark.acceptance("E-L02")
def test_E_L02_rename_enter_escape_cancel(page, e2e_server):
    analysis_id = e2e_server.create_analysis("旧タイトル")
    before = e2e_server.analysis(analysis_id)["updated_at"]
    open_list(page)

    field = start_rename(page, analysis_id)
    expect(field).to_have_value("旧タイトル")
    expect(row(page, analysis_id).locator("[data-rename-count]")).to_have_text("5")
    field.fill("  新しいタイトル  ")
    field.press("Enter")
    expect(row(page, analysis_id).locator("[data-rename-editor]")).to_have_count(0)
    expect(title_link(page, analysis_id)).to_have_text("新しいタイトル")
    expect(rename_button(page, analysis_id)).to_be_focused()
    expect(page.locator(".ui-toast--success")).to_contain_text("タイトルを保存しました")
    saved = e2e_server.analysis(analysis_id)
    assert saved["title"] == "新しいタイトル"  # trimmed like the server
    assert saved["updated_at"] > before
    expect(row(page, analysis_id)).to_have_attribute("data-title", "新しいタイトル")
    expect(rename_button(page, analysis_id)).to_have_attribute("aria-label", "タイトルを変更：新しいタイトル")

    # Esc restores without saving
    field = start_rename(page, analysis_id, "取り消す値")
    field.press("Escape")
    expect(row(page, analysis_id).locator("[data-rename-editor]")).to_have_count(0)
    expect(title_link(page, analysis_id)).to_have_text("新しいタイトル")
    expect(rename_button(page, analysis_id)).to_be_focused()

    # 取消 restores without saving
    start_rename(page, analysis_id, "取り消す値2")
    row(page, analysis_id).get_by_role("button", name="取消").click()
    expect(row(page, analysis_id).locator("[data-rename-editor]")).to_have_count(0)
    expect(title_link(page, analysis_id)).to_have_text("新しいタイトル")
    assert e2e_server.analysis(analysis_id)["title"] == "新しいタイトル"


@pytest.mark.acceptance("E-L02")
def test_E_L02_ime_conversion_enter_and_escape_do_not_save(page, e2e_server):
    analysis_id = e2e_server.create_analysis("変換前")
    open_list(page)
    sent = title_requests(page, analysis_id)
    field = start_rename(page, analysis_id, "へんかんちゅう")

    # Enter / Esc that confirm or cancel an IME conversion (isComposing)
    field.dispatch_event("keydown", {"key": "Enter", "code": "Enter", "isComposing": True})
    field.dispatch_event("keydown", {"key": "Escape", "code": "Escape", "isComposing": True})
    # Safari delivers the confirming Enter with keyCode 229
    field.evaluate(
        """(input) => {
             const event = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true });
             Object.defineProperty(event, 'keyCode', { get: () => 229 });
             input.dispatchEvent(event);
           }"""
    )
    page.wait_for_timeout(300)
    expect(field).to_be_visible()
    expect(field).to_have_value("へんかんちゅう")
    assert sent == []
    assert e2e_server.analysis(analysis_id)["title"] == "変換前"

    # A normal Enter after the conversion saves.
    field.fill("変換後のタイトル")
    field.press("Enter")
    expect(title_link(page, analysis_id)).to_have_text("変換後のタイトル")
    assert len(sent) == 1
    assert e2e_server.analysis(analysis_id)["title"] == "変換後のタイトル"


# ----- E-L03 ----------------------------------------------------------------

@pytest.mark.acceptance("E-L03")
def test_E_L03_validation_empty_and_too_long(page, e2e_server):
    analysis_id = e2e_server.create_analysis("検査用")
    open_list(page)
    sent = title_requests(page, analysis_id)

    field = start_rename(page, analysis_id, "   ")
    field.press("Enter")
    expect(rename_error(page, analysis_id)).to_have_text("タイトルは必須です")
    expect(field).to_have_attribute("aria-invalid", "true")
    expect(field).to_be_focused()

    field.fill("あ" * 256)
    expect(row(page, analysis_id).locator("[data-rename-count]")).to_have_text("256")
    expect(row(page, analysis_id).locator(".rename-editor__help")).to_have_attribute("data-over-limit", "true")
    row(page, analysis_id).get_by_role("button", name="保存").click()
    expect(rename_error(page, analysis_id)).to_have_text("タイトルは255文字以内で入力してください")
    page.wait_for_timeout(200)
    assert sent == []
    assert e2e_server.analysis(analysis_id)["title"] == "検査用"

    # 255 characters outside the BMP are 255 characters for the server too.
    long_title = "𠮷" * 255
    field.fill(long_title)
    expect(rename_error(page, analysis_id)).to_be_hidden()
    field.press("Enter")
    expect(title_link(page, analysis_id)).to_have_text(long_title)
    assert e2e_server.analysis(analysis_id)["title"] == long_title


@pytest.mark.acceptance("E-L03")
def test_E_L03_server_reason_is_shown_as_is(page, page_watch, e2e_server):
    analysis_id = e2e_server.create_analysis("理由表示")
    open_list(page)
    page_watch.allow_console_error(r"status of (400|404)")
    page_watch.allow_console_error(r"ERR_FAILED")

    route = f"**/analyses/{analysis_id}/title"
    page.route(route, lambda r: r.fulfill(status=400, json={"detail": "E2E: サーバーが返した理由"}))
    field = start_rename(page, analysis_id, "新しい名前")
    field.press("Enter")
    expect(rename_error(page, analysis_id)).to_have_text("E2E: サーバーが返した理由")
    expect(page.locator(".ui-toast--error")).to_contain_text("タイトルを保存できませんでした：E2E: サーバーが返した理由")
    expect(page.locator("#ui-live-alert")).to_contain_text("E2E: サーバーが返した理由")
    expect(field).to_be_visible()
    page.unroute(route)

    page.route(route, lambda r: r.abort())
    field.press("Enter")
    expect(rename_error(page, analysis_id)).to_have_text("サーバーに接続できませんでした（通信エラー）")
    page.unroute(route)

    # The analysis was deleted elsewhere: the server's 404 reason is shown.
    e2e_server.delete_analysis(analysis_id)
    field.press("Enter")
    expect(rename_error(page, analysis_id)).to_have_text("分析が見つかりません")
    expect(page.locator("body")).not_to_contain_text("保存に失敗しました")


# ----- E-L04 ----------------------------------------------------------------

@pytest.mark.acceptance("E-L04")
def test_E_L04_browser_tab_title_is_unchanged(page, e2e_server):
    analysis_id = e2e_server.create_analysis("タブ名確認")
    open_list(page)
    expect(page).to_have_title("FTA分析一覧")
    field = start_rename(page, analysis_id, "改名後のタイトル")
    field.press("Enter")
    expect(title_link(page, analysis_id)).to_have_text("改名後のタイトル")
    expect(page).to_have_title("FTA分析一覧")


# ----- E-L05 ----------------------------------------------------------------

@pytest.mark.acceptance("E-L05")
def test_E_L05_no_change_means_no_confirmation(page, e2e_server):
    a = e2e_server.create_analysis("変更なしの分析")
    b = e2e_server.create_analysis("移動先の分析")
    open_list(page)
    dialogs = record_dialogs(page)

    # Opened but unchanged; whitespace/CRLF-only differences are not changes.
    field = start_rename(page, a, "  変更なしの分析 ")
    assert field.is_visible()
    title_link(page, b).click()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{b}")
    assert dialogs == []


@pytest.mark.acceptance("E-L05")
def test_E_L05_continue_editing_and_escape_keep_the_draft(page, e2e_server):
    a = e2e_server.create_analysis("編集中の分析")
    b = e2e_server.create_analysis("別の分析")
    open_list(page)
    field = start_rename(page, a, "編集中の新しい名前")

    title_link(page, b).click()
    dialog = guard_dialog(page)
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("分析「編集中の分析」のタイトル（変更後：「編集中の新しい名前」）")
    expect(dialog.get_by_role("button", name="編集を続ける")).to_be_focused()
    dialog.get_by_role("button", name="編集を続ける").click()
    expect(dialog).to_have_count(0)
    expect(page).to_have_url(f"{e2e_server.url}/")
    expect(field).to_have_value("編集中の新しい名前")
    expect(title_link(page, b)).to_be_focused()  # back to the element that was operated

    header_new = page.get_by_role("navigation", name="メインメニュー").get_by_role("link", name="新規作成")
    header_new.click()
    expect(guard_dialog(page)).to_be_visible()
    page.keyboard.press("Escape")
    expect(guard_dialog(page)).to_have_count(0)
    expect(page).to_have_url(f"{e2e_server.url}/")
    expect(header_new).to_be_focused()
    expect(field).to_have_value("編集中の新しい名前")
    assert e2e_server.analysis(a)["title"] == "編集中の分析"


@pytest.mark.acceptance("E-L05")
def test_E_L05_save_and_go(page, e2e_server):
    a = e2e_server.create_analysis("保存して移動する分析")
    b = e2e_server.create_analysis("移動先")
    open_list(page)
    start_rename(page, a, "保存して移動した名前")
    row(page, b).locator("[data-edit-link]").click()
    guard_dialog(page).get_by_role("button", name="保存して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{b}")
    assert e2e_server.analysis(a)["title"] == "保存して移動した名前"


@pytest.mark.acceptance("E-L05")
def test_E_L05_discard_and_go(page, e2e_server):
    a = e2e_server.create_analysis("破棄する分析")
    open_list(page)
    start_rename(page, a, "破棄される名前")
    page.locator(".list-page__header").get_by_role("link", name="＋ 新規分析を作成").click()
    guard_dialog(page).get_by_role("button", name="破棄して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/new")
    assert e2e_server.analysis(a)["title"] == "破棄する分析"


@pytest.mark.acceptance("E-L05")
def test_E_L05_save_and_go_failure_stays_on_page(page, page_watch, e2e_server):
    a = e2e_server.create_analysis("保存に失敗する分析")
    b = e2e_server.create_analysis("移動しない先")
    open_list(page)
    page_watch.allow_console_error(r"status of 500")
    sent = title_requests(page, a)

    # Invalid input: nothing is sent and the page stays.
    start_rename(page, a, "")
    title_link(page, b).click()
    dialog = guard_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog).to_contain_text("入力に不備があるため保存していません（何も送信していません）。")
    expect(dialog).to_contain_text("タイトルは必須です")
    assert sent == []
    dialog.get_by_role("button", name="編集を続ける").click()

    # Server failure: the page stays, the reason is shown, 再試行 works.
    route = f"**/analyses/{a}/title"
    page.route(route, lambda r: r.fulfill(status=500, json={"detail": "E2E: 保存に失敗させました"}))
    rename_input(page, a).fill("失敗後に再試行する名前")
    title_link(page, b).click()
    dialog = guard_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog).to_contain_text("保存できなかった変更があるため、移動していません。")
    expect(dialog).to_contain_text("E2E: 保存に失敗させました")
    expect(dialog.get_by_role("button", name="再試行")).to_be_visible()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert e2e_server.analysis(a)["title"] == "保存に失敗する分析"

    page.unroute(route)
    dialog.get_by_role("button", name="再試行").click()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{b}")
    assert e2e_server.analysis(a)["title"] == "失敗後に再試行する名前"


@pytest.mark.acceptance("E-L05")
def test_E_L05_leaving_waits_for_a_save_in_flight(page, e2e_server):
    a = e2e_server.create_analysis("送信中の保存")
    b = e2e_server.create_analysis("待ってから移動する先")
    open_list(page)
    held = []
    page.route(f"**/analyses/{a}/title", lambda route: held.append(route))  # hold the request

    field = start_rename(page, a, "送信中の名前")
    field.press("Enter")
    expect(row(page, a).locator("[data-rename-editor]")).to_have_attribute("aria-busy", "true")
    field.press("Escape")  # ignored while the save is in flight
    expect(field).to_be_visible()

    title_link(page, b).click()
    waiting = page.get_by_role("dialog", name="保存の完了を待っています")
    expect(waiting).to_be_visible()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert len(held) == 1
    held[0].continue_()  # the save finishes, then the page moves on
    expect(page).to_have_url(f"{e2e_server.url}/analyses/{b}")
    assert e2e_server.analysis(a)["title"] == "送信中の名前"


@pytest.mark.acceptance("E-L05")
def test_E_L05_rename_of_another_row(page, e2e_server):
    a = e2e_server.create_analysis("行A")
    b = e2e_server.create_analysis("行B")
    open_list(page)

    # Unchanged: switching rows needs no confirmation.
    start_rename(page, a)
    rename_button(page, b).click()
    expect(rename_input(page, b)).to_be_focused()
    expect(rename_input(page, a)).to_have_count(0)

    # Changed: the same three choices.
    rename_input(page, b).fill("行Bの変更")
    rename_button(page, a).click()
    dialog = guard_dialog(page)
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="編集を続ける").click()
    expect(rename_input(page, b)).to_have_value("行Bの変更")
    expect(rename_input(page, a)).to_have_count(0)
    expect(rename_button(page, a)).to_be_focused()

    rename_button(page, a).click()
    guard_dialog(page).get_by_role("button", name="破棄して移動").click()
    expect(rename_input(page, a)).to_be_focused()
    expect(rename_input(page, b)).to_have_count(0)
    expect(title_link(page, b)).to_have_text("行B")

    rename_input(page, a).fill("行Aの保存")
    rename_button(page, b).click()
    guard_dialog(page).get_by_role("button", name="保存して移動").click()
    expect(rename_input(page, b)).to_be_focused()
    expect(title_link(page, a)).to_have_text("行Aの保存")
    assert e2e_server.analysis(a)["title"] == "行Aの保存"
    assert e2e_server.analysis(b)["title"] == "行B"


@pytest.mark.acceptance("E-L05")
def test_E_L05_browser_leave_confirmation_only_when_changed(page, e2e_server):
    analysis_id = e2e_server.create_analysis("離脱確認")
    open_list(page)
    dialogs = record_dialogs(page, action="accept")

    page.reload()
    start_rename(page, analysis_id)  # opened, unchanged
    page.reload()
    assert dialogs == []

    start_rename(page, analysis_id, "未保存の変更")
    page.reload()
    assert dialogs == ["beforeunload"]
    expect(page.locator("[data-rename-editor]")).to_have_count(0)  # reloaded after accepting

    # Closing the tab asks as well.
    start_rename(page, analysis_id, "閉じる前の変更")
    with page.expect_event("close"):
        page.close(run_before_unload=True)
    assert dialogs == ["beforeunload", "beforeunload"]


# ----- E-L06 ----------------------------------------------------------------

@pytest.mark.acceptance("E-L06")
def test_E_L06_delete_dialog_cancel_escape_failure_and_confirm(page, page_watch, e2e_server):
    a = e2e_server.create_analysis("削除する分析", top_event="頂上")
    first = e2e_server.add_level1(a, "一次要因1")
    e2e_server.add_level1(a, "一次要因2")
    e2e_server.add_child(first, "二次要因1")
    b = e2e_server.create_analysis("残る分析")
    open_list(page)
    page_watch.allow_console_error(r"status of 500")

    delete_button(page, a).click()
    dialog = page.get_by_role("dialog", name="分析を削除しますか？")
    expect(dialog).to_contain_text("分析「削除する分析」を削除します。")
    expect(dialog).to_contain_text("この分析の要因 3件（一覧を表示した時点の件数）")
    expect(dialog).to_contain_text("この操作は取り消せません。")
    expect(dialog.get_by_role("button", name="キャンセル")).to_be_focused()
    dialog.get_by_role("button", name="キャンセル").click()
    expect(dialog).to_have_count(0)
    expect(delete_button(page, a)).to_be_focused()

    delete_button(page, a).click()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(delete_button(page, a)).to_be_focused()
    assert e2e_server.analysis(a) is not None and e2e_server.node_count(a) == 3

    route = f"**/analyses/{a}/delete"
    page.route(route, lambda r: r.fulfill(status=500, json={"detail": "E2E: 削除に失敗させました"}))
    delete_button(page, a).click()
    dialog = page.get_by_role("dialog", name="分析を削除しますか？")
    dialog.get_by_role("button", name="削除する").click()
    expect(dialog).to_contain_text("削除できませんでした：E2E: 削除に失敗させました")
    expect(row(page, a)).to_have_count(1)
    assert e2e_server.analysis(a) is not None
    page.unroute(route)

    dialog.get_by_role("button", name="削除する").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(row(page, a)).to_have_count(0)
    expect(page.locator("[data-analysis-count]")).to_have_text("1")
    expect(page.locator(".ui-toast--success")).to_contain_text("分析「削除する分析」を削除しました")
    expect(title_link(page, b)).to_be_focused()
    assert e2e_server.analysis(a) is None
    assert e2e_server.node_count(a) == 0

    # The last one: the empty state appears.
    delete_button(page, b).click()
    dialog = page.get_by_role("dialog", name="分析を削除しますか？")
    expect(dialog).to_contain_text("この分析に要因はありません")
    dialog.get_by_role("button", name="削除する").click()
    expect(page.locator("[data-empty-state]")).to_be_visible()
    expect(page.locator("[data-list-table]")).to_be_hidden()
    expect(page.locator("#list-empty-title")).to_be_focused()
    expect(page.locator("[data-analysis-count]")).to_have_text("0")


@pytest.mark.acceptance("E-L06")
def test_E_L06_count_is_the_value_when_the_list_was_shown(page, e2e_server):
    analysis_id = e2e_server.create_analysis("件数の時点")
    e2e_server.add_level1(analysis_id, "表示前の要因")
    open_list(page)
    e2e_server.add_level1(analysis_id, "表示後に追加した要因")
    delete_button(page, analysis_id).click()
    dialog = page.get_by_role("dialog", name="分析を削除しますか？")
    expect(dialog).to_contain_text("この分析の要因 1件（一覧を表示した時点の件数）")
    dialog.get_by_role("button", name="削除する").click()
    expect(row(page, analysis_id)).to_have_count(0)
    assert e2e_server.node_count(analysis_id) == 0  # all factors are deleted


# ----- E-L07 ----------------------------------------------------------------

@pytest.mark.acceptance("E-L07")
def test_E_L07_export_menu_keyboard_and_links(page, e2e_server):
    analysis_id = e2e_server.create_analysis("出力の分析", top_event="頂上事象")
    e2e_server.add_level1(analysis_id, "出力される要因")
    other = e2e_server.create_analysis("別の出力")
    open_list(page)

    button = export_button(page, analysis_id)
    panel = export_panel(page, analysis_id)
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(panel).to_be_hidden()

    button.focus()
    page.keyboard.press("Enter")
    expect(panel).to_be_visible()
    expect(button).to_have_attribute("aria-expanded", "true")
    links = panel.locator("a")
    expect(links).to_have_count(3)
    for index, fmt in enumerate(("json", "csv", "markdown")):
        expect(links.nth(index)).to_have_attribute("href", f"/analyses/{analysis_id}/export/{fmt}")
        expect(links.nth(index)).to_have_attribute("download", "")
    expect(links.nth(1)).to_contain_text("分析タイトル・頂上事象・参考情報は含みません")

    page.keyboard.press("Tab")
    expect(links.nth(0)).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(links.nth(1)).to_be_focused()
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    expect(button).to_be_focused()
    expect(button).to_have_attribute("aria-expanded", "false")

    page.keyboard.press("ArrowDown")  # opens and moves to the first item
    expect(links.nth(0)).to_be_focused()
    page.keyboard.press("Escape")

    # Only one menu at a time; a click outside closes it.
    button.click()
    export_button(page, other).click()
    expect(panel).to_be_hidden()
    expect(export_panel(page, other)).to_be_visible()
    page.locator("h1").click()
    expect(export_panel(page, other)).to_be_hidden()

    # Download through the menu: the same content as the export URL.
    button.click()
    with page.expect_download() as download_info:
        panel.get_by_role("link", name=re.compile("JSON")).click()
    download = download_info.value
    assert download.suggested_filename == f"fta_{analysis_id}.json"
    with open(download.path(), "rb") as handle:
        assert handle.read() == e2e_server.export(analysis_id, "json")
    expect(panel).to_be_hidden()


@pytest.mark.acceptance("E-L07")
def test_E_L07_download_while_renaming_has_no_leave_confirmation(page, e2e_server):
    analysis_id = e2e_server.create_analysis("改名中の出力")
    e2e_server.add_level1(analysis_id, "要因")
    open_list(page)
    dialogs = record_dialogs(page)
    field = start_rename(page, analysis_id, "改名中の値")

    for fmt, name, filename in (("csv", "CSV", f"fta_{analysis_id}.csv"), ("markdown", "Markdown", f"fta_{analysis_id}.md")):
        export_button(page, analysis_id).click()
        with page.expect_download() as download_info:
            export_panel(page, analysis_id).get_by_role("link", name=re.compile(name)).click()
        assert download_info.value.suggested_filename == filename
        with open(download_info.value.path(), "rb") as handle:
            assert handle.read() == e2e_server.export(analysis_id, fmt)

    page.wait_for_timeout(300)
    assert dialogs == []
    expect(guard_dialog(page)).to_have_count(0)
    expect(page).to_have_url(f"{e2e_server.url}/")
    expect(field).to_have_value("改名中の値")


# ----- E-L08 ----------------------------------------------------------------

@pytest.mark.acceptance("E-L08")
def test_E_L08_empty_list(page, e2e_server):
    open_list(page)
    empty = page.locator("[data-empty-state]")
    expect(empty).to_be_visible()
    expect(empty.get_by_role("heading", name="分析がまだありません")).to_be_visible()
    expect(page.locator("[data-list-table]")).to_be_hidden()
    expect(page.locator("[data-analysis-count]")).to_have_text("0")
    create = empty.get_by_role("link", name="＋ 新規分析を作成")
    expect(create).to_have_attribute("href", "/analyses/new")
    create.click()
    expect(page).to_have_url(f"{e2e_server.url}/analyses/new")

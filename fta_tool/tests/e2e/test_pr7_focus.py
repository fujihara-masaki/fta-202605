"""E2E (PR-7, the fix of 2026-10-29; plan 8.7 conditions 2, 3 and 4): the
notifications have a room of their own (below the work area on the edit
screen, below the main area on the others) and the inspector's 保存・取消
are at its bottom, outside its scroll area. Checked as the screen is,
never helped by a scroll of the test (layout_checks.reach(scroll=False),
focus_shown(), tab_walk()):

* E-V01 / E-V03  保存・取消 in view and on top from the moment the factor's
  editor is shown: right after the factor was chosen, before any input,
  while typing, after a save and a failed save (its reason in the bar),
  after another factor was chosen and after a partial update; with a
  notification that stays (an error) shown;
* E-K01  Tab, Shift+Tab and the arrow keys with several notifications shown
  (errors that stay; success・お知らせ・注意 checked while they are still
  there): after each key, the control and its focus outline are in view
  and on top; the notifications' 閉じる are reached and used with the keys;
* E-K01  a notification shown after the focus was placed (in the work area,
  in the inspector while typing, on the list) hides neither the control nor
  its outline, and leaves the focus, the input, its selection and the
  unsaved state as they were.

The same checks run on the user's Windows PC in tests/e2e/display_check.py.
"""

from __future__ import annotations

import pytest

from tests.e2e import acceptance
from tests.e2e.edit_helpers import (
    editor,
    expect_editor_ready,
    factor_cancel,
    factor_field,
    factor_message,
    factor_save,
    factor_status,
    open_edit,
    select_button,
    toast,
)
from tests.e2e.layout_checks import focus_shown, reach, tab_walk
from tests.e2e.support import expect
from tests.e2e.test_pr7_viewports import CASE_BY_LABEL, build, cases, shown
from tests.e2e.test_pr7_viewports import editor_bar_as_shown as bar_as_shown

pytestmark = pytest.mark.e2e

NOTIFY = "async ([message, type]) => (await import('/static/js/common/notify.js')).notify(message, { type })"

# The sizes where the notifications took most room or the layout changes:
# the lowest, below 1024px, both sides of 1280px, the base size.
FOCUS_SIZES = ["1093x500", "900x600", "1024x683", "edge150-1275x609", "chrome150-1280x630", "1280x620"]


def focus_cases():
    params = [pytest.param(acceptance.BASE_CASES[0], id=acceptance.BASE_CASES[0].label)]
    params += [pytest.param(CASE_BY_LABEL[label], id=label) for label in FOCUS_SIZES]
    return pytest.mark.parametrize("viewport", params, indirect=True)


def notify(page, message: str, kind: str = "error") -> None:
    page.evaluate(NOTIFY, [message, kind])


def toasts(page) -> int:
    return page.locator("#ui-toasts .ui-toast").count()


def untouched(page) -> None:
    """Nothing was typed, clicked or scrolled in the inspector yet."""
    state = page.evaluate("""() => ({
      inside: Boolean(document.activeElement && document.activeElement.closest('#edit-inspector')),
      top: document.querySelector('[data-scroll="inspector"]').scrollTop })""")
    assert state == {"inside": False, "top": 0}, state


def many_factors(server, title: str, count: int = 14) -> tuple[int, list[int]]:
    analysis_id = server.create_analysis(title, top_event="ログインできない")
    return analysis_id, [server.add_level1(analysis_id, f"一次要因{n:02d}：確認のための長めの要因名") for n in range(count)]


def walk_with_notifications(page, *, presses: int = 60, what: str = "") -> list[dict]:
    """Tab and Shift+Tab with notifications shown (focus_shown after each
    key): first while a success, an お知らせ and a 注意 are still there,
    then with three errors that stay."""
    for kind in ("success", "info", "warning"):
        notify(page, f"フォーカスの確認（{kind}）", kind)
    seen = tab_walk(page, 6, toasts=3, what=f"{what}短い通知の間・")
    page.evaluate("() => document.querySelectorAll('#ui-toasts .ui-toast__close').forEach((b) => b.click())")
    for n in range(3):
        notify(page, f"フォーカスの確認：閉じるまで残るエラー {n + 1}")
    seen += tab_walk(page, presses, toasts=3, what=f"{what}エラーの通知3件・")
    seen += tab_walk(page, presses // 2, key="Shift+Tab", toasts=3, what=f"{what}エラーの通知3件・")
    return seen


def close_notifications_by_keyboard(page, what: str = "") -> None:
    """Each notification's 閉じる is reached with Tab (in view, its stack
    scrolls to it) and closes it with Enter."""
    while toasts(page):
        before = toasts(page)
        for _ in range(200):
            page.keyboard.press("Tab")
            found = focus_shown(page, f"{what}通知の閉じる")
            if found and found["inToasts"] and found["label"] == "閉じる":
                break
        else:
            raise AssertionError(f"{what}Tab で通知の閉じるに届かない")
        page.keyboard.press("Enter")
        expect(page.locator("#ui-toasts .ui-toast")).to_have_count(before - 1)


# ----- E-V01 / E-V03: 保存・取消 from the moment the editor is shown ----------------------

@pytest.mark.acceptance("E-V01")
@cases(small_ids=("E-V03",))
def test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown(page, page_watch, e2e_server,
                                                                           display_case, request):
    analysis_id, a, b, c, d = build(e2e_server, "保存・取消の表示")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect(editor(page)).to_have_attribute("data-node-id", str(b))
    bar_as_shown(page, "要因を選んだ直後")
    expect_editor_ready(page, b)
    shown(page, request, display_case, "保存・取消：入力の前から")
    untouched(page)
    bar_as_shown(page, "入力の前")

    factor_field(page, "memo").fill("入力中のメモ")
    bar_as_shown(page, "入力中")
    factor_save(page).click()
    expect(factor_status(page)).to_have_text("保存済み")
    bar_as_shown(page, "保存の成功の後")

    # A failed save: its reason in the bar, the error notification stays.
    page_watch.allow_console_error(r"status of 500")
    page.route(f"**/nodes/{b}/update", lambda route: route.fulfill(status=500, body="error"))
    factor_field(page, "memo").fill("保存に失敗するメモ")
    factor_save(page).click()
    expect(toast(page, "要因を保存できませんでした", "error")).to_be_visible()
    expect(factor_message(page)).to_be_visible()
    bar_as_shown(page, "保存の失敗の後")
    reach(factor_message(page), name="保存失敗の理由（帯の中）", scroll=False)
    # The bar never covers a field: from 取消 back through the fields.
    factor_cancel(page).focus()
    tab_walk(page, 8, key="Shift+Tab", toasts=1, what="保存の失敗の後・")
    page.unroute(f"**/nodes/{b}/update")
    factor_cancel(page).click()
    expect(factor_status(page)).to_have_text("保存済み")

    # Another factor (its editor is new), then a partial update.
    select_button(page, "group", a).click()  # the parent's name in ③'s group heading
    expect_editor_ready(page, a)
    bar_as_shown(page, "要因の切替の後")
    marked = page.evaluate("() => { document.querySelector('[data-inspector-title]').dataset.fta = 'before'; return 1; }")
    assert marked
    page.evaluate("() => window.ftaEditBridge.refresh({})")
    expect(page.locator("[data-inspector-title][data-fta='before']")).to_have_count(0)
    expect_editor_ready(page, a)
    bar_as_shown(page, "部分更新の後")
    assert toasts(page) >= 1  # the error stayed through all of it


# ----- E-K01: the focus with notifications shown ---------------------------------------

@pytest.mark.acceptance("E-K01")
@focus_cases()
def test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications(page, e2e_server, display_case):
    analysis_id, ids = many_factors(e2e_server, "通知の表示中のフォーカス")
    open_edit(page, analysis_id, f"#sel={ids[-1]}&step=2&view=work")
    expect_editor_ready(page, ids[-1])
    seen = walk_with_notifications(page)
    places = {("toasts" if f["inToasts"] else f["label"]) for f in seen}
    assert "toasts" in places, "Tab が通知の閉じるに届いていない"
    assert len(places) >= 20, places

    # The arrow keys: the view tabs (roving focus).
    page.locator("#edit-tab-work").focus()
    for key, tab_id in (("ArrowRight", "edit-tab-tree"), ("ArrowRight", "edit-tab-table"),
                        ("ArrowLeft", "edit-tab-tree"), ("ArrowLeft", "edit-tab-work")):
        page.keyboard.press(key)
        expect(page.locator(f"#{tab_id}")).to_be_focused()
        focus_shown(page, f"{key}（表示タブ）")
    assert toasts(page) == 3
    close_notifications_by_keyboard(page)


@pytest.mark.acceptance("E-K01")
@focus_cases()
def test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing(page, e2e_server, display_case):
    analysis_id, ids = many_factors(e2e_server, "フォーカスの後の通知")
    open_edit(page, analysis_id, f"#sel={ids[-1]}&step=2&view=work")
    expect_editor_ready(page, ids[-1])

    # The work area: Tab to a control at the bottom of its visible part.
    area = page.locator('[data-scroll="center"]')
    for _ in range(150):
        page.keyboard.press("Tab")
        found = focus_shown(page, "作業エリアの下端まで")
        bottom = area.evaluate("(el) => el.getBoundingClientRect().bottom")
        if found and found["visible"][3] > bottom - 90 and page.evaluate(
                "() => Boolean(document.activeElement.closest('[data-scroll=\"center\"]'))"):
            break
    else:
        raise AssertionError("作業エリアの下端の操作に Tab で届かない")
    page.evaluate("() => { window.__ftaFocused = document.activeElement; }")
    for n in range(3):
        notify(page, f"フォーカスの後のエラー {n + 1}")
    assert toasts(page) == 3
    focus_shown(page, "通知の後（作業エリア）")
    assert page.evaluate("() => document.activeElement === window.__ftaFocused")

    # The inspector, while typing: the focus, the text, its selection and
    # the unsaved state stay.
    field = factor_field(page, "prevention_idea")
    field.click()
    page.keyboard.type("入力中の再発防止策")
    page.keyboard.press("Shift+Home")
    before = field.evaluate("(el) => [el.value, el.selectionStart, el.selectionEnd]")
    expect(factor_status(page)).to_have_text("入力中（未保存）")
    notify(page, "入力中に出たお知らせ", "info")
    notify(page, "入力中に出た注意", "warning")
    focus_shown(page, "通知の後（インスペクタで入力中）")
    expect(field).to_be_focused()
    assert field.evaluate("(el) => [el.value, el.selectionStart, el.selectionEnd]") == before
    expect(factor_status(page)).to_have_text("入力中（未保存）")
    assert toasts(page) == 5


@pytest.mark.acceptance("E-K01")
@focus_cases()
def test_E_K01_the_list_keeps_the_focus_in_view_with_notifications(page, e2e_server, display_case):
    ids = [e2e_server.create_analysis(f"通知とフォーカスの一覧 {n:02d}", top_event="頂上事象") for n in range(14)]
    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    main = page.locator("#main")
    for _ in range(200):
        page.keyboard.press("Tab")
        found = focus_shown(page, "一覧の下端まで")
        if found and found["visible"][3] > main.evaluate("(el) => el.getBoundingClientRect().bottom") - 80:
            break
    else:
        raise AssertionError("一覧の下端の操作に Tab で届かない")
    page.evaluate("() => { window.__ftaFocused = document.activeElement; }")
    notify(page, "一覧でのエラー（閉じるまで残る）")
    notify(page, "一覧での成功", "success")
    focus_shown(page, "通知の後（一覧）")
    assert page.evaluate("() => document.activeElement === window.__ftaFocused")
    tab_walk(page, 10, toasts=2, what="一覧・")
    tab_walk(page, 30, key="Shift+Tab", toasts=1, what="一覧・")
    row = page.locator(f'tr[data-analysis-id="{ids[0]}"]')
    reach(row.locator('[data-action="rename"]'), name="一覧の改名（通知の表示中）")

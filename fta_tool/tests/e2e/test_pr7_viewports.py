"""E2E: PR-7 display areas — E-V01, E-V02, E-V03 (plan 5.9.4, 8.7, 8.9).

Every test runs at the base sizes (1280x800, 1440x900) and at PR-7's sizes
(acceptance.PR7_CASES): the plan's assumed sizes and the user's display
areas measured on 2026-10-28 with their devicePixelRatio. The browser is
**not zoomed**: a size of a zoom level is not that zoom level, and these
results are recorded apart from the checks on the user's Windows PC
(manual-check-pr7.md).

* E-V01  the layout of the width (three panes from 1280px; below it the
         structure navigation folded and shown by 「構造を表示」 over the work
         area), and every main control — the work steps, tabs, filter, the
         work list's buttons, the judgement, the inspector's 保存・取消 and
         削除, the header, the operation bar, the status line of a generation
         under way, the generation log, the notifications, the inspector's
         message of a failed save, the dialogs (unsaved changes, delete,
         manual add, leaving the page) — is visible, inside the display area
         and on top (its centre and four inner points: no notification or
         other element covers it); the list and the new-analysis screens'
         main controls too.
* E-V02  from 1024px on, the page never scrolls sideways (with the folded
         navigation open, while a generation runs, with a dialog open); the
         navigation and the inspector never scroll sideways; below 1024px
         only the work area does.
* E-V03  at 900x600 and 1093x500 the inspector's 保存・取消 and the dialogs'
         buttons are reached without scrolling the page sideways.

The display area is measured after the app is shown and must be the
requested one (no tolerance here); it is recorded with the layout found
(e2e-report.md). With --e2e-screens the screens are kept for the visual
review (not part of the verdict).
"""

from __future__ import annotations

import re

import pytest

from tests.e2e import acceptance
from tests.e2e.edit_helpers import (
    add_dialog,
    expect_editor_ready,
    factor_cancel,
    factor_field,
    factor_message,
    factor_save,
    gen_log,
    gen_status,
    inspector,
    judgement_button,
    item,
    leave_dialog,
    leave_link,
    open_edit,
    select_button,
    step_button,
    step_panel,
    tab,
    toast,
    wait_phase,
)
from tests.e2e import layout_checks
from tests.e2e.layout_checks import assert_no_page_hscroll, layout, pane_scroll, reach
from tests.e2e.support import expect, measure_viewport, save_screenshot

pytestmark = pytest.mark.e2e

SMALL = {"900x600", "1093x500"}


def cases(*, small_ids=()):
    """Base and PR-7 sizes; the two small ones also carry `small_ids`."""
    params = []
    for case in acceptance.BASE_CASES + acceptance.PR7_CASES:
        marks = [pytest.mark.acceptance(*small_ids)] if small_ids and case.label in SMALL else []
        params.append(pytest.param(case, id=case.label, marks=marks))
    return pytest.mark.parametrize("viewport", params, indirect=True)


def build(server, title="表示領域の確認"):
    """一次A (Yes) → 二次B → 三次C; 一次D. Long names wrap, never widen a pane."""
    analysis_id = server.create_analysis(title, top_event="ログインできない", system_context="Web 2台・DB 1台")
    a = server.add_level1(analysis_id, "一次要因A：ネットワーク機器の設定変更が反映されていない可能性がある", "説明A")
    b = server.add_child(a, "二次要因B", "説明B")
    c = server.add_child(b, "三次要因C")
    d = server.add_level1(analysis_id, "一次要因D")
    server.update_node(a, user_judgement="yes")
    return analysis_id, a, b, c, d


def shown(page, request, display_case, name: str = "") -> dict:
    """Measure the display area, check it is the requested one, record it
    with the layout found; returns the layout (tests/e2e/layout_checks.py)."""
    measured = measure_viewport(page)
    found = layout(page) if page.locator("[data-edit-page]").count() else {}
    mode = ("構造ナビの折りたたみ" if found.get("folded") else "3ペイン") if found else "（編集画面以外）"
    acceptance.record_display(request.node, requested=display_case.size, dpr=display_case.dpr,
                              origin=display_case.origin, measured=measured, layout=mode,
                              note=name)
    assert tuple(measured["client"]) == display_case.size, (
        f"表示領域が要求と違う：要求 {display_case.width}×{display_case.height}、実測 {measured['client']}")
    if display_case.dpr:
        assert measured["devicePixelRatio"] == display_case.dpr
    return found


def keep(page, request, name: str) -> None:
    """A screen for the visual review (--e2e-screens), named after the test."""
    folder = acceptance.screens_dir(request.config)
    if folder is None:
        return
    slug = re.sub(r"[^\w.-]+", "-", request.node.name)[:90]
    result = save_screenshot(page, folder / f"{slug}--{name}.png")
    acceptance.add_screenshot(request.node, name, result)


def expect_layout(page, display_case) -> dict:
    """The layout of the width (plan 5.9.4) and the panes inside the display area."""
    found = layout(page)
    width = display_case.width
    center, side = found["center"], found["inspector"]
    assert center and side
    if width >= 1280:
        assert not found["folded"] and found["toggle"] is None, found  # no button: the left pane is there
        nav = found["nav"]
        assert nav and nav[0] >= 0 and nav[0] + nav[2] <= center[0] + 1, found
    else:
        assert found["folded"] and found["nav"] is None and found["toggle"] == "false", found
        assert center[0] >= 0
    assert center[0] + center[2] <= side[0] + 1 and side[0] + side[2] <= width + 0.5, found
    for box in (center, side):
        assert box[3] > 150 and box[1] + box[3] <= display_case.height + 0.5, found
    return found


def expect_scrolling(page, display_case, what: str) -> None:
    """E-V02: the page from 1024px on, the panes at every width."""
    if display_case.width >= 1024:
        assert_no_page_hscroll(page, what)
    panes = pane_scroll(page)
    for name in ("nav", "inspector"):
        pane = panes.get(name)
        if pane and pane["shown"]:
            assert pane["scrollWidth"] <= pane["clientWidth"], (name, pane, what)
    center = panes["center"]
    if display_case.width >= 1024:
        assert center["scrollWidth"] <= center["clientWidth"], (center, what)


def main_controls(page, b) -> dict:
    work = item(page, "work", b)
    return {
        **{f"作業ステップ{n}": step_button(page, n) for n in range(1, 6)},
        **{f"表示タブ{view}": tab(page, view) for view in ("work", "tree", "table")},
        "絞り込み": page.locator("#edit-filter-text"),
        "評価の絞り込み": page.locator("#edit-filter-judgement"),
        "絞り込みのクリア": page.locator('[data-action="filter-clear"]'),
        "作業リストの要因": select_button(page, "work", b),
        "作業リストの評価Yes": judgement_button(work, b, "yes"),
        "インスペクタの評価No": judgement_button(inspector(page), b, "no"),
        "インスペクタの削除": inspector(page).get_by_role("button", name="この要因を削除"),
        "インスペクタの手動追加": inspector(page).get_by_role("button", name="手動追加"),
        "タイトルの変更": page.locator("[data-title-edit]"),
        "出力メニュー": page.locator(".edit-header [data-ui-menu-button]"),
        "一覧へ": leave_link(page),
        "操作バーの生成": step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成"),
    }


def editor_bar_as_shown(page, what: str) -> None:
    """保存・取消 as the screen is, before any input (no focus, no scroll)."""
    reach(factor_save(page), name=f"保存（{what}）", scroll=False)
    reach(factor_cancel(page), name=f"取消（{what}）", scroll=False)


def editor_bar(page, what: str) -> None:
    """保存・取消 while a field of the editor is in use: in view without any
    further scrolling (at the inspector's bottom, outside its scroll area;
    PR-7's fix of 2026-10-29). The focus brings the field into view, as the
    user's click or Tab does. Before any input: editor_bar_as_shown()."""
    factor_field(page, "title").focus()
    reach(factor_save(page), name=f"保存（{what}）", scroll=False)
    reach(factor_cancel(page), name=f"取消（{what}）", scroll=False)


# ----- E-V01 / E-V02 / E-V03: the edit screen ---------------------------------------

@pytest.mark.acceptance("E-V01", "E-V02")
@cases(small_ids=("E-V03",))
def test_E_V01_edit_layout_and_main_controls(page, e2e_server, display_case, request):
    analysis_id, a, b, c, d = build(e2e_server)
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    shown(page, request, display_case, "③・二次要因Bを選択")
    expect_layout(page, display_case)
    expect_scrolling(page, display_case, "③")
    editor_bar_as_shown(page, "入力の前")
    for name, control in main_controls(page, b).items():
        reach(control, name=name)
    editor_bar(page, "要因の内容を入力中")
    keep(page, request, "編集画面")

    if display_case.width < 1280:
        # The folded navigation: shown over the work area, never over the
        # inspector or the header; the focus goes to the selected factor.
        toggle = page.locator("[data-nav-toggle]")
        reach(toggle, name="構造を表示")
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(toggle).to_have_text("構造を閉じる")
        found = layout(page)
        nav, side = found["nav"], found["inspector"]
        assert nav and nav[0] >= 0 and nav[0] + nav[2] <= side[0] + 0.5, found
        expect(select_button(page, "nav", b)).to_be_focused()
        for node in (a, b, c, d):
            reach(select_button(page, "nav", node), name=f"構造ナビの要因 {node}")
        reach(toggle, name="構造を閉じる")
        reach(factor_save(page), name="保存（構造ナビを開いた状態）", scroll=False)
        expect_scrolling(page, display_case, "構造ナビを開いた状態")
        keep(page, request, "構造ナビを開いた状態")
        page.keyboard.press("Escape")
        expect(page.locator("#edit-nav")).to_be_hidden()
        expect(toggle).to_be_focused()
        expect(toggle).to_have_attribute("aria-expanded", "false")


@pytest.mark.acceptance("E-V01", "E-V02")
@cases()
def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
                                                                      request):
    analysis_id, a, b, c, d = build(e2e_server, "生成と通知の表示")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    shown(page, request, display_case, "生成中・生成ログ・通知・保存失敗")
    e2e_server.set_stub_mode("delay", delay_seconds=2)
    generate = step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成")
    generate.click()
    wait_phase(page, "running")
    # The status line of a generation under way, above the work area.
    expect(gen_status(page)).to_be_visible()
    reach(gen_status(page).locator("[data-gen-status-text]").first, name="生成中の状態表示")
    reach(factor_save(page), name="保存（生成中。押せないが見える）", scroll=False)
    expect_scrolling(page, display_case, "生成中")
    keep(page, request, "生成中")
    wait_phase(page, "idle", timeout=30)

    # The generation log, below the operation bar; the notifications (the
    # result's, and an error that stays, so that they are surely there while
    # it is checked) cover none of the controls.
    log = gen_log(page)
    expect(log).to_be_visible()
    page.evaluate("async () => (await import('/static/js/common/notify.js')).notify("
                  "'閉じるまで残るエラー（生成の後の確認）', { type: 'error' })")
    expect(toast(page, "件作成しました", "success").first).to_be_visible()
    reach(log.locator("#edit-genlog-title"), name="生成ログの見出し")
    reach(log.locator("[data-gen-log-close]"), name="生成ログを閉じる")
    reach(generate, name="操作バーの生成（生成後）")
    editor_bar(page, "生成の結果の通知が出ている間")
    expect(toast(page, "閉じるまで残るエラー", "error")).to_be_visible()
    assert page.locator("#ui-toasts .ui-toast").count() >= 2
    keep(page, request, "生成ログ")

    # A failed save: the reason in the inspector and an error that stays.
    page_watch.allow_console_error(r"status of 500")  # the browser's log of the 500 forced here
    page.route(f"**/nodes/{b}/update", lambda route: route.fulfill(status=500, body="error"))
    factor_field(page, "memo").fill("保存に失敗するメモ")
    factor_save(page).click()
    error = toast(page, "要因を保存できませんでした", "error")
    expect(error).to_be_visible()
    expect(factor_message(page)).to_be_visible()
    reach(factor_message(page), name="保存失敗の表示（インスペクタ）")
    reach(error.locator(".ui-toast__close"), name="エラーの通知を閉じる")
    editor_bar(page, "エラーの通知が残っている間")
    reach(generate, name="操作バーの生成（エラーの通知が残っている間）")
    expect_scrolling(page, display_case, "保存失敗")
    keep(page, request, "保存失敗の表示と通知")


@pytest.mark.acceptance("E-V01", "E-V02")
@cases(small_ids=("E-V03",))
def test_E_V01_dialogs_fit_and_their_buttons_are_reached(page, e2e_server, display_case, request):
    analysis_id, a, b, c, d = build(e2e_server, "ダイアログの表示")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    shown(page, request, display_case, "ダイアログ")

    def fits(dialog, buttons: list[str], name: str) -> None:
        expect(dialog).to_be_visible()
        box = dialog.bounding_box()
        assert box["x"] >= 0 and box["y"] >= 0, (name, box)
        assert box["x"] + box["width"] <= display_case.width + 0.5, (name, box)
        assert box["y"] + box["height"] <= display_case.height + 0.5, (name, box)
        for label in buttons:
            reach(dialog.get_by_role("button", name=label, exact=True), name=f"{name}：{label}", scroll=False)
        expect_scrolling(page, display_case, name)
        keep(page, request, name)

    # Unsaved changes when the factor is switched (R-01): three choices.
    factor_field(page, "memo").fill("切り替える前の下書き")
    select_button(page, "group", a).click()  # the parent's name in ③'s group heading
    switch = page.get_by_role("dialog", name="保存していない変更があります")
    fits(switch, ["保存して移動", "破棄して移動", "編集を続ける"], "未保存確認（要因の切替）")
    page.keyboard.press("Escape")
    expect(switch).to_have_count(0)

    # Leaving the page with the same draft.
    leave_link(page).click()
    fits(leave_dialog(page), ["保存して移動", "破棄して移動", "編集を続ける"], "未保存確認（画面の移動）")
    page.keyboard.press("Escape")
    factor_cancel(page).click()

    # Delete (with its descendants) and manual add.
    inspector(page).get_by_role("button", name="この要因を削除").click()
    fits(page.get_by_role("dialog", name="要因を削除しますか？"), ["削除する", "キャンセル"], "削除確認")
    page.keyboard.press("Escape")
    inspector(page).get_by_role("button", name="手動追加").click()
    dialog = add_dialog(page)
    reach(page.locator("#add-factor-title"), name="手動追加のタイトル")
    fits(dialog, ["追加する", "キャンセル"], "手動追加")
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)


# ----- E-V01 / E-V02 / E-V03: the list and the new-analysis screens -------------------

@pytest.mark.acceptance("E-V01", "E-V02")
@cases(small_ids=("E-V03",))
def test_E_V01_list_and_new_screens(page, e2e_server, display_case, request):
    ids = [e2e_server.create_analysis(f"一覧の表示の確認 {n}：長いタイトルが折り返されても操作が見えること" * 2,
                                      top_event="頂上事象") for n in range(3)]
    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    shown(page, request, display_case, "一覧")
    if display_case.width >= 1024:
        assert_no_page_hscroll(page, "一覧")
    row = page.locator(f'tr[data-analysis-id="{ids[0]}"]')
    for name, control in {
        "新規作成": page.locator("main").get_by_role("link", name="＋ 新規分析を作成"),
        "分析を開く": row.locator("[data-title-link]"),
        "改名": row.locator('[data-action="rename"]'),
        "出力": row.locator("[data-ui-menu-button]"),
        "削除": row.locator('[data-action="delete"]'),
    }.items():
        reach(control, name=f"一覧：{name}")
    keep(page, request, "一覧")
    row.locator('[data-action="delete"]').click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    for button in dialog.get_by_role("button").all():
        reach(button, name="一覧の削除ダイアログ", scroll=False)
    keep(page, request, "一覧の削除ダイアログ")
    page.keyboard.press("Escape")

    page.goto("/analyses/new")
    expect(page.locator("h1")).to_have_text("新規FTA分析を作成")
    if display_case.width >= 1024:
        assert_no_page_hscroll(page, "新規作成")
    for name, control in {
        "タイトル": page.locator("#title"),
        "頂上事象": page.locator("#top_event"),
        "作成": page.locator("[data-submit]"),
        "キャンセル": page.locator("[data-cancel-link]"),
    }.items():
        reach(control, name=f"新規作成：{name}")
    keep(page, request, "新規作成")
    page.fill("#title", "入力あり")
    page.locator("[data-cancel-link]").click()
    dialog = page.get_by_role("dialog", name="作成していない入力があります")
    for label in ("入力を続ける", "破棄して移動"):
        reach(dialog.get_by_role("button", name=label), name=f"新規作成の確認：{label}", scroll=False)
    page.keyboard.press("Escape")


# ----- the checks catch what they must ------------------------------------------------

# Each fault is a layout these checks must refuse, at the size where it shows.
FAULTS = {
    # The page's minimum width of PR-3〜PR-6 (1100px): 1366x768 at 125 % scrolls sideways.
    "page-min-width-1100": ("1093x500", ".edit-page { min-width: 1100px; }", "page"),
    "three-panes-below-1280": ("edge150-1275x609",
                               "@media (width < 1280px) { .edit-layout { grid-template-columns: 240px minmax(0, 1fr) 340px; }"
                               " .edit-nav { position: static; } .edit-nav:not([data-open]) { display: flex; } }", "layout"),
    # The notifications put over the inspector again (fixed at the bottom
    # right, as an overlay; since PR-7's fix they have a row of their own).
    "notifications-over-the-inspector": ("1093x500", ".edit-body .ui-toast-stack { position: fixed; right: 0; bottom: 0; "
                                                     "z-index: var(--z-toast); width: 340px; max-height: none; }",
                                         "toast"),
    # The 保存・取消 bar back in the inspector's scroll area (its place until PR-7's fix).
    "bar-in-the-scroll-area": ("1093x500", ".edit-editor__bar { position: static; }", "bar"),
    "covered-control": ("900x600", "body::after { content: ''; position: fixed; inset: 0; z-index: 2147483647; }", "bar"),
    "inspector-out-of-view": ("900x600", "@media (width < 1024px) { .edit-layout { min-width: 1024px; } }", "bar"),
}


CASE_BY_LABEL = {case.label: case for case in acceptance.PR7_CASES}


@pytest.mark.acceptance("E-V01")
@pytest.mark.parametrize("viewport, fault", [
    pytest.param(CASE_BY_LABEL[size], fault, id=f"{fault}-{size}") for fault, (size, _css, _kind) in FAULTS.items()
], indirect=["viewport"])
def test_the_pr7_layout_checks_catch_what_they_must(page, e2e_server, display_case, fault):
    size, css, kind = FAULTS[fault]
    analysis_id, a, b, c, d = build(e2e_server, "検査の検出力")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    # As it is, it passes …
    expect_layout(page, display_case)
    expect_scrolling(page, display_case, "そのまま")
    editor_bar(page, "そのまま")
    if kind == "toast":
        page.evaluate("async () => (await import('/static/js/common/notify.js')).notify("
                      "'検出力の確認：閉じるまで残るエラー。保存・取消の上に重なると失敗にならなければならない', { type: 'error' })")
        editor_bar(page, "エラーの通知（そのまま）")
    # … with the fault it must not.
    page.add_style_tag(content=css)
    with pytest.raises(AssertionError):
        if kind == "page":
            expect_scrolling(page, display_case, "不具合")
        elif kind == "layout":
            expect_layout(page, display_case)
        else:
            editor_bar(page, "不具合")


@pytest.mark.acceptance("E-V01")
@pytest.mark.parametrize("viewport", [CASE_BY_LABEL["1093x500"]], ids=["1093x500"], indirect=True)
def test_reach_tells_as_shown_a_pane_scroll_and_a_notification_over_it_apart(page, e2e_server, display_case):
    """reach() keeps "not covered from the start" apart from "reached after
    a scroll"; scroll=False (the main buttons) accepts no scroll, and a
    notification over a control fails either way."""
    analysis_id, a, b, c, d = build(e2e_server, "到達の区別")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    seen = []
    layout_checks.OBSERVERS.append(seen.append)
    try:
        generate = step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成")
        reach(generate, name="生成")  # below the work area's visible part at this size
        assert seen[-1]["how"] == layout_checks.REACHED_BY_PANE_SCROLL
        reach(generate, name="生成（スクロールした後）")
        assert seen[-1]["how"] == layout_checks.REACHED_AS_SHOWN

        # 保存 before a field is in use: in view at once since PR-7 (the bar
        # at the bottom of the inspector, outside its scroll area).
        reach(factor_save(page), name="保存（入力の前。スクロールなし）", scroll=False)
        assert seen[-1]["how"] == layout_checks.REACHED_AS_SHOWN

        # A notification over a control of the work area (the stack put
        # back over the page, as it was before PR-7's fix): a failure, with
        # or without a scroll, and the record names the notification.
        page.evaluate("async () => (await import('/static/js/common/notify.js')).notify("
                      "'到達の区別の確認', { type: 'error' })")
        top = generate.evaluate("(el) => el.getBoundingClientRect().top")
        page.add_style_tag(content=f".ui-toast-stack {{ position: fixed !important; top: {top - 8}px !important; "
                                   "left: 0; width: 560px; max-height: none !important; }}")
        for scroll in (False, True):
            with pytest.raises(AssertionError, match="通知に覆われている"):
                reach(generate, name=f"生成（通知の下。{'ペインのスクロールあり' if scroll else 'スクロールなし'}）",
                      scroll=scroll)
            entry = seen[-1]
            assert entry["how"] == layout_checks.NOT_REACHED and entry["covered_by_notifications"]
            assert [t["text"] for t in entry["notifications"]] == ["到達の区別の確認"]
    finally:
        layout_checks.OBSERVERS.remove(seen.append)

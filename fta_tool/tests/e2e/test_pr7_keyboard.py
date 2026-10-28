"""E2E: PR-7 keyboard, focus and announcements — E-K01, E-K02, E-K03
(plan 5.7, 8.7, 8.9; 付録D).

Only the keyboard is used where these tests say so: the focus is moved with
Tab / Shift+Tab (tab_to() presses Tab until the control has the focus, so it
proves the control is in the tab order and reached from where the focus
was), and controls are used with Enter, Space, the arrow keys and Esc. No
mouse click, no locator.click().

* E-K01  the representative scenario (付録D 1〜5, 7〜11; 6, the result
         categories, is the same Enter on the generation button and is
         E-G03's) by keyboard only:
         create an analysis from the empty list, edit the top event and
         generate 一次 without saving (the automatic save), judge Yes and
         generate 二次, save the inspector's fields, add a factor manually,
         delete one, the filter, the export menu, leave with an unsaved change (three
         choices); at a folded width the structure navigation by keyboard;
         while a generation runs, the keyboard cannot get round its
         restrictions (no write is sent, no link is followed).
* E-K02  dialogs: the initial focus (the safe choice; the title field of
         the manual add), Tab and Shift+Tab never reach the page behind (in
         Chromium the focus goes to the browser's own UI between the last
         and the first control: document.activeElement is then the body),
         Esc is the cancel choice, and the focus returns to the control that
         opened the dialog (or the nearest one when it is gone).
* E-K03  the live regions (#ui-live-status role=status, polite;
         #ui-live-alert role=alert, assertive): the start, each parent's
         result and the summary of a generation, a failed generation and a
         failed save are written to them (recorded with a MutationObserver
         from the page's start). **This checks the DOM, not a screen
         reader**: what NVDA and Edge actually read is checked by hand
         (manual-check-pr7.md).
"""

from __future__ import annotations

import pytest

from tests.e2e import acceptance
from tests.e2e.edit_helpers import (
    LEAVE_DIALOG,
    expect_editor_ready,
    factor_field,
    inspector,
    item,
    judgement_button,
    open_edit,
    select_button,
    step_button,
    step_panel,
    wait_phase,
)
from tests.e2e.support import expect

pytestmark = pytest.mark.e2e

FOLDED = next(case for case in acceptance.PR7_CASES if case.label == "edge150-1275x609")
KEYBOARD_CASES = pytest.mark.parametrize(
    "viewport", [pytest.param(case, id=case.label) for case in acceptance.BASE_CASES + (FOLDED,)], indirect=True)

ACTIVE = """() => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  return el.id || el.getAttribute('data-action') || el.textContent.trim().slice(0, 40);
}"""


def tab_to(page, locator, *, backwards: bool = False, limit: int = 400) -> int:
    """Press Tab (Shift+Tab) until `locator` has the focus; the presses it took."""
    key = "Shift+Tab" if backwards else "Tab"
    handle = locator.element_handle()
    for presses in range(1, limit + 1):
        page.keyboard.press(key)
        if page.evaluate("(el) => document.activeElement === el", handle):
            return presses
    raise AssertionError(f"{key} を {limit} 回押しても届かない：{locator}")


def posts(page) -> list[str]:
    sent: list[str] = []
    page.on("request", lambda r: sent.append("/" + r.url.split("/", 3)[3]) if r.method == "POST" else None)
    return sent


# ----- E-K01 ------------------------------------------------------------------------

@pytest.mark.acceptance("E-K01")
@KEYBOARD_CASES
def test_E_K01_the_representative_scenario_by_keyboard_only(page, e2e_server, display_case):
    sent = posts(page)
    # 1. The empty list → 新規作成 → the form → 作成して編集へ → ① opens.
    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    # The empty state's own link (the list's header has the same one).
    tab_to(page, page.get_by_label("分析がまだありません").get_by_role("link", name="＋ 新規分析を作成"))
    page.keyboard.press("Enter")
    expect(page.locator("h1")).to_have_text("新規FTA分析を作成")
    tab_to(page, page.locator("#title"))
    page.keyboard.type("キーボードだけの分析")
    tab_to(page, page.locator("#top_event"))
    page.keyboard.type("ログインできない")
    tab_to(page, page.locator("[data-submit]"))
    page.keyboard.press("Enter")
    expect(page.locator("#analysisTitle")).to_have_text("キーボードだけの分析")
    expect(step_button(page, 1)).to_have_attribute("aria-current", "step")
    analysis_id = int(page.url.rstrip("/").rsplit("/", 1)[1].split("#")[0])

    # 2. The top event changed and not saved, then 一次 generated: the
    #    automatic save first (plan 5.9.1).
    tab_to(page, page.locator("#topEventInput"))
    page.keyboard.press("End")
    page.keyboard.type("（キーボード）")
    tab_to(page, step_button(page, 2))
    page.keyboard.press("Enter")
    generate1 = step_panel(page, 2).locator('[data-action="generate"][data-level="1"]')
    tab_to(page, generate1)
    page.keyboard.press("Enter")
    wait_phase(page, "idle", timeout=30)
    assert e2e_server.analysis(analysis_id)["top_event"] == "ログインできない（キーボード）"
    factors = sorted(e2e_server.node_ids(analysis_id))
    assert factors
    first = factors[0]

    # 3. Judge Yes (Space on the toggle button), then 二次 from the Yes factors.
    yes = judgement_button(item(page, "work", first), first, "yes")
    tab_to(page, yes)
    page.keyboard.press("Space")
    expect(yes).to_have_attribute("aria-pressed", "true")
    assert e2e_server.judgement(first) == "yes"
    tab_to(page, step_button(page, 3), backwards=True)
    page.keyboard.press("Enter")
    generate2 = step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成")
    tab_to(page, generate2)
    page.keyboard.press("Enter")
    wait_phase(page, "idle", timeout=30)
    children = [n for n in e2e_server.node_ids(analysis_id) if n not in factors]
    assert children
    child = sorted(children)[0]

    # 4・5. Choose a factor (Enter on its row), save the inspector's fields.
    if display_case.width < 1280:
        # The folded navigation by keyboard: open, Tab to the factor, Enter
        # (it closes, the focus is on its button again).
        toggle = page.locator("[data-nav-toggle]")
        tab_to(page, toggle, backwards=True)
        page.keyboard.press("Enter")
        expect(toggle).to_have_attribute("aria-expanded", "true")
        tab_to(page, select_button(page, "nav", child))
        page.keyboard.press("Enter")
        expect(page.locator("#edit-nav")).to_be_hidden()
        expect(toggle).to_be_focused()
    else:
        tab_to(page, select_button(page, "work", child))
        page.keyboard.press("Enter")
    expect_editor_ready(page, child)
    tab_to(page, factor_field(page, "evidence"))
    page.keyboard.type("ログの記録")
    tab_to(page, inspector(page).locator("[data-factor-save]"))
    page.keyboard.press("Enter")
    expect(inspector(page).locator("[data-factor-status]")).to_have_text("保存済み")
    assert e2e_server.get_node(child)["evidence"] == "ログの記録"

    # 4. A factor added by hand below the chosen one's parent? Below it: 三次.
    tab_to(page, inspector(page).get_by_role("button", name="手動追加"))
    page.keyboard.press("Enter")
    expect(page.locator("#add-factor-title")).to_be_focused()
    page.keyboard.type("手動の三次要因")
    page.keyboard.press("Enter")
    expect(page.get_by_role("dialog", name="要因を手動追加")).to_have_count(0)
    expect(page.locator("[data-inspector-title]")).to_have_text("手動の三次要因")
    added = max(e2e_server.node_ids(analysis_id))

    # 8. Delete it: the dialog's safe choice has the focus; Tab to 削除する.
    tab_to(page, inspector(page).get_by_role("button", name="この要因を削除"))
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="要因を削除しますか？")
    expect(dialog.get_by_role("button", name="キャンセル")).to_be_focused()
    tab_to(page, dialog.get_by_role("button", name="削除する"))
    page.keyboard.press("Enter")
    expect(dialog).to_have_count(0)
    assert added not in e2e_server.node_ids(analysis_id)

    # 9. The export menu: open, its links, Esc back to the button.
    menu = page.locator(".edit-header [data-ui-menu-button]")
    tab_to(page, menu, backwards=True)
    page.keyboard.press("Enter")
    expect(menu).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Escape")
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(menu).to_be_focused()

    # 7. Search: the filter by keyboard, then クリア.
    tab_to(page, page.locator("#edit-filter-text"), backwards=True)
    page.keyboard.type("存在しない要因名")
    expect(page.locator("#edit-filter-count")).to_contain_text("一致 0件")
    tab_to(page, page.locator('[data-action="filter-clear"]'))
    page.keyboard.press("Enter")
    expect(page.locator("#edit-filter-text")).to_have_value("")

    # 11. While a generation runs, the keyboard gets round nothing: the
    #     restricted buttons are out of reach (disabled), 一覧へ by Enter stays.
    e2e_server.set_stub_mode("delay", delay_seconds=3)
    tab_to(page, step_button(page, 3))
    page.keyboard.press("Enter")
    tab_to(page, generate2)
    page.keyboard.press("Enter")
    wait_phase(page, "running")
    before = list(sent)
    leave = page.locator(".edit-header").get_by_role("link", name="一覧へ")
    tab_to(page, leave, backwards=True)
    page.keyboard.press("Enter")
    expect(page.locator("#analysisTitle")).to_be_visible()
    assert page.url.split("#")[0].endswith(f"/analyses/{analysis_id}")
    restricted = page.evaluate("""() => [...document.querySelectorAll(
        '[data-action="judgement"], [data-action="add"], [data-action="delete"], [data-action^="generate"], [data-factor-save]')]
        .filter((el) => el.offsetParent !== null && !el.disabled).map((el) => el.dataset.action || 'save')""")
    assert restricted == [], restricted
    wait_phase(page, "idle", timeout=30)
    during = [p for p in sent[len(before):] if not p.endswith("/generate/level/2")]
    assert not [p for p in during if p.endswith(("/update", "/delete", "/children")) or "/judgement" in p], during

    # 10. Leaving with an unsaved change: three choices, the safe one first.
    tab_to(page, factor_field(page, "memo"))
    page.keyboard.type("離れる前の下書き")
    tab_to(page, leave, backwards=True)
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name=LEAVE_DIALOG)
    expect(dialog.get_by_role("button", name="編集を続ける")).to_be_focused()
    tab_to(page, dialog.get_by_role("button", name="破棄して移動"))
    page.keyboard.press("Enter")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")


# ----- E-K02 ------------------------------------------------------------------------

def stays_inside(page, dialog, presses: int = 8) -> None:
    """Tab and Shift+Tab: the focus is inside the dialog or on the browser's
    own UI (activeElement null here), never on the page behind it."""
    handle = dialog.element_handle()
    for key in ("Tab", "Shift+Tab"):
        inside = 0
        for _ in range(presses):
            page.keyboard.press(key)
            where = page.evaluate("""(d) => { const el = document.activeElement;
              if (!el || el === document.body) return 'browser';
              return d.contains(el) ? 'dialog' : (el.id || el.tagName) }""", handle)
            assert where in ("dialog", "browser"), f"{key}：フォーカスがダイアログの外へ出た（{where}）"
            inside += where == "dialog"
        assert inside >= presses // 2, f"{key}：ダイアログの中に戻らない"


def build(server):
    analysis_id = server.create_analysis("ダイアログの確認", top_event="頂上")
    a = server.add_level1(analysis_id, "一次要因A")
    b = server.add_child(a, "二次要因B")
    c = server.add_child(b, "三次要因C")
    server.update_node(a, user_judgement="yes")
    return analysis_id, a, b, c


@pytest.mark.acceptance("E-K02")
@KEYBOARD_CASES
def test_E_K02_edit_dialogs_focus_tab_escape_and_return(page, e2e_server, display_case):
    analysis_id, a, b, c = build(e2e_server)
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)

    # Unsaved changes, switching the factor: 編集を続ける first; Esc keeps
    # the draft and gives the focus back to the row that was used.
    factor_field(page, "memo").fill("下書き")
    group = select_button(page, "group", a)
    tab_to(page, group)
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="保存していない変更があります")
    expect(dialog.get_by_role("button", name="編集を続ける")).to_be_focused()
    stays_inside(page, dialog)
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(group).to_be_focused()
    expect(factor_field(page, "memo")).to_have_value("下書き")

    # Leaving the page: the same, back to 一覧へ.
    leave = page.locator(".edit-header").get_by_role("link", name="一覧へ")
    tab_to(page, leave, backwards=True)
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name=LEAVE_DIALOG)
    expect(dialog.get_by_role("button", name="編集を続ける")).to_be_focused()
    stays_inside(page, dialog)
    page.keyboard.press("Escape")
    expect(leave).to_be_focused()

    # Delete: キャンセル first; Esc back to この要因を削除. Confirmed, the
    # button is gone with the factor: the focus goes to the nearest place,
    # never to the page's body.
    delete = inspector(page).get_by_role("button", name="この要因を削除")
    tab_to(page, delete)
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="要因を削除しますか？")
    expect(dialog.get_by_role("button", name="キャンセル")).to_be_focused()
    stays_inside(page, dialog)
    page.keyboard.press("Escape")
    expect(delete).to_be_focused()

    # Manual add: the title field first; Esc back to 手動追加.
    add = inspector(page).get_by_role("button", name="手動追加")
    tab_to(page, add)
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="要因を手動追加")
    expect(page.locator("#add-factor-title")).to_be_focused()
    stays_inside(page, dialog)
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(add).to_be_focused()

    # Saved first (保存して移動 is not what this checks), then deleted.
    factor_field(page, "memo").fill("")
    tab_to(page, delete)
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="要因を削除しますか？")
    tab_to(page, dialog.get_by_role("button", name="削除する"))
    page.keyboard.press("Enter")
    expect(dialog).to_have_count(0)
    expect(page.locator("[data-inspector-title]")).to_have_text("一次要因A")  # the parent is chosen
    assert page.evaluate(ACTIVE) is not None, "削除の後、フォーカスが本文（body）に落ちた"

    if display_case.width < 1280:
        # The folded navigation: Esc closes it, the focus is on its button;
        # a dialog opened from it gives the focus back inside it.
        toggle = page.locator("[data-nav-toggle]")
        tab_to(page, toggle, backwards=True)
        page.keyboard.press("Enter")
        expect(select_button(page, "nav", a)).to_be_focused()
        page.keyboard.press("Escape")
        expect(toggle).to_be_focused()
        expect(page.locator("#edit-nav")).to_be_hidden()
        factor_field(page, "memo").fill("ナビから切り替える前の下書き")
        tab_to(page, toggle, backwards=True)
        page.keyboard.press("Enter")
        tab_to(page, top_nav := page.locator('[data-action="select"][data-select="top"][data-role="nav"]'), backwards=True)
        page.keyboard.press("Enter")
        dialog = page.get_by_role("dialog", name="保存していない変更があります")
        expect(dialog.get_by_role("button", name="編集を続ける")).to_be_focused()
        page.keyboard.press("Escape")
        expect(top_nav).to_be_focused()
        expect(page.locator("#edit-nav")).to_be_visible()


@pytest.mark.acceptance("E-K02")
@KEYBOARD_CASES
def test_E_K02_list_and_new_dialogs(page, e2e_server, display_case):
    analysis_id = e2e_server.create_analysis("一覧のダイアログ", top_event="頂上")
    page.goto("/")
    row = page.locator(f'tr[data-analysis-id="{analysis_id}"]')
    delete = row.locator('[data-action="delete"]')
    tab_to(page, delete)
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="分析を削除しますか？")
    expect(dialog.get_by_role("button", name="キャンセル")).to_be_focused()
    stays_inside(page, dialog)
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(delete).to_be_focused()

    page.goto("/analyses/new")
    tab_to(page, page.locator("#title"))
    page.keyboard.type("入力あり")
    cancel = page.locator("[data-cancel-link]")
    tab_to(page, cancel)
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="作成していない入力があります")
    expect(dialog.get_by_role("button", name="入力を続ける")).to_be_focused()
    stays_inside(page, dialog)
    page.keyboard.press("Escape")
    expect(cancel).to_be_focused()
    expect(page.locator("#title")).to_have_value("入力あり")


# ----- E-K03 ------------------------------------------------------------------------

RECORD_LIVE = """
window.__live = [];
document.addEventListener('DOMContentLoaded', () => {
  for (const id of ['ui-live-status', 'ui-live-alert']) {
    const region = document.getElementById(id);
    if (!region) continue;
    new MutationObserver(() => {
      const text = region.textContent.trim();
      if (text) window.__live.push([id, text]);
    }).observe(region, { childList: true, characterData: true, subtree: true });
  }
});
"""


def live(page) -> list[tuple[str, str]]:
    return [tuple(entry) for entry in page.evaluate("window.__live")]


@pytest.mark.acceptance("E-K03")
def test_E_K03_generation_progress_results_and_failures_reach_the_live_regions(page, e2e_server, page_watch):
    page.add_init_script(RECORD_LIVE)
    analysis_id, a, b, c = build(e2e_server)
    second = e2e_server.add_level1(analysis_id, "一次要因E")
    e2e_server.update_node(second, user_judgement="yes")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    status = page.locator("#ui-live-status")
    alert = page.locator("#ui-live-alert")
    expect(status).to_have_attribute("role", "status")
    expect(status).to_have_attribute("aria-live", "polite")
    expect(alert).to_have_attribute("role", "alert")
    expect(alert).to_have_attribute("aria-live", "assertive")

    # A generation of two parents: its start, each parent's result, the summary.
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    wait_phase(page, "idle", timeout=30)
    page.wait_for_timeout(200)  # the regions are written 50 ms after a notification
    said = [text for region, text in live(page) if region == "ui-live-status"]
    start = [i for i, text in enumerate(said) if "開始しました" in text]
    parents = [i for i, text in enumerate(said) if text.startswith(("親「一次要因A」", "親「一次要因E」"))]
    summary = [i for i, text in enumerate(said) if "件作成しました" in text]
    assert start and len(parents) == 2 and summary, said
    assert start[0] < parents[0] < parents[1] < summary[-1], said

    # A failed generation (the stub raises) and a failed save: assertive.
    e2e_server.set_stub_mode("error")
    page_watch.allow_console_error(r"status of 500")
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    wait_phase(page, "idle", timeout=30)
    page.route(f"**/nodes/{b}/update", lambda route: route.fulfill(status=500, body="error"))
    factor_field(page, "memo").fill("保存に失敗する")
    inspector(page).locator("[data-factor-save]").click()
    expect(page.locator('#ui-toasts [data-toast-type="error"]').filter(has_text="要因を保存できませんでした")).to_be_visible()
    page.wait_for_timeout(200)
    alerts = [text for region, text in live(page) if region == "ui-live-alert"]
    assert any("作成できませんでした" in text or "失敗" in text for text in alerts), alerts
    assert any("要因を保存できませんでした" in text for text in alerts), alerts


# ----- the checks catch what they must ------------------------------------------------

@pytest.mark.acceptance("E-K02")
def test_the_focus_check_catches_a_dialog_that_is_not_modal(page, e2e_server):
    """A dialog opened with show() instead of showModal() lets Tab reach the
    page behind it: stays_inside() must fail."""
    page.add_init_script("HTMLDialogElement.prototype.showModal = function () { this.show(); };")
    analysis_id, a, b, c = build(e2e_server)
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    inspector(page).get_by_role("button", name="この要因を削除").click()
    dialog = page.get_by_role("dialog", name="要因を削除しますか？")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="キャンセル").focus()
    with pytest.raises(AssertionError, match="ダイアログの外へ出た"):
        stays_inside(page, dialog)


@pytest.mark.acceptance("E-K03")
def test_the_announcement_check_catches_a_missing_live_region(page, e2e_server):
    """Without #ui-live-status nothing of a generation is recorded: the
    check of E-K03 would fail (its list stays empty)."""
    page.add_init_script(RECORD_LIVE)
    page.add_init_script("document.addEventListener('DOMContentLoaded', () => "
                         "document.getElementById('ui-live-status')?.remove(), { capture: true });")
    analysis_id, a, b, c = build(e2e_server)
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    expect(page.locator("#ui-live-status")).to_have_count(0)
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    wait_phase(page, "idle", timeout=30)
    page.wait_for_timeout(200)
    assert [text for region, text in live(page) if region == "ui-live-status"] == []

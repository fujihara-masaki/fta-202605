"""E2E: items of the PR-3 manual check (docs/manual-check-pr3.md) that the
earlier tests did not check, added when the check in Google Chrome moved to
this automatic run with a few checks by eye (the user's decision of
2026-10-03; the mapping is in the guide, section 11).

* E-E19  section 5 with two real tabs of one browser: after the other tab
         changed a judgement, the first partial update is not applied (one
         「表示を最新にできませんでした」; the save itself is done) and the
         next one is. (test_edit_refresh.py changes it through the API.)
* E-E03  item 3: back to 未 from the inspector, counts and targets follow.
* E-E04  item 4: 「Noのみ」「未評価のみ」.
* E-E07  item 6: deleting a 一次要因 names it in the confirmation (PR-5: the
         in-page dialog with the number of descendants), selects the top
         event (①) and keeps what was typed in ①.
* E-E08  section 7: a 二次要因 of every inconsistent category refuses
         「AIで追加生成」 and 「手動追加」 with the reason, both shown (二次F, a
         parent in another analysis, included); a 三次要因 has neither.
* PR3-LAYOUT  item 7: at 1280x800 and 1440x900 the three panes are side by
         side and each scrolls on its own (the inspector with a long
         factor); the page does not.
* PR3-LEGACY-OPS  item 9: the generation of 二次 marks each parent
         (生成中… / +3件) while it runs, ends with 「合計6件の要因を生成しました」,
         and the marks go with the partial update (PR-3 interim; PR-6).
"""

from __future__ import annotations

import re
import time

import pytest

from tests.e2e.edit_helpers import (
    choose,
    chip,
    delete_dialog,
    factor_field,
    factor_save,
    factor_status,
    expect_selected,
    inspector,
    inspector_title,
    item,
    judgement_button,
    open_edit,
    select_button,
    step_button,
    step_panel,
    tab,
    toast,
    top_button,
    wait_until,
)
from tests.e2e.support import PageWatcher, expect
from tests.e2e.test_edit_integrity import PARENT_REASON_INCONSISTENT, build_every_category
from tests.e2e.test_edit_page import build_tree

pytestmark = pytest.mark.e2e

STALE = "表示を最新にできませんでした。ページを再読み込みしてください。"


def mark_page(page) -> None:
    page.evaluate("() => { window.__pr3NoReload = 'kept'; }")


def same_page(page) -> bool:
    return page.evaluate("() => window.__pr3NoReload === 'kept'")


def wait_for(page, check, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within the timeout")
        page.wait_for_timeout(50)


def scroll_top(page, name: str) -> int:
    return page.locator(f'[data-scroll="{name}"]').evaluate("(el) => el.scrollTop")


def set_scroll_top(page, name: str, value: int) -> int:
    return page.locator(f'[data-scroll="{name}"]').evaluate("(el, v) => { el.scrollTop = v; return el.scrollTop; }", value)


# ----- E-E19: section 5 with two tabs -------------------------------------------

@pytest.mark.acceptance("E-E19")
def test_E_E19_two_tabs_a_judgement_changed_in_the_other_tab(page, e2e_server):
    analysis_id = e2e_server.create_analysis("別のタブでの評価の変更", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    nav = page.locator("#edit-nav")

    # Tab A saves Yes for A.
    open_edit(page, analysis_id)
    judgement_button(item(page, "work", a), a, "yes").click()
    expect(toast(page, "評価を更新しました", "success", exact=True)).to_have_count(1)
    wait_until(lambda: e2e_server.judgement(a) == "yes")

    # Tab B (a new tab of the same browser, as with Ctrl+T) saves No for A.
    other = page.context.new_page()
    other_watch = PageWatcher(other, e2e_server.url)
    other.goto(f"/analyses/{analysis_id}")
    expect(other.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    judgement_button(item(other, "work", a), a, "no").click()
    expect(toast(other, "評価を更新しました", "success", exact=True)).to_have_count(1)
    wait_until(lambda: e2e_server.judgement(a) == "no")

    # Back in tab A, not reloaded: a save of B in the inspector (PR-5; the
    # detail dialog before). The partial update after it cannot tell tab B's
    # value from an old answer: not applied, one message, and the memo is
    # saved all the same (known issue).
    page.bring_to_front()
    mark_page(page)
    choose(page, b)
    factor_field(page, "memo").fill("別タブ確認1")
    factor_save(page).click()
    stale = toast(page, STALE, "error", exact=True)
    expect(stale).to_have_count(1)
    expect(chip(nav, a)).to_have_text("Yes")
    wait_until(lambda: e2e_server.get_node(b)["memo"] == "別タブ確認1")
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    expect(factor_field(page, "memo")).to_have_value("別タブ確認1")  # the saved value; the update did not roll it back

    # The next save: its update is applied and shows tab B's value; no new message.
    factor_field(page, "memo").fill("別タブ確認2")
    factor_save(page).click()
    expect(chip(nav, a)).to_have_text("No")
    expect(judgement_button(item(page, "work", a), a, "no")).to_have_attribute("aria-pressed", "true")
    expect(chip(page.locator("#edit-panel-tree"), a)).to_have_text("No")
    wait_until(lambda: e2e_server.get_node(b)["memo"] == "別タブ確認2")
    page.wait_for_timeout(300)
    expect(stale).to_have_count(1)
    assert same_page(page)
    assert not other_watch.problems(), other_watch.problems()


# ----- E-E03 / E-E04: items 3 and 4 ---------------------------------------------

@pytest.mark.acceptance("E-E03")
def test_E_E03_back_to_unknown_from_the_inspector(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)  # A Yes, D 未評価
    open_edit(page, analysis_id)
    select_button(page, "nav", d).click()
    judgement_button(inspector(page), d, "yes").click()
    expect(step_button(page, 2)).to_contain_text("2件・未評価0")
    expect(page.locator('[data-target-count="2"]')).to_have_text("2")
    wait_until(lambda: e2e_server.judgement(d) == "yes")

    judgement_button(inspector(page), d, "unknown").click()
    expect(judgement_button(inspector(page), d, "unknown")).to_have_attribute("aria-pressed", "true")
    expect(chip(page.locator("#edit-nav"), d)).to_have_text("未評価")
    for role in ("work", "tree", "table"):
        expect(item(page, role, d)).to_have_attribute("data-judgement", "unknown")
    expect(chip(page.locator("#edit-panel-tree"), d)).to_have_text("未評価")
    expect(step_button(page, 2)).to_contain_text("2件・未評価1")
    expect(page.locator('[data-target-count="2"]')).to_have_text("1")
    wait_until(lambda: e2e_server.judgement(d) == "unknown")


@pytest.mark.acceptance("E-E04")
def test_E_E04_no_and_unknown_filters(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)  # A Yes, B・C 未評価, D No
    e2e_server.update_node(d, user_judgement="no")
    open_edit(page, analysis_id)
    count = page.locator("#edit-filter-count")
    dim, match = re.compile(r"\bis-filter-dim\b"), re.compile(r"\bis-filter-match\b")

    page.select_option("#edit-filter-judgement", "no")
    expect(count).to_have_text("一致 1件（全4件）")
    expect(item(page, "work", d)).to_be_visible()
    expect(item(page, "work", a)).to_be_hidden()
    for role in ("nav", "tree"):
        expect(item(page, role, d)).to_have_class(match)
        expect(item(page, role, a)).to_have_class(dim)

    page.select_option("#edit-filter-judgement", "unknown")
    expect(count).to_have_text("一致 2件（全4件）")
    tab(page, "table").click()
    for node_id in (b, c):
        expect(item(page, "table", node_id)).to_be_visible()
    for node_id in (a, d):
        expect(item(page, "table", node_id)).to_be_hidden()
        expect(select_button(page, "nav", node_id)).to_be_visible()  # the navigation hides nothing
    tab(page, "work").click()
    step_button(page, 3).click()
    expect(page.locator('[data-target-count="2"]')).to_have_text("1")  # the hidden Yes parent A still counts

    page.get_by_role("button", name="クリア").click()
    expect(count).to_have_text("全4件")


# ----- E-E07: item 6 ---------------------------------------------------------------

@pytest.mark.acceptance("E-E07")
def test_E_E07_deleting_a_primary_factor_selects_the_top_event(page, e2e_server):
    analysis_id = e2e_server.create_analysis("一次要因の削除", top_event="頂上")
    e2e_server.add_level1(analysis_id, "一次要因A")
    d = e2e_server.add_level1(analysis_id, "手動確認で追加した要因")
    e2e_server.add_child(d, "その下の二次要因")
    open_edit(page, analysis_id)
    step_button(page, 1).click()
    page.fill("#topEventInput", "頂上（未保存の入力）")
    select_button(page, "nav", d).click()
    mark_page(page)
    messages: list[str] = []
    page.on("dialog", lambda dialog: (messages.append(dialog.message), dialog.accept()))

    inspector(page).get_by_role("button", name="この要因を削除").click()
    dialog = delete_dialog(page)
    expect(dialog.locator("[data-delete-title]")).to_have_text("手動確認で追加した要因")
    expect(dialog.locator("[data-delete-count]")).to_have_text("この要因の子孫 1件も一緒に削除されます（合計 2件）。")
    dialog.get_by_role("button", name="削除する").click()
    expect(toast(page, "要因「手動確認で追加した要因」を削除しました", "success", exact=True)).to_be_visible()
    assert messages == []  # no browser confirm() any more (PR-5)
    expect(inspector_title(page)).to_have_text("頂上事象")
    expect(top_button(page, "nav")).to_have_attribute("aria-current", "true")
    expect(step_button(page, 1)).to_have_attribute("aria-current", "step")
    expect(select_button(page, "nav", d)).to_have_count(0)
    expect(page.locator("#topEventInput")).to_have_value("頂上（未保存の入力）")
    assert e2e_server.node_count(analysis_id) == 1
    assert same_page(page)


# ----- E-E08: section 7 ---------------------------------------------------------------

@pytest.mark.acceptance("E-E08")
def test_E_E08_child_actions_are_refused_for_every_inconsistent_category(page, e2e_server):
    analysis_id, x, ids = build_every_category(e2e_server)
    open_edit(page, analysis_id)
    # 二次要因 of every category (三次要因 have no level below them).
    for key, title in (("M", "親不在の要因M"), ("F", "別分析を親にする要因F"), ("S", "自己参照の要因S"),
                       ("C1", "循環の要因C1"), ("C2", "循環の要因C2")):
        select_button(page, "nav", ids[key]).click()
        expect(inspector_title(page)).to_have_text(title)
        for name in ("AIで追加生成", "手動追加"):
            button = inspector(page).get_by_role("button", name=name, exact=True)
            expect(button).to_be_visible()
            expect(button).to_be_disabled()
        reason = inspector(page).locator("#inspector-children-reason")
        expect(reason).to_be_visible()
        expect(reason).to_have_text(PARENT_REASON_INCONSISTENT)
    for key, title in (("M2", "Mの下の要因M2"), ("L", "階層不一致の要因L"), ("K", "循環の下の要因K")):
        select_button(page, "nav", ids[key]).click()
        expect(inspector_title(page)).to_have_text(title)
        for name in ("AIで追加生成", "手動追加"):
            expect(inspector(page).get_by_role("button", name=name, exact=True)).to_have_count(0)

    select_button(page, "nav", ids["A"]).click()  # a consistent factor: both offered
    expect(inspector_title(page)).to_have_text("一次要因A")
    for name in ("AIで追加生成", "手動追加"):
        expect(inspector(page).get_by_role("button", name=name, exact=True)).to_be_enabled()


# ----- PR3-LAYOUT: item 7 ---------------------------------------------------------------

@pytest.mark.acceptance("PR3-LAYOUT")
def test_each_pane_scrolls_on_its_own(page, e2e_server, viewport):
    analysis_id = e2e_server.create_analysis("ペインのスクロール", top_event="頂上")
    long_text = "説明が長い要因の確認用の文です。" * 40
    first = e2e_server.add_level1(analysis_id, "一次要因01", long_text)
    e2e_server.update_node(first, memo=long_text, evidence=long_text, prevention_idea=long_text)
    for n in range(2, 41):
        e2e_server.add_level1(analysis_id, f"一次要因{n:02d}", f"一次要因{n:02d}の説明")
    open_edit(page, analysis_id)
    expect_selected(page, first, "一次要因01")
    expect(factor_field(page, "memo")).to_have_value(long_text)  # the details are in (PR-5: the editor)

    width = page.evaluate("() => document.documentElement.clientWidth")
    assert width == viewport["width"]
    assert page.evaluate("() => document.documentElement.scrollWidth") <= width
    nav, center, side = (page.locator(selector).bounding_box()
                         for selector in ("#edit-nav", "#edit-work-area", "#edit-inspector"))
    assert nav["x"] + nav["width"] <= center["x"] + 1 and center["x"] + center["width"] <= side["x"] + 1
    assert side["x"] + side["width"] <= width + 1

    panes = ("nav", "center", "inspector")
    for name in panes:
        assert page.locator(f'[data-scroll="{name}"]').evaluate("(el) => el.scrollHeight > el.clientHeight + 1"), name
    for name in panes:
        before = {other: scroll_top(page, other) for other in panes if other != name}
        assert set_scroll_top(page, name, 150) > 0, name
        assert {other: scroll_top(page, other) for other in before} == before, name
        assert page.evaluate("() => window.scrollY") == 0
    assert page.evaluate("() => document.documentElement.scrollHeight <= document.documentElement.clientHeight + 1")


# ----- PR3-LEGACY-OPS: item 9 -------------------------------------------------------------

@pytest.mark.acceptance("PR3-LEGACY-OPS")
def test_generation_marks_each_parent_until_the_partial_update(page, e2e_server):
    analysis_id = e2e_server.create_analysis("生成の件数の表示", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    for node_id in (a, b):
        e2e_server.update_node(node_id, user_judgement="yes")
    open_edit(page, analysis_id, f"#sel={a}&step=3&view=work")
    held, sent = [], []

    def hold_second(route):
        if route.request.method == "POST" and len(sent) == 1 and not held:
            held.append(route)  # B waits until released
            return
        sent.append(route.request.url)
        route.continue_()

    page.route(f"**/analyses/{analysis_id}/generate/level/2", hold_second)
    mark_page(page)

    def mark(node_id):
        return page.locator(f'[data-gen-host="{node_id}"] .gen-status-badge')

    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    expect(toast(page, "2件の親要因から順に生成中...", "success", exact=True)).to_be_visible()
    wait_for(page, lambda: bool(held))  # A is done, B is being generated
    expect(mark(a)).to_have_text("+3件")
    expect(mark(b)).to_have_text("生成中…")

    held[0].continue_()
    expect(toast(page, "合計6件の要因を生成しました", "success", exact=True)).to_be_visible()
    for parent_id in (a, b):
        expect(page.locator(f'[data-group-parent="{parent_id}"] [data-role="work-item"]')).to_have_count(3)
    expect(page.locator(".gen-status-badge")).to_have_count(0)  # replaced by the partial update (PR-3 interim)
    assert same_page(page)

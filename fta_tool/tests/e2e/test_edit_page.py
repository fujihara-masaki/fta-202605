"""E2E: analysis edit (B), PR-3 skeleton — plan 8.3, E-E01〜E-E06, E-E09.

Runs against the real app (stub AI provider, temporary database) in
Chromium at 1280x800 and 1440x900.

* E-E01  default display: without factors ① and the top event, with factors
         ② and the first consistent 一次要因.
* E-E02  every R-01 route selects (navigation, work row, parent name,
         tree, table, 要確認, breadcrumb, child link); all representations
         and the inspector agree; 要確認 shows the full quality warning.
* E-E03  judgement from the work list and the inspector: saved, reflected
         everywhere (tree included, C-04), step and target counts; failure
         leaves the page as it was and shows the reason; rapid clicks end
         on the last choice.
* E-E04  filter: hidden in the work list and the table, highlighted (never
         hidden) in the navigation and the tree (J-08); count; the targets
         of the normal generation do not change (J-07).
* E-E05  view tabs: arrow keys / Home / End, the selection is kept.
* E-E06  reload restores selection, step, tab, scroll and filter; an invalid
         hash gives the default display; without Web Storage it still works.
* E-E09  demo_points never shown; markup in factor texts stays text.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.e2e.edit_helpers import (
    chip,
    expect_selected,
    inspector,
    inspector_title,
    item,
    judgement_button,
    notifications,
    open_edit,
    panel,
    select_button,
    selected_ids,
    step_button,
    step_panel,
    tab,
    top_button,
    update_requests,
)
from tests.e2e.support import expect

pytestmark = pytest.mark.e2e

BLOCK_STORAGE = """
for (const name of ['localStorage', 'sessionStorage']) {
  Object.defineProperty(window, name, {
    configurable: true,
    get() { throw new DOMException('storage blocked for the test', 'SecurityError'); },
  });
}
"""


def build_tree(server, title="編集画面の確認"):
    """一次 A (Yes) → 二次 B (要確認) → 三次 C; 一次 D."""
    analysis_id = server.create_analysis(title, top_event="ログインできない")
    a = server.add_level1(analysis_id, "一次要因A", "ネットワーク機器の説明")
    b = server.add_child(a, "二次要因B", "DB接続の説明")
    c = server.add_child(b, "三次要因C")
    d = server.add_level1(analysis_id, "一次要因D")
    server.update_node(a, user_judgement="yes")
    server.set_warning(b, "既存要因「一次要因A」に類似; 要因名が長すぎる")
    return analysis_id, a, b, c, d


# ----- E-E01 ----------------------------------------------------------------

@pytest.mark.acceptance("E-E01")
def test_E_E01_without_factors_step_1_and_the_top_event(page, e2e_server):
    analysis_id = e2e_server.create_analysis("要因なし", top_event="頂上事象E01")
    open_edit(page, analysis_id)
    expect(step_button(page, 1)).to_have_attribute("aria-current", "step")
    expect(step_panel(page, 1)).to_be_visible()
    expect(step_panel(page, 2)).to_be_hidden()
    expect(page.locator("#topEventInput")).to_have_value("頂上事象E01")
    expect(top_button(page, "nav")).to_have_attribute("aria-current", "true")
    expect(inspector_title(page)).to_have_text("頂上事象")
    expect(inspector(page)).to_contain_text("頂上事象E01")
    expect(tab(page, "work")).to_have_attribute("aria-selected", "true")
    assert "#" not in page.url  # the default display leaves the URL alone

    # Only an inconsistent 一次要因: still ① (the default needs a consistent one).
    broken = e2e_server.create_analysis("不整合の一次だけ")
    e2e_server.insert_node(broken, 1, 99999, title="親のある一次")
    open_edit(page, broken)
    expect(step_button(page, 1)).to_have_attribute("aria-current", "step")
    expect(inspector_title(page)).to_have_text("頂上事象")


@pytest.mark.acceptance("E-E01")
def test_E_E01_with_factors_step_2_and_the_first_primary_factor(page, e2e_server):
    analysis_id = e2e_server.create_analysis("要因あり", top_event="頂上")
    first = e2e_server.add_level1(analysis_id, "最初の一次要因")
    e2e_server.add_level1(analysis_id, "二番目の一次要因")
    e2e_server.add_child(first, "二次要因")
    open_edit(page, analysis_id)
    expect(step_button(page, 2)).to_have_attribute("aria-current", "step")
    expect(step_panel(page, 2)).to_be_visible()
    expect(step_panel(page, 1)).to_be_hidden()
    expect_selected(page, first, "最初の一次要因")
    expect(step_button(page, 2)).to_contain_text("2件・未評価2")
    expect(step_button(page, 3)).to_contain_text("1件・未評価1")


# ----- E-E02 ----------------------------------------------------------------

@pytest.mark.acceptance("E-E02")
def test_E_E02_every_route_selects_and_all_views_agree(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)
    open_edit(page, analysis_id)

    # Structure navigation → the step follows the factor (④ for 三次).
    select_button(page, "nav", c).click()
    expect_selected(page, c, "三次要因C")
    expect(step_button(page, 4)).to_have_attribute("aria-current", "step")
    expect(item(page, "work", c)).to_be_visible()
    assert re.search(rf"#sel={c}&step=4&view=work$", page.url)

    # Parent name in the group heading of ④ → its parent (二次, step ③).
    select_button(page, "group", b).click()
    expect_selected(page, b, "二次要因B")
    expect(step_button(page, 3)).to_have_attribute("aria-current", "step")

    # Work row title.
    step_button(page, 2).click()
    select_button(page, "work", d).click()
    expect_selected(page, d, "一次要因D")

    # 要確認 in the work list → the full warning in the inspector.
    step_button(page, 3).click()
    page.locator(f'[data-role="work-warning"][data-node-id="{b}"]').click()
    expect_selected(page, b, "二次要因B")
    warning = page.locator("[data-inspector-warning] [data-warning-text]")
    expect(warning).to_have_text("既存要因「一次要因A」に類似; 要因名が長すぎる")
    expect(page.locator("[data-inspector-warning] h4")).to_be_focused()

    # Tree.
    tab(page, "tree").click()
    select_button(page, "tree", a).click()
    expect_selected(page, a, "一次要因A")
    expect(panel(page, "tree")).to_be_visible()

    # Table.
    tab(page, "table").click()
    select_button(page, "table", c).click()
    expect_selected(page, c, "三次要因C")

    # Breadcrumb: 頂上事象 › 一次要因A › 二次要因B › 三次要因C.
    crumbs = page.locator(".edit-crumbs li")
    expect(crumbs).to_have_text(["頂上事象", "一次要因A", "二次要因B", "三次要因C"])
    page.locator(f'[data-role="crumb"][data-node-id="{a}"]').click()
    expect_selected(page, a, "一次要因A")

    # Child link in the inspector.
    page.locator(f'[data-role="child"][data-node-id="{b}"]').click()
    expect_selected(page, b, "二次要因B")

    # The top event from the breadcrumb, and back from the navigation.
    page.locator('[data-role="crumb"][data-select="top"]').click()
    expect(inspector_title(page)).to_have_text("頂上事象")
    assert selected_ids(page) == {"top"}
    expect(step_button(page, 1)).to_have_attribute("aria-current", "step")


@pytest.mark.acceptance("E-E02")
def test_E_E02_the_inspector_shows_the_saved_details_of_the_latest_choice(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)
    e2e_server.update_node(a, memo="Aのメモ", evidence="Aの根拠", direct_cause_status="likely")
    open_edit(page, analysis_id)
    expect_selected(page, a, "一次要因A")
    details = page.locator("[data-details]")
    expect(details.locator('[data-detail="memo"]')).to_have_text("Aのメモ")
    expect(details.locator('[data-detail="evidence"]')).to_have_text("Aの根拠")
    expect(details.locator('[data-detail="direct_cause_status"]')).to_have_text("直接要因の可能性が高い")
    expect(page.locator(".edit-inspector__tags")).to_contain_text("直接要因評価：可能性高")
    expect(page.locator(".edit-inspector__tags")).to_contain_text("メモあり")

    # A slow answer for an earlier choice never fills the later one.
    held = []
    page.route(f"**/nodes/{c}", lambda route: held.append(route))
    select_button(page, "nav", c).click()
    expect(inspector_title(page)).to_have_text("三次要因C")
    expect(page.locator("[data-detail-status]")).to_contain_text("読み込んでいます")
    expect(details.locator('[data-detail="memo"]')).to_have_text("")  # nothing of A left behind
    select_button(page, "nav", d).click()
    expect(inspector_title(page)).to_have_text("一次要因D")
    expect(page.locator("[data-detail-status]")).to_have_text("保存されている内容です。")
    held[0].fulfill(json={
        "id": c, "analysis_id": analysis_id, "parent_id": b, "level": 3, "title": "三次要因C",
        "description": "", "memo": "古い応答のメモ", "user_judgement": "unknown", "direct_cause_status": "unknown",
        "direct_cause_comment": "", "evidence": "", "prevention_idea": "", "warning_flags": "", "ai_generated": False,
    })
    page.wait_for_timeout(300)
    expect(inspector_title(page)).to_have_text("一次要因D")
    expect(page.locator('[data-details] [data-detail="memo"]')).not_to_have_text("古い応答のメモ")


# ----- E-E03 ----------------------------------------------------------------

@pytest.mark.acceptance("E-E03")
def test_E_E03_judgement_is_saved_and_shown_everywhere(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)
    open_edit(page, analysis_id)
    expect(step_button(page, 2)).to_contain_text("2件・未評価1")
    expect(page.locator('[data-target-count="2"]')).to_have_text("1")

    judgement_button(item(page, "work", d), d, "yes").click()
    expect(chip(page.locator("#edit-nav"), d)).to_have_text("Yes")
    assert e2e_server.judgement(d) == "yes"
    for role in ("tree", "table", "work"):
        expect(item(page, role, d)).to_have_attribute("data-judgement", "yes")
    expect(chip(page.locator("#edit-panel-tree"), d)).to_have_text("Yes")  # the tree follows (C-04)
    expect(chip(page.locator("#edit-panel-table"), d)).to_have_text("Yes")
    expect(judgement_button(item(page, "work", d), d, "yes")).to_have_attribute("aria-pressed", "true")
    expect(step_button(page, 2)).to_contain_text("2件・未評価0")
    expect(page.locator('[data-target-count="2"]')).to_have_text("2")
    expect(notifications(page).filter(has_text="評価を更新しました")).to_have_count(1)

    # From the inspector: the parent group heading, the work list and the
    # targets of the next level follow.
    select_button(page, "nav", b).click()
    expect(page.locator('[data-target-count="3"]')).to_have_text("0")
    judgement_button(inspector(page), b, "yes").click()
    expect(item(page, "group", b)).to_have_attribute("data-judgement", "yes")
    expect(chip(page.locator(f'[data-role="group-item"][data-node-id="{b}"]'), b)).to_have_text("Yes")
    expect(judgement_button(item(page, "work", b), b, "yes")).to_have_attribute("aria-pressed", "true")
    expect(page.locator('[data-target-count="3"]')).to_have_text("1")
    judgement_button(inspector(page), b, "no").click()
    expect(item(page, "group", b)).to_have_attribute("data-judgement", "no")
    expect(page.locator('[data-target-count="3"]')).to_have_text("0")
    assert e2e_server.judgement(b) == "no"


@pytest.mark.acceptance("E-E03")
def test_E_E03_failure_leaves_the_judgement_and_rapid_clicks_end_on_the_last(page, page_watch, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)
    open_edit(page, analysis_id)
    row = item(page, "work", a)

    page_watch.allow_console_error("500")
    page.route(f"**/nodes/{a}/update", lambda route: route.fulfill(status=500, json={"detail": "E2E: 評価を保存できない状態"}))
    judgement_button(row, a, "no").click()
    error = notifications(page).filter(has_text="E2E: 評価を保存できない状態")
    expect(error).to_have_count(1)
    expect(judgement_button(row, a, "yes")).to_have_attribute("aria-pressed", "true")
    expect(chip(page.locator("#edit-nav"), a)).to_have_text("Yes")
    assert e2e_server.judgement(a) == "yes"
    page.wait_for_timeout(3500)
    expect(error).to_have_count(1)  # errors stay until closed (J-24)
    page.unroute(f"**/nodes/{a}/update")

    # Rapid clicks while the first request is in flight: the last one wins
    # and the choice in between is never sent.
    held = []
    page.route(f"**/nodes/{a}/update", lambda route: route.continue_() if held else held.append(route))
    sent = update_requests(page, a)
    judgement_button(row, a, "no").click()
    judgement_button(row, a, "unknown").click()
    judgement_button(row, a, "yes").click()
    judgement_button(row, a, "no").click()
    expect(judgement_button(row, a, "yes")).to_have_attribute("aria-pressed", "true")  # nothing confirmed yet
    held[0].continue_()
    expect(judgement_button(row, a, "no")).to_have_attribute("aria-pressed", "true")
    page.wait_for_timeout(500)
    assert e2e_server.judgement(a) == "no"
    assert [json.loads(r.post_data)["user_judgement"] for r in sent] == ["no"]
    expect(chip(page.locator("#edit-panel-tree"), a)).to_have_text("No")


# ----- E-E04 ----------------------------------------------------------------

@pytest.mark.acceptance("E-E04")
def test_E_E04_filter_hides_rows_highlights_the_tree_and_keeps_the_targets(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)
    open_edit(page, analysis_id)
    step_button(page, 3).click()
    expect(page.locator('[data-target-count="2"]')).to_have_text("1")  # Yes 一次要因A
    count = page.locator("#edit-filter-count")
    expect(count).to_have_text("全4件")

    page.fill("#edit-filter-text", "DB接続")  # description of 二次要因B
    expect(count).to_have_text("一致 1件（全4件）")
    expect(item(page, "work", b)).to_be_visible()
    tab(page, "table").click()
    expect(item(page, "table", b)).to_be_visible()
    for node_id in (a, c, d):
        expect(item(page, "table", node_id)).to_be_hidden()
    # Navigation and tree: never hidden, matches highlighted (J-08).
    for role in ("nav", "tree"):
        expect(item(page, role, b)).to_have_class(re.compile(r"\bis-filter-match\b"))
        for node_id in (a, c, d):
            expect(item(page, role, node_id)).to_have_class(re.compile(r"\bis-filter-dim\b"))
    for node_id in (a, b, c, d):
        expect(select_button(page, "nav", node_id)).to_be_visible()
    # The Yes parent is hidden by the filter but still a target (J-07).
    tab(page, "work").click()
    step_button(page, 3).click()
    expect(page.locator('[data-target-count="2"]')).to_have_text("1")
    step_button(page, 2).click()
    expect(item(page, "work", a)).to_be_hidden()

    page.fill("#edit-filter-text", "")
    page.select_option("#edit-filter-judgement", "warning")
    expect(count).to_have_text("一致 1件（全4件）")
    expect(item(page, "nav", b)).to_have_class(re.compile(r"\bis-filter-match\b"))
    page.select_option("#edit-filter-judgement", "yes")
    expect(count).to_have_text("一致 1件（全4件）")
    expect(item(page, "work", a)).to_be_visible()
    expect(item(page, "work", d)).to_be_hidden()

    page.get_by_role("button", name="クリア").click()
    expect(count).to_have_text("全4件")
    expect(item(page, "work", d)).to_be_visible()
    expect(item(page, "nav", d)).not_to_have_class(re.compile(r"is-filter"))


# ----- E-E05 ----------------------------------------------------------------

@pytest.mark.acceptance("E-E05")
def test_E_E05_tabs_by_keyboard_keep_the_selection(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)
    open_edit(page, analysis_id)
    select_button(page, "nav", b).click()
    expect(page.get_by_role("tablist", name="表示の切り替え").get_by_role("tab")).to_have_text(["作業", "ツリー", "一覧表"])

    tab(page, "work").focus()
    page.keyboard.press("ArrowRight")
    expect(tab(page, "tree")).to_be_focused()
    expect(tab(page, "tree")).to_have_attribute("aria-selected", "true")
    expect(panel(page, "tree")).to_be_visible()
    expect(panel(page, "work")).to_be_hidden()
    page.keyboard.press("ArrowRight")
    expect(tab(page, "table")).to_have_attribute("aria-selected", "true")
    page.keyboard.press("ArrowRight")
    expect(tab(page, "work")).to_have_attribute("aria-selected", "true")
    page.keyboard.press("ArrowLeft")
    expect(tab(page, "table")).to_be_focused()
    page.keyboard.press("Home")
    expect(tab(page, "work")).to_be_focused()
    page.keyboard.press("End")
    expect(tab(page, "table")).to_be_focused()
    expect(tab(page, "tree")).to_have_attribute("tabindex", "-1")
    expect(tab(page, "table")).to_have_attribute("tabindex", "0")

    # The selection stays through the switches.
    expect_selected(page, b, "二次要因B")
    expect(item(page, "table", b)).to_have_class(re.compile(r"\bis-selected\b"))
    assert page.url.endswith("view=table")


# ----- E-E06 ----------------------------------------------------------------

@pytest.mark.acceptance("E-E06")
def test_E_E06_reload_restores_selection_step_tab_scroll_and_filter(page, e2e_server):
    analysis_id = e2e_server.create_analysis("復元の確認", top_event="頂上")
    ids = [e2e_server.add_level1(analysis_id, f"一次要因{n:02d}") for n in range(40)]
    target = ids[30]
    open_edit(page, analysis_id)
    select_button(page, "nav", target).click()
    page.fill("#edit-filter-text", "一次要因3")
    tab(page, "tree").click()  # the tree only highlights, so it keeps its height
    nav_scroll = page.locator('[data-scroll="nav"]')
    center = page.locator('[data-scroll="center"]')
    nav_scroll.evaluate("el => { el.scrollTop = 300; }")
    center.evaluate("el => { el.scrollTop = 250; }")

    page.reload()
    expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    expect_selected(page, target, "一次要因30")
    expect(tab(page, "tree")).to_have_attribute("aria-selected", "true")
    expect(step_button(page, 2)).to_have_attribute("aria-current", "step")
    expect(page.locator("#edit-filter-text")).to_have_value("一次要因3")
    expect(page.locator("#edit-filter-count")).to_have_text("一致 10件（全40件）")
    assert abs(nav_scroll.evaluate("el => el.scrollTop") - 300) <= 2
    assert abs(center.evaluate("el => el.scrollTop") - 250) <= 2


@pytest.mark.acceptance("E-E06")
def test_E_E06_invalid_hash_gives_the_default_display(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)
    open_edit(page, analysis_id, "#sel=99999&step=9&view=bogus")
    expect_selected(page, a, "一次要因A")
    expect(step_button(page, 2)).to_have_attribute("aria-current", "step")
    expect(tab(page, "work")).to_have_attribute("aria-selected", "true")

    open_edit(page, analysis_id, f"#sel={c}&step=0&view=nothing")
    expect_selected(page, c, "三次要因C")
    expect(step_button(page, 4)).to_have_attribute("aria-current", "step")
    expect(tab(page, "work")).to_have_attribute("aria-selected", "true")

    open_edit(page, analysis_id, "#sel=12abc&step=2&view=tree")
    expect_selected(page, a, "一次要因A")


@pytest.mark.acceptance("E-E06")
def test_E_E06_without_web_storage_the_screen_still_works(page, e2e_server):
    analysis_id, a, b, c, d = build_tree(e2e_server)
    page.add_init_script(BLOCK_STORAGE)
    open_edit(page, analysis_id)
    assert page.evaluate("() => { try { window.sessionStorage; return 'available'; } catch { return 'blocked'; } }") == "blocked"
    judgement_button(item(page, "work", a), a, "no").click()
    expect(chip(page.locator("#edit-nav"), a)).to_have_text("No")
    select_button(page, "nav", c).click()
    tab(page, "tree").click()
    page.fill("#edit-filter-text", "二次")
    expect(page.locator("#edit-filter-count")).to_have_text("一致 1件（全4件）")

    page.reload()
    expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    expect_selected(page, c, "三次要因C")  # from the hash
    expect(tab(page, "tree")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#edit-filter-text")).to_have_value("")  # not kept without storage


# ----- E-E09 ----------------------------------------------------------------

@pytest.mark.acceptance("E-E09")
def test_E_E09_demo_points_hidden_and_markup_stays_text(page, e2e_server):
    analysis_id = e2e_server.create_analysis(
        "表示の安全性", top_event="頂上<b>太字</b>", system_context="構成の説明", incident_context="状況の説明",
        demo_points="デモ観点XYZ-非表示")
    markup = '<img src=x onerror="window.__xss=1">'
    script = "<script>window.__xss=2</script>"
    a = e2e_server.add_level1(analysis_id, f"一次{markup}", f"説明{script}")
    b = e2e_server.add_child(a, f"二次{script}")
    e2e_server.set_warning(b, f"警告{markup}")
    e2e_server.update_node(a, memo=f"メモ{script}")
    broken = e2e_server.insert_node(analysis_id, 2, 99999, title=f"不整合{markup}")

    open_edit(page, analysis_id)
    assert page.evaluate("window.__xss") is None
    assert "デモ観点XYZ" not in page.content()
    embedded = json.dumps(json.loads(page.locator("#analysis-data").text_content()), ensure_ascii=False)
    assert "デモ観点XYZ" not in embedded
    assert "メモ<script>" not in embedded  # only whether there is a memo, never its text

    expect(select_button(page, "nav", a)).to_contain_text(f"一次{markup}")
    expect(select_button(page, "work", a)).to_have_text(f"一次{markup}")
    expect(item(page, "work", a).locator(".edit-row__desc")).to_have_text(f"説明{script}")
    expect(select_button(page, "tree", b)).to_have_text(f"二次{script}")
    expect(select_button(page, "table", broken)).to_have_text(f"不整合{markup}")
    expect(page.locator("#edit-nav")).to_contain_text("頂上<b>太字</b>")
    expect(inspector_title(page)).to_have_text(f"一次{markup}")
    expect(page.locator('[data-details] [data-detail="memo"]')).to_have_text(f"メモ{script}")
    expect(page.locator(f'[data-role="child"][data-node-id="{b}"]')).to_have_text(f"二次{script}")
    page.locator(f'[data-role="child"][data-node-id="{b}"]').click()
    expect(page.locator("[data-warning-text]")).to_have_text(f"警告{markup}")
    expect(page.locator(".edit-crumbs li").nth(1)).to_have_text(f"一次{markup}")
    assert page.evaluate("window.__xss") is None
    assert page.locator("#edit-inspector img, .edit-page img, script:not([src]):not([type])").count() == 0

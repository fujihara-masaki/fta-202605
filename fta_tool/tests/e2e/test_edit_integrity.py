"""E2E: inconsistent parent links on the edit screen (PR-3) — plan 5.9.5,
J-25, the user's decisions of 2026-09-29 (判断2・判断3); E-E08,
PR3-DELETE-SCOPE and PR3-GEN-PARENTS.

The inconsistent data is written straight into the E2E server's temporary
database (tests/e2e/support.py insert_node / set_parent); the user's
database is never used. Faults of the checks (the lookups fail, the
deletion walk cannot be completed) are injected through stub_control.json
(tests/e2e/stub_server.py); the data itself is never changed for that.

* E-E08  every category is shown in the group 「親子関係に不整合がある要因」
         (navigation, work list, tree, table), never as the top event; the
         page opens although the data loops; the inspector names the
         category; deletion and child actions are offered as decided.
* PR3-DELETE-SCOPE  a factor of another analysis directly or further below
         blocks the factor and every ancestor (consistent ones included);
         a walk that cannot be completed, or lookups that fail, block
         deletion; when blocked, no delete request is sent — neither from
         the button nor from app.js's deleteNode called directly; a missing
         parent / 「上位に不整合あり」 factor is deleted with exactly its
         subtree.
* PR3-GEN-PARENTS  the normal generation of 二次・三次 sends one request per
         consistent Yes parent (hidden by the filter or not), each naming its
         parent, never one for an inconsistent parent; with none left
         nothing is sent; the counts of targets and exclusions are shown;
         additional generation and manual add below an inconsistent parent
         are refused before a request (buttons and direct calls), and never
         sent without a parent; below a consistent parent they work whatever
         its judgement.

Generation requests are never made for factors on a parent-link loop: the
existing generation API has no loop detection (recorded in the plan), so
the generation tests use inconsistent parents that are not on a loop.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import pytest

from tests.e2e.edit_helpers import (
    inspector,
    inspector_title,
    item,
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

REASON_NOT_VERIFIED = "安全に削除できるか確認できていないため、この画面では削除できません。"
REASON_LOOKUP_FAILED = "削除される範囲を確認するための情報を取得できなかったため、この画面では削除できません。"
REASON_SCOPE_INCOMPLETE = "削除される範囲をすべて確認できなかったため、この画面では削除できません。"
REASON_FOREIGN_DESCENDANT = ("この要因の子孫に別の分析の要因が含まれるため、この画面では削除できません"
                             "（削除すると別の分析の要因も削除されます）。")
PARENT_REASON_INCONSISTENT = "親子関係に不整合があるため、この要因の下には要因を追加・生成できません。"
DELETE_ALLOWED_TEXT = "子孫の要因もすべて削除されます。この操作は取り消せません。"
MISSING = 999999  # a parent id that no factor has


# ----- helpers ----------------------------------------------------------------

def posts(page, pattern: str) -> list[str]:
    """POST requests whose path matches `pattern`, as the page sends them."""
    seen: list[str] = []
    regex = re.compile(pattern)
    page.on("request", lambda r: seen.append(urlparse(r.url).path)
            if r.method == "POST" and regex.search(urlparse(r.url).path) else None)
    return seen


def delete_button(page):
    return inspector(page).get_by_role("button", name="この要因を削除")


def delete_reason(page):
    return inspector(page).locator("[data-delete-reason]")


def select(page, node_id: int, title: str) -> None:
    select_button(page, "nav", node_id).click()
    expect(inspector_title(page)).to_have_text(title)


def expect_delete_blocked(page, node_id: int, title: str, reason: str) -> None:
    select(page, node_id, title)
    expect(delete_button(page)).to_be_disabled()
    expect(delete_reason(page)).to_have_text(reason)


def call_delete(page, node_id: int, analysis_id: int) -> None:
    """app.js's deleteNode called directly, as a stale button or another
    route would."""
    page.evaluate("([id, aid]) => deleteNode(id, aid)", [node_id, analysis_id])


# ----- E-E08 --------------------------------------------------------------------

def build_every_category(server):
    """Every category of plan 5.9.5 in one analysis."""
    other = server.create_analysis("別の分析", top_event="別の頂上事象")
    x = server.insert_node(other, 1, title="別の分析の一次要因X")
    analysis_id = server.create_analysis("不整合の確認", top_event="頂上E08")
    ids = {"A": server.insert_node(analysis_id, 1, title="一次要因A", judgement="yes")}
    ids["M"] = server.insert_node(analysis_id, 2, MISSING, title="親不在の要因M")
    ids["M2"] = server.insert_node(analysis_id, 3, ids["M"], title="Mの下の要因M2")
    ids["F"] = server.insert_node(analysis_id, 2, x, title="別分析を親にする要因F")
    ids["S"] = server.insert_node(analysis_id, 2, title="自己参照の要因S")
    server.set_parent(ids["S"], ids["S"])
    ids["C1"] = server.insert_node(analysis_id, 2, title="循環の要因C1")
    ids["C2"] = server.insert_node(analysis_id, 2, ids["C1"], title="循環の要因C2")
    server.set_parent(ids["C1"], ids["C2"])
    ids["L"] = server.insert_node(analysis_id, 3, ids["A"], title="階層不一致の要因L")
    ids["K"] = server.insert_node(analysis_id, 3, ids["C1"], title="循環の下の要因K")
    return analysis_id, x, ids


@pytest.mark.acceptance("E-E08")
def test_E_E08_every_category_is_named_in_its_group(page, e2e_server):
    analysis_id, x, ids = build_every_category(e2e_server)
    labels = {
        "M": ("missing_parent", f"（親が見つかりません：ID {MISSING}）"),
        "M2": ("upper", "上位に不整合あり"),
        "F": ("foreign_parent", f"（別の分析の要因を親にしています：ID {x}）"),
        "S": ("self_parent", "（自分自身を親にしています）"),
        "C1": ("cycle", "（親子関係が循環しています）"),
        "C2": ("cycle", "（親子関係が循環しています）"),
        "L": ("level_mismatch", "（階層が合いません：親は一次）"),
        "K": ("upper", "上位に不整合あり"),
    }
    open_edit(page, analysis_id)  # the page opens although the links loop

    top = page.locator("#edit-nav .edit-outline__item--top")
    expect(top.locator('[data-select="top"]')).to_contain_text("頂上E08")
    expect(top.locator(f'[data-role="nav-item"][data-node-id="{ids["A"]}"]')).to_have_count(1)
    for view in ("nav", "tree"):
        group = page.locator(f".edit-anomalies--{view}")
        expect(group.locator(".edit-anomalies__title")).to_have_text("親子関係に不整合がある要因（8件）")
        for key, (kind, text) in labels.items():
            entry = group.locator(f'[data-role="{view}-item"][data-node-id="{ids[key]}"]')
            expect(entry).to_have_count(1)
            expect(entry.first).to_contain_text(text)
            if kind != "upper":
                expect(entry).to_have_attribute("data-kind", kind)
    for key in labels:  # never below the top event
        expect(page.locator(f'.edit-outline__item--top [data-node-id="{ids[key]}"]')).to_have_count(0)

    # Work list: the group at the end of ②〜④.
    anomalies = page.locator("[data-work-anomalies]")
    expect(anomalies).to_be_visible()
    expect(anomalies.locator('[data-role="work-item"]')).to_have_count(8)
    expect(item(page, "work", ids["M"]).locator(".ui-tag--issue")).to_have_text(labels["M"][1])
    step_button(page, 5).click()
    expect(anomalies).to_be_hidden()

    # Table: the parent column names the problem, never 「（頂上事象）」.
    tab(page, "table").click()
    for key in ("M", "F", "S", "C1", "L"):
        expect(page.locator(f'[data-role="table-item"][data-node-id="{ids[key]}"] .edit-table__parent')).to_have_text(labels[key][1])
    expect(page.locator(f'[data-role="table-item"][data-node-id="{ids["M2"]}"] .edit-table__parent')).to_have_text("親不在の要因M 上位に不整合あり")

    # Inspector: the category, the breadcrumb, deletion and child actions.
    select(page, ids["M"], "親不在の要因M")
    notice = inspector(page).locator("[data-integrity-notice]")
    expect(notice).to_contain_text(labels["M"][1])
    expect(inspector(page).locator(".edit-crumbs li").first).to_have_text("親子関係に不整合がある要因")
    expect(delete_button(page)).to_be_enabled()
    expect(delete_reason(page)).to_have_text(DELETE_ALLOWED_TEXT)
    for name in ("AIで追加生成", "手動追加"):
        expect(inspector(page).get_by_role("button", name=name, exact=True)).to_be_disabled()
    expect(inspector(page).locator("#inspector-children-reason")).to_have_text(PARENT_REASON_INCONSISTENT)

    select(page, ids["M2"], "Mの下の要因M2")
    expect(inspector(page).locator("[data-integrity-notice]")).to_contain_text("親不在の要因M")
    expect(delete_button(page)).to_be_enabled()
    for key, title in (("F", "別分析を親にする要因F"), ("S", "自己参照の要因S"), ("C1", "循環の要因C1"),
                       ("C2", "循環の要因C2"), ("L", "階層不一致の要因L")):
        expect_delete_blocked(page, ids[key], title, REASON_NOT_VERIFIED)
        expect(inspector(page).locator("[data-integrity-notice]")).to_contain_text(labels[key][1])
    select(page, ids["K"], "循環の下の要因K")
    expect(delete_button(page)).to_be_enabled()

    # The consistent 一次要因 A is still the parent of the normal generation.
    step_button(page, 3).click()
    expect(page.locator('[data-target-count="2"]')).to_have_text("1")
    expect(page.locator('[data-target-excluded="2"]')).to_be_hidden()


# ----- PR3-DELETE-SCOPE ------------------------------------------------------------

@pytest.mark.acceptance("PR3-DELETE-SCOPE")
def test_other_analysis_below_blocks_the_factor_and_every_ancestor(page, e2e_server):
    other = e2e_server.create_analysis("別の分析", top_event="別")
    analysis_id = e2e_server.create_analysis("削除範囲の確認", top_event="頂上")
    p = e2e_server.insert_node(analysis_id, 1, title="一次要因P")
    q = e2e_server.insert_node(analysis_id, 2, p, title="二次要因Q")
    foreign_q = e2e_server.insert_node(other, 3, q, title="Qの下にある別分析の要因")    # directly below Q
    r = e2e_server.insert_node(analysis_id, 1, title="一次要因R")
    r2 = e2e_server.insert_node(analysis_id, 2, r, title="二次要因R2")
    r3 = e2e_server.insert_node(analysis_id, 3, r2, title="三次要因R3")
    foreign_r = e2e_server.insert_node(other, 1, r3, title="R3の下にある別分析の要因")  # below the display depth of R
    safe = e2e_server.insert_node(analysis_id, 1, title="一次要因S")
    safe_child = e2e_server.insert_node(analysis_id, 2, safe, title="二次要因S2")
    open_edit(page, analysis_id)
    deletes = posts(page, r"^/nodes/\d+/delete$")
    dialogs = record_dialogs(page, action="accept")
    before = e2e_server.node_ids()

    # Consistent factors, blocked all the same: the direct parent, the
    # ancestors, and the ancestors of a factor of another analysis further down.
    for node_id, title in ((q, "二次要因Q"), (p, "一次要因P"), (r3, "三次要因R3"),
                           (r2, "二次要因R2"), (r, "一次要因R")):
        expect_delete_blocked(page, node_id, title, REASON_FOREIGN_DESCENDANT)
        expect(inspector(page).locator("[data-integrity-notice]")).to_have_count(0)  # its own link is fine
        delete_button(page).click(force=True)  # a disabled button does nothing
        call_delete(page, node_id, analysis_id)
        expect(toast(page, REASON_FOREIGN_DESCENDANT, "error")).to_be_visible()
    page.wait_for_timeout(300)
    assert deletes == [] and dialogs == []
    assert e2e_server.node_ids() == before
    assert {foreign_q, foreign_r} <= e2e_server.node_ids(other)

    # A factor with nothing of another analysis below: deleted with its subtree.
    select(page, safe, "一次要因S")
    expect(delete_button(page)).to_be_enabled()
    delete_button(page).click()
    expect(select_button(page, "nav", safe)).to_have_count(0)
    wait_until(lambda: safe not in e2e_server.node_ids())
    assert before - e2e_server.node_ids() == {safe, safe_child}
    assert dialogs == ["confirm"] and len(deletes) == 1


@pytest.mark.acceptance("PR3-DELETE-SCOPE")
def test_a_walk_that_cannot_be_completed_blocks_deletion(page, e2e_server):
    e2e_server.set_control(integrity_scope_limit=2)
    analysis_id = e2e_server.create_analysis("走査を完了できない", top_event="頂上")
    p1 = e2e_server.add_level1(analysis_id, "一次要因P1")
    p2 = e2e_server.add_child(p1, "二次要因P2")
    e2e_server.add_child(p2, "三次要因P3")
    open_edit(page, analysis_id)
    deletes = posts(page, r"^/nodes/\d+/delete$")
    dialogs = record_dialogs(page, action="accept")
    before = e2e_server.node_ids()

    expect_delete_blocked(page, p1, "一次要因P1", REASON_SCOPE_INCOMPLETE)  # three factors, the walk stops at two
    call_delete(page, p1, analysis_id)
    expect(toast(page, REASON_SCOPE_INCOMPLETE, "error")).to_be_visible()
    page.wait_for_timeout(300)
    assert deletes == [] and dialogs == [] and e2e_server.node_ids() == before

    select(page, p2, "二次要因P2")  # two factors: the walk completes
    expect(delete_button(page)).to_be_enabled()


@pytest.mark.acceptance("PR3-DELETE-SCOPE")
def test_failed_lookups_block_every_deletion_and_the_page_still_opens(page, e2e_server):
    e2e_server.set_control(integrity="lookup_error")
    analysis_id = e2e_server.create_analysis("確認用の情報を取得できない", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_child(a, "二次要因B")
    m = e2e_server.insert_node(analysis_id, 2, MISSING, title="親を確認できない要因M")
    open_edit(page, analysis_id)
    deletes = posts(page, r"^/nodes/\d+/delete$")
    dialogs = record_dialogs(page, action="accept")
    before = e2e_server.node_ids()

    expect(page.locator(f'.edit-anomalies--nav [data-role="nav-item"][data-node-id="{m}"]')).to_contain_text(
        f"（親を確認できませんでした：ID {MISSING}）")
    for node_id, title in ((a, "一次要因A"), (b, "二次要因B"), (m, "親を確認できない要因M")):
        expect_delete_blocked(page, node_id, title, REASON_LOOKUP_FAILED)
        call_delete(page, node_id, analysis_id)
        expect(toast(page, REASON_LOOKUP_FAILED, "error")).to_be_visible()
    page.wait_for_timeout(300)
    assert deletes == [] and dialogs == [] and e2e_server.node_ids() == before
    select(page, a, "一次要因A")  # the rest of the screen works
    expect(inspector(page).get_by_role("button", name="手動追加", exact=True)).to_be_enabled()


@pytest.mark.acceptance("PR3-DELETE-SCOPE")
def test_missing_parent_and_upper_factors_are_deleted_with_exactly_their_subtree(page, e2e_server):
    other = e2e_server.create_analysis("別の分析", top_event="別")
    kept_elsewhere = {e2e_server.insert_node(other, 1, title="別の分析の要因"),
                      e2e_server.insert_node(other, 2, MISSING, title="別の分析の親不在の要因")}
    analysis_id = e2e_server.create_analysis("親不在の削除", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    m = e2e_server.insert_node(analysis_id, 2, MISSING, title="親不在の要因M")
    m2 = e2e_server.insert_node(analysis_id, 3, m, title="Mの下の要因M2")
    n = e2e_server.insert_node(analysis_id, 2, MISSING, title="親不在の要因N")
    n2 = e2e_server.insert_node(analysis_id, 3, n, title="Nの下の要因N2")
    open_edit(page, analysis_id)
    dialogs = record_dialogs(page, action="accept")
    before = e2e_server.node_ids()

    select(page, n2, "Nの下の要因N2")  # 「上位に不整合あり」
    delete_button(page).click()
    expect(select_button(page, "nav", n2)).to_have_count(0)
    wait_until(lambda: n2 not in e2e_server.node_ids())
    assert before - e2e_server.node_ids() == {n2}

    select(page, m, "親不在の要因M")  # 親不在, with its child
    delete_button(page).click()
    expect(select_button(page, "nav", m)).to_have_count(0)
    wait_until(lambda: m not in e2e_server.node_ids())
    assert before - e2e_server.node_ids() == {n2, m, m2}
    assert kept_elsewhere <= e2e_server.node_ids(other) and a in e2e_server.node_ids() and n in e2e_server.node_ids()
    assert dialogs == ["confirm", "confirm"]


# ----- PR3-GEN-PARENTS ---------------------------------------------------------------

def generate_bodies(page) -> list[dict]:
    """Bodies of the generation requests the page sends."""
    seen: list[dict] = []

    def record(request):
        if request.method == "POST" and re.search(r"/generate/level/\d$", urlparse(request.url).path):
            seen.append({"level": int(urlparse(request.url).path.rsplit("/", 1)[1]), **(request.post_data_json or {})})

    page.on("request", record)
    return seen


@pytest.mark.acceptance("PR3-GEN-PARENTS")
def test_normal_generation_uses_consistent_yes_parents_only(page, e2e_server):
    analysis_id = e2e_server.create_analysis("生成の親（通常）", top_event="頂上")
    a = e2e_server.insert_node(analysis_id, 1, title="一次要因A", judgement="yes")
    b = e2e_server.insert_node(analysis_id, 1, title="一次要因B", judgement="yes")
    e2e_server.insert_node(analysis_id, 1, a, title="親を持つ一次要因L", judgement="yes")        # level mismatch
    e2e_server.insert_node(analysis_id, 1, MISSING, title="親不在の一次要因M", judgement="yes")  # missing parent
    e2e_server.set_stub_mode("delay", delay_seconds=1)  # the start message stays while it runs
    open_edit(page, analysis_id)
    bodies = generate_bodies(page)

    page.fill("#edit-filter-text", "一次要因A")  # B is hidden, still a target (J-07)
    expect(item(page, "work", b)).to_be_hidden()
    step_button(page, 3).click()
    expect(page.locator('[data-target-count="2"]')).to_have_text("2")
    expect(page.locator('[data-target-excluded="2"]')).to_be_visible()
    expect(page.locator('[data-target-excluded="2"] [data-target-excluded-count]')).to_have_text("2")
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    expect(toast(page, "2件の親要因から順に生成中...（親子関係に不整合があるYes評価の要因2件は対象外）", "success")).to_be_visible()
    for parent_id in (a, b):
        expect(page.locator(f'[data-group-parent="{parent_id}"] [data-role="work-item"]')).to_have_count(3)
    assert [(body["level"], body.get("parent_id")) for body in bodies] == [(2, a), (2, b)]
    assert [call["parent_factor"] for call in e2e_server.stub_calls()] == ["一次要因A", "一次要因B"]


@pytest.mark.acceptance("PR3-GEN-PARENTS")
def test_no_request_when_every_yes_parent_is_inconsistent(page, e2e_server):
    analysis_id = e2e_server.create_analysis("生成の親（すべて対象外）", top_event="頂上")
    a = e2e_server.insert_node(analysis_id, 1, title="一次要因A")  # consistent, not Yes
    e2e_server.insert_node(analysis_id, 1, a, title="親を持つ一次要因L", judgement="yes")
    open_edit(page, analysis_id)
    bodies = generate_bodies(page)

    step_button(page, 3).click()
    expect(page.locator('[data-target-count="2"]')).to_have_text("0")
    expect(page.locator('[data-target-excluded="2"] [data-target-excluded-count]')).to_have_text("1")
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    expect(toast(
        page, "生成できる親要因がありません（Yes評価の要因のうち1件は親子関係に不整合があるため対象外です）", "error",
    )).to_be_visible()
    page.wait_for_timeout(300)
    assert bodies == [] and e2e_server.stub_calls() == []


@pytest.mark.acceptance("PR3-GEN-PARENTS")
def test_additional_generation_and_manual_add_below_inconsistent_parents_are_refused(page, e2e_server):
    analysis_id = e2e_server.create_analysis("生成の親（追加生成・手動追加）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")                                   # consistent, 未評価
    z = e2e_server.insert_node(analysis_id, 1, MISSING, title="親不在の一次要因Z")
    u = e2e_server.insert_node(analysis_id, 2, z, title="Zの下の二次要因U")               # 「上位に不整合あり」
    m = e2e_server.insert_node(analysis_id, 2, MISSING, title="親不在の二次要因M")
    open_edit(page, analysis_id)
    bodies = generate_bodies(page)
    adds = posts(page, r"^/nodes/\d+/children$|/nodes/add-level1$")
    before = e2e_server.node_ids()

    for node_id, title in ((u, "Zの下の二次要因U"), (m, "親不在の二次要因M"), (z, "親不在の一次要因Z")):
        select(page, node_id, title)
        for name in ("AIで追加生成", "手動追加"):
            expect(inspector(page).get_by_role("button", name=name, exact=True)).to_be_disabled()
        expect(inspector(page).locator("#inspector-children-reason")).to_have_text(PARENT_REASON_INCONSISTENT)

    # Direct calls are refused before anything is sent (or opened).
    page.evaluate("([aid, id]) => generateAdditional(aid, id, 3)", [analysis_id, u])
    expect(toast(page, PARENT_REASON_INCONSISTENT, "error")).to_be_visible()
    page.evaluate("([aid, id]) => showAddNodeModal(aid, id, 3)", [analysis_id, m])
    expect(page.locator("#addNodeModal")).to_be_hidden()
    page.evaluate("([aid]) => generateAdditional(aid, null, 2)", [analysis_id])
    expect(toast(page, "親要因が指定されていないため、追加・生成できません", "error")).to_be_visible()

    # The manual-add dialog opened for A but pointed at M before sending.
    select(page, a, "一次要因A")
    inspector(page).get_by_role("button", name="手動追加", exact=True).click()
    expect(page.locator("#addNodeTitle")).to_be_focused()
    page.evaluate("(id) => { document.getElementById('addNodeParentId').value = String(id); }", m)
    page.fill("#addNodeTitle", "送られてはいけない要因")
    page.locator("#addNodeModal").get_by_role("button", name="追加").click()
    expect(toast(page, PARENT_REASON_INCONSISTENT, "error")).to_be_visible()
    page.wait_for_timeout(300)
    assert bodies == [] and adds == [] and e2e_server.node_ids() == before
    page.locator("#addNodeModal").get_by_role("button", name="キャンセル").click()

    # Below the consistent A (未評価) additional generation works (J-16).
    add_more = inspector(page).get_by_role("button", name="AIで追加生成", exact=True)
    expect(add_more).to_be_enabled()
    add_more.click()
    expect(page.locator(f'[data-group-parent="{a}"] [data-role="work-item"]')).to_have_count(2)
    assert bodies == [{"level": 2, "additional": True, "parent_id": a}]

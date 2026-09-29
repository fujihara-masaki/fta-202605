"""E2E: partial update of the edit screen (PR-3) — plan 3.4-5, 5.7, 8.3,
E-E07 and E-E19.

After a manual add, a delete, a detail save or a generation (still the
legacy app.js in PR-3) the page fetches its own URL again and replaces only
the structure (edit/refresh.js); it is never reloaded. The tests mark the
page (window.__pr3NoReload) and check that the mark is still there.

* E-E07  the focus goes back to the same element (or the parent's row / the
         list heading when it is gone); scroll positions, the view tab, the
         filter and typed input in ① stay; the added factor is selected, the
         parent of a deleted one; a factor removed elsewhere moves the
         selection to its nearest ancestor; the analysis deleted elsewhere
         (404) stops the operations; a failed fetch reloads the page when
         nothing is typed and keeps the page (with a message) when something
         is; nothing is fetched while a generation runs, once after it.
* E-E19  an old answer never rolls the page back: the answer to a fetch
         issued before a judgement was saved is discarded and fetched again;
         an answer without the judgement the server confirmed is not applied
         and, the second time, 「表示を最新にできませんでした」 is shown.

Where no screen operation can cause the case (the analysis deleted in
another tab, a fetch while a generation runs), the tests call the bridge the
legacy functions use (window.ftaEditBridge.refresh).
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urlparse

import pytest

from tests.e2e.edit_helpers import (
    chip,
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
    wait_until,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e

GONE_TEXT = "分析が見つかりません（削除された可能性があります）。この画面では保存・生成・削除ができません。一覧へ戻ってください。"


# ----- helpers ----------------------------------------------------------------

def mark_page(page) -> None:
    page.evaluate("() => { window.__pr3NoReload = 'kept'; }")


def same_page(page) -> bool:
    return page.evaluate("() => window.__pr3NoReload === 'kept'")


def is_page_fetch(request, analysis_id: int) -> bool:
    """GET /analyses/{id} sent by the page's script (the partial update)."""
    return (request.method == "GET" and request.resource_type == "fetch"
            and urlparse(request.url).path == f"/analyses/{analysis_id}")


def page_fetches(page, analysis_id: int) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url) if is_page_fetch(request, analysis_id) else None)
    return seen


def refresh(page) -> None:
    page.evaluate("() => window.ftaEditBridge.refresh({})")


def scroll_top(page, name: str) -> int:
    return page.locator(f'[data-scroll="{name}"]').evaluate("(el) => el.scrollTop")


def set_scroll_top(page, name: str, value: int) -> int:
    return page.locator(f'[data-scroll="{name}"]').evaluate("(el, v) => { el.scrollTop = v; return el.scrollTop; }", value)


def nav(page):
    return page.locator("#edit-nav")


def watch_data(page, node_id: int) -> None:
    """Record the judgement of `node_id` each time the embedded data is replaced."""
    page.evaluate("""(id) => {
      window.__dataChanges = [];
      const script = document.getElementById('analysis-data');
      new MutationObserver(() => {
        const data = JSON.parse(script.textContent);
        const node = data.nodes.find((n) => n.id === id);
        window.__dataChanges.push(node ? node.judgement : null);
      }).observe(script, { childList: true, characterData: true, subtree: true });
    }""", node_id)


def data_changes(page) -> list:
    return page.evaluate("() => window.__dataChanges")


def embedded_judgement(page, node_id: int):
    return page.evaluate(
        "(id) => { const n = JSON.parse(document.getElementById('analysis-data').textContent)"
        ".nodes.find((x) => x.id === id); return n ? n.judgement : null; }", node_id)


def wait_for(page, check, timeout: float = 10.0) -> None:
    """Let the page run (and Playwright deliver its events) until `check()` holds."""
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within the timeout")
        page.wait_for_timeout(50)


def selected_node(page) -> int:
    return int(nav(page).locator('[data-action="select"][aria-current="true"]').get_attribute("data-node-id"))


def open_dialog(page, button, field: str) -> None:
    """Open a legacy dialog and wait for its first field: app.js focuses it
    50 ms after opening, which would otherwise take text typed meanwhile."""
    button.click()
    expect(page.locator(field)).to_be_focused()


def open_detail(page) -> None:
    open_dialog(page, inspector(page).get_by_role("button", name="詳細を編集"), "#modalTitle")


def many_level1(server, title: str, count: int = 30) -> tuple[int, list[int]]:
    """Enough 一次要因 for the navigation and the work list to scroll."""
    analysis_id = server.create_analysis(title, top_event="決済が失敗する")
    ids = [server.add_level1(analysis_id, f"一次要因{n:02d}", f"一次要因{n:02d}の説明") for n in range(1, count + 1)]
    return analysis_id, ids


# ----- E-E07 --------------------------------------------------------------------

@pytest.mark.acceptance("E-E07")
def test_E_E07_detail_save_keeps_focus_scroll_and_typed_input(page, e2e_server):
    analysis_id, ids = many_level1(e2e_server, "部分更新（詳細の保存）")
    target = ids[20]
    open_edit(page, analysis_id, f"#sel={target}&step=2&view=work")

    # Typed (not saved) in ①, then back to ②.
    step_button(page, 1).click()
    page.fill("#topEventInput", "入力中の頂上事象（未保存）")
    step_button(page, 2).click()
    center = set_scroll_top(page, "center", 600)
    navigation = set_scroll_top(page, "nav", 200)
    assert center > 0 and navigation > 0
    mark_page(page)
    fetches = page_fetches(page, analysis_id)

    edit = inspector(page).get_by_role("button", name="詳細を編集")
    open_dialog(page, edit, "#modalTitle")
    page.fill("#modalTitle", "一次要因21（改名）")
    page.fill("#modalDescription", "改めた説明")
    page.locator("#modalSaveBtn").click()

    expect(inspector_title(page)).to_have_text("一次要因21（改名）")
    expect(page.locator('[data-details] [data-detail="description"]')).to_have_text("改めた説明")
    for role in ("nav", "work", "tree", "table"):
        expect(select_button(page, role, target)).to_contain_text("一次要因21（改名）")
    expect_selected(page, target, "一次要因21（改名）")
    expect(edit).to_be_focused()
    assert same_page(page)
    assert (scroll_top(page, "center"), scroll_top(page, "nav")) == (center, navigation)
    expect(page.locator("#topEventInput")).to_have_value("入力中の頂上事象（未保存）")
    expect(page.locator("#topEventInput")).to_have_attribute("data-saved", "決済が失敗する")
    expect(page).to_have_url(re.compile(rf"#sel={target}&step=2&view=work$"))
    assert len(fetches) == 1


@pytest.mark.acceptance("E-E07")
def test_E_E07_manual_add_and_delete_select_and_keep_the_focus(page, e2e_server):
    analysis_id = e2e_server.create_analysis("部分更新（追加と削除）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_child(a, "二次要因B")
    x = e2e_server.add_child(a, "別の要因X")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    step_button(page, 1).click()
    page.fill("#topEventInput", "入力中（未保存）")
    step_button(page, 3).click()
    page.fill("#edit-filter-text", "二次要因")
    expect(item(page, "work", x)).to_be_hidden()
    expect(page.locator("#edit-filter-count")).to_have_text("一致 1件（全3件）")
    mark_page(page)
    fetches = page_fetches(page, analysis_id)

    # Manual add from the parent's group heading: the new factor is selected,
    # the focus is back on the button, the filter still applies.
    add = page.locator(f'[data-group-parent="{a}"]').get_by_role("button", name="手動追加（親：一次要因A）")
    open_dialog(page, add, "#addNodeTitle")
    page.fill("#addNodeTitle", "手動で追加した二次要因")
    page.locator("#addNodeModal").get_by_role("button", name="追加").click()
    expect(inspector_title(page)).to_have_text("手動で追加した二次要因")
    added = selected_node(page)
    assert e2e_server.get_node(added)["parent_id"] == a
    expect_selected(page, added, "手動で追加した二次要因")
    expect(add).to_be_focused()
    expect(page.locator("#edit-filter-count")).to_have_text("一致 2件（全4件）")
    expect(item(page, "work", x)).to_be_hidden()
    expect(item(page, "work", added)).to_be_visible()
    expect(page.locator("#topEventInput")).to_have_value("入力中（未保存）")
    expect(page).to_have_url(re.compile(rf"#sel={added}&step=3&view=work$"))
    assert same_page(page) and len(fetches) == 1

    # Delete it from the inspector: its parent is selected (step ②) and the
    # focus, whose button is gone, moves to the inspector heading.
    dialogs = record_dialogs(page, action="accept")
    inspector(page).get_by_role("button", name="この要因を削除").click()
    expect(inspector_title(page)).to_have_text("一次要因A")
    expect(inspector_title(page)).to_be_focused()
    assert dialogs == ["confirm"]
    for role in ("nav", "work", "tree", "table"):
        expect(select_button(page, role, added)).to_have_count(0)
    expect_selected(page, a, "一次要因A")
    expect(step_button(page, 2)).to_have_attribute("aria-current", "step")
    expect(page.locator("#edit-filter-count")).to_have_text("一致 1件（全3件）")
    expect(page.locator("#topEventInput")).to_have_value("入力中（未保存）")
    assert same_page(page) and len(fetches) == 2


@pytest.mark.acceptance("E-E07")
def test_E_E07_factor_removed_elsewhere_moves_selection_and_focus_up(page, e2e_server):
    analysis_id = e2e_server.create_analysis("部分更新（別タブでの削除）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_child(a, "二次要因B")
    c = e2e_server.add_child(b, "三次要因C")
    open_edit(page, analysis_id, f"#sel={c}&step=4&view=table")
    select_button(page, "nav", c).focus()
    mark_page(page)

    # Another tab deletes B (and C with it); then this page is updated.
    response = e2e_server.http.post(f"/nodes/{b}/delete")
    assert response.status_code == 200 and response.json()["success"] is True
    refresh(page)

    expect(inspector_title(page)).to_have_text("一次要因A")
    expect(toast(page, "選んでいた要因が見つからなくなったため、選択を切り替えました", "info")).to_be_visible()
    expect(select_button(page, "nav", a)).to_be_focused()  # C and B are gone: the nearest ancestor's row
    expect(tab(page, "table")).to_have_attribute("aria-selected", "true")
    expect(page.locator(f'[data-role="table-item"][data-node-id="{c}"]')).to_have_count(0)
    expect(page).to_have_url(re.compile(rf"#sel={a}&step=2&view=table$"))
    assert same_page(page)


@pytest.mark.acceptance("E-E07")
def test_E_E07_analysis_deleted_elsewhere_stops_the_operations(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("部分更新（分析の削除）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    open_edit(page, analysis_id)
    expect_selected(page, a, "一次要因A")
    fetches = page_fetches(page, analysis_id)
    page_watch.allow_console_error(r"status of 404")

    e2e_server.delete_analysis(analysis_id)
    refresh(page)

    expect(page.locator(".edit-gone")).to_have_text(GONE_TEXT)
    expect(toast(page, "分析が見つかりません（削除された可能性があります）", "error")).to_be_visible()
    expect(judgement_button(item(page, "work", a), a, "yes")).to_be_disabled()
    expect(judgement_button(inspector(page), a, "yes")).to_be_disabled()
    for name in ("一次要因を生成", "一次要因を追加生成", "手動追加"):
        expect(step_panel(page, 2).get_by_role("button", name=name, exact=True)).to_be_disabled()
    for name in ("詳細を編集", "AIで追加生成", "手動追加", "この要因を削除"):
        expect(inspector(page).get_by_role("button", name=name, exact=True)).to_be_disabled()
    expect(page.locator("#analysisTitle")).to_have_attribute("contenteditable", "false")

    # Selecting still works; what it shows cannot be changed.
    select_button(page, "nav", b).click()
    expect(inspector_title(page)).to_have_text("一次要因B")
    expect(judgement_button(inspector(page), b, "yes")).to_be_disabled()
    expect(inspector(page).get_by_role("button", name="詳細を編集")).to_be_disabled()
    step_button(page, 1).click()
    expect(step_panel(page, 1).get_by_role("button", name="保存", exact=True)).to_be_disabled()
    expect(step_panel(page, 1).get_by_role("button", name="コンテキストを保存")).to_be_disabled()

    refresh(page)  # nothing is fetched any more
    page.wait_for_timeout(300)
    assert len(fetches) == 1


@pytest.mark.acceptance("E-E07")
def test_E_E07_failed_fetch_keeps_typed_input_or_reloads(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("部分更新（取得の失敗）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    open_edit(page, analysis_id, f"#sel={b}&step=2&view=work")
    page_watch.allow_console_error(r"status of 500")

    def fail(route):
        if is_page_fetch(route.request, analysis_id):
            route.fulfill(status=500, content_type="application/json",
                          body=json.dumps({"detail": "E2E：部分更新の取得に失敗（検証用）"}))
        else:
            route.continue_()

    page.route(f"**/analyses/{analysis_id}", fail)

    # Something typed in ①: no reload, the reason, the input stays.
    step_button(page, 1).click()
    page.fill("#topEventInput", "入力中の頂上事象")
    step_button(page, 2).click()
    mark_page(page)
    open_dialog(page, step_panel(page, 2).get_by_role("button", name="手動追加", exact=True), "#addNodeTitle")
    page.fill("#addNodeTitle", "追加した一次要因C")
    page.locator("#addNodeModal").get_by_role("button", name="追加").click()
    expect(toast(page, "最新の表示に更新できませんでした（E2E：部分更新の取得に失敗（検証用））。"
                       "入力中の内容を保存してから、ページを再読み込みしてください。", "error")).to_be_visible()
    assert same_page(page)
    expect(page.locator("#topEventInput")).to_have_value("入力中の頂上事象")
    assert e2e_server.node_count(analysis_id) == 3  # saved; shown after a reload

    # Nothing typed: the page is reloaded and the state comes back (plan 5.5).
    step_button(page, 1).click()
    page.fill("#topEventInput", "頂上")
    select_button(page, "nav", b).click()
    open_detail(page)
    page.fill("#modalMemo", "再読み込みの前に保存したメモ")
    page.locator("#modalSaveBtn").click()
    page.wait_for_function("() => window.__pr3NoReload === undefined")
    expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    expect_selected(page, b, "一次要因B")
    expect(page.locator('[data-details] [data-detail="memo"]')).to_have_text("再読み込みの前に保存したメモ")
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(3)
    assert a in {int(v) for v in step_panel(page, 2).locator('[data-role="work-item"]').evaluate_all(
        "els => els.map((e) => e.dataset.nodeId)")}


@pytest.mark.acceptance("E-E07")
def test_E_E07_no_fetch_while_a_generation_runs_one_after(page, e2e_server):
    analysis_id = e2e_server.create_analysis("部分更新（生成中）", top_event="頂上")
    e2e_server.add_level1(analysis_id, "一次要因A")
    e2e_server.set_stub_mode("delay", delay_seconds=3)
    open_edit(page, analysis_id)
    fetches = page_fetches(page, analysis_id)
    mark_page(page)

    overlay = page.locator("#loadingOverlay")
    step_panel(page, 2).get_by_role("button", name="一次要因を追加生成").click()
    expect(overlay).to_be_visible()
    wait_until(lambda: len(e2e_server.stub_calls()) == 1)
    refresh(page)  # e.g. another change asked for an update meanwhile
    refresh(page)
    page.wait_for_timeout(300)
    expect(overlay).to_be_visible()  # still generating …
    assert fetches == []             # … and nothing fetched

    expect(overlay).to_be_hidden(timeout=15000)
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(3)
    page.wait_for_timeout(500)
    assert len(fetches) == 1
    assert same_page(page)


# ----- E-E19 --------------------------------------------------------------------

@pytest.mark.acceptance("E-E19")
def test_E_E19_answer_fetched_before_a_judgement_is_discarded(page, e2e_server):
    analysis_id = e2e_server.create_analysis("古い応答（書き込みの前）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    e2e_server.add_level1(analysis_id, "一次要因B")
    open_edit(page, analysis_id)
    watch_data(page, a)
    held_fetch, held_write = [], []

    def hold_first_fetch(route):
        if not is_page_fetch(route.request, analysis_id) or held_fetch:
            route.continue_()
            return
        held_fetch.append((route, route.fetch()))  # the page as it is now, answered later

    def hold_first_write(route):
        if route.request.method != "POST" or held_write:
            route.continue_()
            return
        held_write.append(route)

    page.route(f"**/analyses/{analysis_id}", hold_first_fetch)
    page.route(f"**/nodes/{a}/update", hold_first_write)
    fetches = page_fetches(page, analysis_id)
    mark_page(page)

    # A manual add asks for an update; its answer is held back …
    open_dialog(page, step_panel(page, 2).get_by_role("button", name="手動追加", exact=True), "#addNodeTitle")
    page.fill("#addNodeTitle", "手動で追加した一次要因")
    page.locator("#addNodeModal").get_by_role("button", name="追加").click()
    wait_for(page, lambda: bool(held_fetch))
    # … while the judgement of A is being saved, and more updates are asked for.
    judgement_button(item(page, "work", a), a, "yes").click()
    wait_for(page, lambda: bool(held_write))
    refresh(page)
    refresh(page)

    # The old answer arrives while the judgement is still being saved:
    # discarded, and nothing is fetched until the write has finished.
    route, stale = held_fetch[0]
    route.fulfill(response=stale)
    page.wait_for_timeout(500)
    assert data_changes(page) == []
    assert len(fetches) == 1
    expect(chip(nav(page), a)).to_have_text("未評価")

    held_write[0].continue_()  # the judgement is saved; then one fetch
    expect(chip(nav(page), a)).to_have_text("Yes")
    expect(inspector_title(page)).to_have_text("手動で追加した一次要因")
    expect(chip(page.locator("#edit-panel-table"), a)).to_have_text("Yes")
    assert e2e_server.judgement(a) == "yes"
    assert embedded_judgement(page, a) == "yes"
    page.wait_for_timeout(300)
    assert len(fetches) == 2              # the held one and one more for every request
    assert data_changes(page) == ["yes"]  # applied once, never the old answer
    assert same_page(page)


@pytest.mark.acceptance("E-E19")
def test_E_E19_answer_without_the_confirmed_judgement_is_not_applied(page, e2e_server):
    analysis_id = e2e_server.create_analysis("古い応答（確定済みの評価）", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    open_edit(page, analysis_id)
    old_page = e2e_server.http.get(f"/analyses/{analysis_id}").text  # before the judgement
    watch_data(page, a)
    judgement_button(item(page, "work", a), a, "yes").click()
    expect(chip(nav(page), a)).to_have_text("Yes")
    wait_until(lambda: e2e_server.judgement(a) == "yes")

    def answer_old(route):
        if is_page_fetch(route.request, analysis_id):
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=old_page)
        else:
            route.continue_()

    page.route(f"**/analyses/{analysis_id}", answer_old)
    fetches = page_fetches(page, analysis_id)
    mark_page(page)

    # A detail save of B asks for an update; the answers lack A's judgement.
    select_button(page, "nav", b).click()
    open_detail(page)
    page.fill("#modalMemo", "Bのメモ")
    page.locator("#modalSaveBtn").click()

    expect(toast(page, "表示を最新にできませんでした。ページを再読み込みしてください。", "error")).to_be_visible()
    page.wait_for_timeout(300)
    assert len(fetches) == 2
    assert data_changes(page) == []  # nothing applied
    expect(chip(nav(page), a)).to_have_text("Yes")
    expect(judgement_button(item(page, "work", a), a, "yes")).to_have_attribute("aria-pressed", "true")
    assert same_page(page)

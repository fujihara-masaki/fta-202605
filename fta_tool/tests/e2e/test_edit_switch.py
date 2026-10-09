"""E2E: switching the factor of the inspector with an unsaved draft (PR-5) —
R-01, plan 5.1, 5.2, 5.9.1 (the part of J-01 moved forward), 5.9.3, 8.5;
E-E15 and E-E18.

* E-E15  every R-01 route — the structure navigation, a work-list row, the
         parent's name of a group heading, the tree, the table, 要確認, the
         breadcrumb, a child link, the top event (and the selection after a
         manual add: test_edit_inspector.py) — asks about the inspector's
         unsaved draft with the three choices; 編集を続ける and Esc keep the
         selection, the step, the hash and the input and give the focus back
         to the control. 保存して移動 saves to the factor being edited (never
         the one chosen), the list shows ① too and saves 要因 → 頂上事象 →
         参考情報 (validated first: an empty title sends nothing and switches
         nothing; a partial failure keeps the page with each result, 再試行
         sends the failed one only, 破棄して移動 then says what stays saved).
         Input typed and restored, the same factor chosen again (or its
         要確認), and unsaved ① alone switch without a question and keep the
         draft / ①; A → B → A leaves one source, never two saves.
* E-E18  a switch while the factor's save is in flight waits for it (the
         answer never reaches the next factor's inspector); while the details
         load, the fields are off and an old answer (A → B → A: the first A's)
         is never used; a partial update fetched before a save never rolls the
         saved values back; a draft survives partial updates (another factor
         added, a generation's result) and the external removal of its factor
         (the input stays with the reason it cannot be saved, the selection
         is not moved, nothing is sent elsewhere; a factor's 404 is told from
         the analysis' 404). While a generation is prepared, runs or is
         finished (J-01, moved forward to PR-5 for the real inspector): no
         save of the factor is started, a switch with a draft offers
         編集を続ける / 破棄して移動 only with the reason, 破棄して移動 drops the
         inspector's change alone (① stays), a switch without a draft is not
         refused, and once the generation is done the three choices are back.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import pytest

from tests.e2e.edit_helpers import (
    GENERATING_SWITCH,
    add_factor,
    choose,
    editor,
    expect_editor_ready,
    expect_selected,
    factor_field,
    factor_message,
    factor_save,
    factor_status,
    inspector,
    inspector_title,
    item,
    leave_dialog,
    leave_link,
    open_edit,
    save_status,
    select_button,
    step_button,
    step_panel,
    tab,
    toast,
    top_button,
    wait_until,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e

SWITCH_NOTE = "「破棄して移動」を選ぶと、上の一覧のすべての変更が破棄されます。"


def posts(page) -> list[str]:
    sent: list[str] = []
    page.on("request", lambda r: sent.append(urlparse(r.url).path) if r.method == "POST" else None)
    return sent


def detail_gets(page, node_id: int) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda r: seen.append(r.url)
            if r.method == "GET" and urlparse(r.url).path == f"/nodes/{node_id}" else None)
    return seen


def is_page_fetch(request, analysis_id: int) -> bool:
    return (request.method == "GET" and request.resource_type == "fetch"
            and urlparse(request.url).path == f"/analyses/{analysis_id}")


def pump(page, check, timeout: float = 10.0) -> None:
    """Let the page run (and Playwright deliver its events) until check() holds."""
    import time
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within the timeout")
        page.wait_for_timeout(50)


def hash_of(page) -> str:
    return page.evaluate("() => location.hash")


def switch_dialog(page):
    return leave_dialog(page)  # the same three choices (js/common/unsaved.js)


def build(server, title="要因の切替"):
    """一次 A (Yes) → 二次 B (要確認) → 三次 C; 一次 D."""
    analysis_id = server.create_analysis(title, top_event="頂上")
    a = server.add_level1(analysis_id, "一次要因A")
    b = server.add_child(a, "二次要因B")
    c = server.add_child(b, "三次要因C")
    d = server.add_level1(analysis_id, "一次要因D")
    server.update_node(a, user_judgement="yes")
    server.set_warning(b, "既存要因に類似")
    return analysis_id, a, b, c, d


def generation_phase(page) -> str:
    return page.evaluate("async () => (await import('/static/js/common/unsaved.js')).getGenerationPhase()")


# ----- E-E15 -------------------------------------------------------------------

@pytest.mark.acceptance("E-E15")
def test_E_E15_every_route_asks_and_continue_or_escape_keeps_everything(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server)
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    sent = posts(page)
    factor_field(page, "memo").fill("切替の確認の下書き")
    kept_hash = hash_of(page)

    def asks(control, how="continue"):
        control.click()
        dialog = switch_dialog(page)
        expect(dialog).to_be_visible()
        expect(dialog.locator("ul").first.locator("li")).to_have_text(["要因「二次要因B」の内容"])
        expect(dialog).to_contain_text(SWITCH_NOTE)
        expect(dialog.get_by_role("button", name="編集を続ける")).to_be_focused()
        if how == "continue":
            dialog.get_by_role("button", name="編集を続ける").click()
        else:
            page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(control).to_be_focused()
        expect(inspector_title(page)).to_have_text("二次要因B")
        expect(editor(page)).to_have_attribute("data-node-id", str(b))
        expect(factor_field(page, "memo")).to_have_value("切替の確認の下書き")
        assert hash_of(page) == kept_hash

    routes = [
        ("nav", lambda: select_button(page, "nav", d)),
        ("top event", lambda: top_button(page, "nav")),
        ("group parent name", lambda: page.locator(f'[data-group-parent="{a}"] [data-role="group"]')),
        ("breadcrumb", lambda: inspector(page).locator(f'.edit-crumbs [data-node-id="{a}"]')),
        ("breadcrumb top", lambda: inspector(page).locator('.edit-crumbs [data-select="top"]')),
        ("child link", lambda: inspector(page).locator(f'[data-role="child"][data-node-id="{c}"]')),
    ]
    for index, (name, control) in enumerate(routes):
        asks(control(), "continue" if index % 2 == 0 else "escape")
    step_button(page, 2).click()  # the step is not a switch of the factor
    kept_hash = hash_of(page)
    asks(select_button(page, "work", d))
    kept_hash = hash_of(page)
    for view, role in (("tree", "tree"), ("table", "table")):
        tab(page, view).click()
        kept_hash = hash_of(page)
        asks(select_button(page, role, d), "escape")
    tab(page, "work").click()
    kept_hash = hash_of(page)
    step_button(page, 4).click()
    kept_hash = hash_of(page)
    # 要確認 of another factor (B's 要確認 is the same factor: no question).
    e2e_server.set_warning(c, "三次の警告")
    page.evaluate("() => window.ftaEditBridge.refresh({})")
    warning = page.locator(f'[data-role="work-warning"][data-node-id="{c}"]')
    expect(warning).to_have_count(1)
    kept_hash = hash_of(page)
    asks(warning)
    assert sent == []

    # 破棄して移動 on one route switches and saves nothing.
    select_button(page, "nav", c).click()
    switch_dialog(page).get_by_role("button", name="破棄して移動").click()
    expect_selected(page, c, "三次要因C")
    expect_editor_ready(page, c)
    assert sent == [] and e2e_server.get_node(b)["memo"] == ""


@pytest.mark.acceptance("E-E15")
def test_E_E15_save_and_go_saves_to_the_edited_factor_not_the_chosen_one(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "保存先の確認")
    e2e_server.update_node(d, memo="Dの保存済みメモ")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    sent = posts(page)
    factor_field(page, "memo").fill("Aに保存されるメモ")
    factor_field(page, "title").fill("一次要因A（保存して移動）")

    select_button(page, "nav", d).click()
    switch_dialog(page).get_by_role("button", name="保存して移動").click()
    expect_selected(page, d, "一次要因D")
    expect_editor_ready(page, d)
    expect(factor_field(page, "memo")).to_have_value("Dの保存済みメモ")  # D's own values, never A's
    assert sent == [f"/nodes/{a}/update"]
    stored = e2e_server.get_node(a)
    assert (stored["memo"], stored["title"], stored["user_judgement"]) == (
        "Aに保存されるメモ", "一次要因A（保存して移動）", "yes")
    assert e2e_server.get_node(d)["memo"] == "Dの保存済みメモ"
    expect(select_button(page, "nav", a)).to_contain_text("一次要因A（保存して移動）")
    expect(item(page, "work", a)).to_contain_text("メモあり")


@pytest.mark.acceptance("E-E15")
def test_E_E15_empty_title_sends_nothing_and_switches_nothing(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "空のタイトル")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    sent = posts(page)
    factor_field(page, "title").fill("")
    step_button(page, 1).click()
    page.fill("#topEventInput", "送られない頂上事象")
    select_button(page, "nav", d).click()
    dialog = switch_dialog(page)
    expect(dialog.locator("ul").first.locator("li")).to_have_text(["要因「一次要因A」の内容", "頂上事象"])
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog).to_contain_text("入力に不備があるため保存していません（何も送信していません）。")
    expect(dialog).to_contain_text("要因「一次要因A」の内容：要因タイトルは必須です")
    page.wait_for_timeout(300)
    assert sent == []
    dialog.get_by_role("button", name="編集を続ける").click()
    expect(inspector_title(page)).to_have_text("一次要因A")
    expect(factor_field(page, "title")).to_have_value("")
    assert e2e_server.analysis(analysis_id)["top_event"] == "頂上"


@pytest.mark.acceptance("E-E15")
def test_E_E15_restored_input_same_factor_and_step1_alone_do_not_ask(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "確認しない場合")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    gets = detail_gets(page, b)
    dialogs = record_dialogs(page)
    sent = posts(page)

    # The same factor again, and its own 要確認: no question, the draft and
    # the editor stay (no new reading of the details).
    factor_field(page, "memo").fill("同じ要因の下書き")
    select_button(page, "nav", b).click()
    page.locator(f'[data-role="work-warning"][data-node-id="{b}"]').click()
    expect(inspector(page).locator("[data-inspector-warning] .edit-inspector__section-title")).to_be_focused()
    expect(switch_dialog(page)).to_have_count(0)
    expect(factor_field(page, "memo")).to_have_value("同じ要因の下書き")
    expect(factor_status(page)).to_have_attribute("data-state", "dirty")
    page.wait_for_timeout(200)
    assert gets == []

    # Typed and restored (CRLF/spaces count as the same): no question.
    factor_field(page, "memo").fill("")
    factor_field(page, "description").fill("  \n")
    select_button(page, "nav", d).click()
    expect_selected(page, d, "一次要因D")
    expect(switch_dialog(page)).to_have_count(0)

    # Only ① unsaved, the factor's draft unchanged: switched, ① kept.
    step_button(page, 1).click()
    page.fill("#systemContextInput", "①だけの下書き")
    select_button(page, "nav", c).click()
    expect_selected(page, c, "三次要因C")
    expect(switch_dialog(page)).to_have_count(0)
    expect(page.locator("#systemContextInput")).to_have_value("①だけの下書き")
    expect(save_status(page, "systemContextInput")).to_have_attribute("data-state", "dirty")
    assert sent == [] and dialogs == []


@pytest.mark.acceptance("E-E15")
def test_E_E15_the_list_saves_factor_top_event_context_in_order_partial_failure_retry(page, e2e_server, page_watch):
    analysis_id, a, b, c, d = build(e2e_server, "要因と①の保存")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    page_watch.allow_console_error(r"status of 500")
    sent = posts(page)
    factor_field(page, "evidence").fill("Aの根拠")
    step_button(page, 1).click()
    page.fill("#topEventInput", "保存される頂上事象")
    page.fill("#incidentContextInput", "失敗する状況")
    route = f"**/analyses/{analysis_id}/context"
    page.route(route, lambda r: r.fulfill(status=500, json={"detail": "E2E: 参考情報だけ失敗"}))

    select_button(page, "nav", d).click()
    dialog = switch_dialog(page)
    expect(dialog.locator("ul").first.locator("li")).to_have_text(
        ["要因「一次要因A」の内容", "頂上事象", "参考情報（システム構成・対象範囲／障害発生時の状況・観測事実）"])
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog.locator(f'[data-source-id="edit-factor-{a}"]')).to_have_text("要因「一次要因A」の内容：保存済み")
    expect(dialog.locator('[data-source-id="edit-top-event"]')).to_have_text("頂上事象：保存済み")
    expect(dialog.locator('[data-source-id="edit-context"]')).to_contain_text("失敗：E2E: 参考情報だけ失敗")
    expect(dialog.locator("[data-partial-note]")).to_be_visible()
    assert sent == [f"/nodes/{a}/update", f"/analyses/{analysis_id}/top-event", f"/analyses/{analysis_id}/context"]
    expect(inspector_title(page)).to_have_text("一次要因A")  # not switched
    expect(factor_status(page)).to_have_attribute("data-state", "saved")

    page.unroute(route)
    dialog.get_by_role("button", name="再試行").click()
    expect_selected(page, d, "一次要因D")
    assert sent[3:] == [f"/analyses/{analysis_id}/context"]
    assert e2e_server.get_node(a)["evidence"] == "Aの根拠"
    assert e2e_server.analysis(analysis_id)["top_event"] == "保存される頂上事象"


@pytest.mark.acceptance("E-E15")
def test_E_E15_a_b_a_leaves_one_source_and_one_save(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "A→B→A")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    sent = posts(page)
    factor_field(page, "memo").fill("一度目の下書き")
    choose_d = select_button(page, "nav", d)
    choose_d.click()
    switch_dialog(page).get_by_role("button", name="破棄して移動").click()
    expect_editor_ready(page, d)
    choose(page, a)
    expect(factor_field(page, "memo")).to_have_value("")  # the discarded draft is gone
    factor_field(page, "memo").fill("二度目の下書き")
    assert page.evaluate("""async () => (await import('/static/js/common/unsaved.js')).dirtySources()
      .map((s) => s.id)""") == [f"edit-factor-{a}"]
    leave_link(page).click()
    dialog = leave_dialog(page)
    expect(dialog.locator("ul").first.locator("li")).to_have_text(["要因「一次要因A」の内容"])
    dialog.get_by_role("button", name="保存して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert sent == [f"/nodes/{a}/update"]
    assert e2e_server.get_node(a)["memo"] == "二度目の下書き"


# ----- E-E18 -------------------------------------------------------------------

@pytest.mark.acceptance("E-E18")
def test_E_E18_a_switch_waits_for_the_save_and_its_answer_stays_with_its_factor(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "保存中の切替")
    e2e_server.update_node(d, memo="Dのメモ")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    held = []
    page.route(f"**/nodes/{a}/update", lambda route: held.append(route))
    sent = posts(page)

    factor_field(page, "memo").fill("保存中のAのメモ")
    factor_save(page).click()
    pump(page, lambda: len(held) == 1)
    select_button(page, "nav", d).click()
    waiting = page.get_by_role("dialog", name="保存の完了を待っています")
    expect(waiting).to_be_visible()
    expect(waiting).to_contain_text("要因「一次要因A」の内容の保存が終わってから切り替えます。")
    expect(inspector_title(page)).to_have_text("一次要因A")  # nothing changed while waiting

    held[0].continue_()
    expect_selected(page, d, "一次要因D")
    expect_editor_ready(page, d)
    expect(factor_field(page, "memo")).to_have_value("Dのメモ")  # A's answer never reaches D
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    wait_until(lambda: e2e_server.get_node(a)["memo"] == "保存中のAのメモ")
    assert e2e_server.get_node(d)["memo"] == "Dのメモ"
    assert sent == [f"/nodes/{a}/update"]
    expect(item(page, "work", a)).to_contain_text("メモあり")


@pytest.mark.acceptance("E-E18")
def test_E_E18_details_loading_and_the_first_answer_of_a_b_a(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "読込み中の切替")
    open_edit(page, analysis_id, "#sel=top&step=1&view=work")
    held = []
    page.route(f"**/nodes/{a}", lambda r: held.append(r) if r.request.method == "GET" and not held else r.continue_())
    dialogs = record_dialogs(page)

    select_button(page, "nav", a).click()  # its details are held
    pump(page, lambda: len(held) == 1)
    expect(editor(page)).to_have_attribute("data-phase", "loading")
    expect(factor_field(page, "memo")).to_be_disabled()
    expect(factor_save(page)).to_be_disabled()
    select_button(page, "nav", d).click()  # nothing to protect yet: no question
    expect_editor_ready(page, d)
    e2e_server.update_node(a, memo="今のAのメモ")
    select_button(page, "nav", a).click()  # A again: a new reading
    expect_editor_ready(page, a)
    expect(factor_field(page, "memo")).to_have_value("今のAのメモ")
    held[0].fulfill(json={
        "id": a, "analysis_id": analysis_id, "parent_id": None, "level": 1, "title": "古い応答のA",
        "description": "", "memo": "古い応答のメモ", "user_judgement": "yes", "direct_cause_status": "unknown",
        "direct_cause_comment": "", "evidence": "", "prevention_idea": "", "warning_flags": "", "ai_generated": False,
    })
    page.wait_for_timeout(400)
    expect(factor_field(page, "memo")).to_have_value("今のAのメモ")
    expect(factor_field(page, "title")).to_have_value("一次要因A")
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    assert dialogs == []


@pytest.mark.acceptance("E-E18")
def test_E_E18_an_update_fetched_before_the_save_does_not_roll_it_back(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "保存の前の取得")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    fetches: list[str] = []
    page.on("request", lambda r: fetches.append(r.url) if is_page_fetch(r, analysis_id) else None)
    held_fetch = []

    def hold_first(route):
        if is_page_fetch(route.request, analysis_id) and not held_fetch:
            held_fetch.append((route, route.fetch()))  # the page as it is now, answered later
            return
        route.continue_()

    page.route(f"**/analyses/{analysis_id}", hold_first)
    page.evaluate("() => window.ftaEditBridge.refresh({})")  # e.g. a generation ended
    pump(page, lambda: bool(held_fetch))
    factor_field(page, "title").fill("保存後のタイトル")
    factor_field(page, "memo").fill("保存後のメモ")
    factor_save(page).click()
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    route, stale = held_fetch[0]
    route.fulfill(response=stale)  # read before the save: discarded, fetched again
    page.wait_for_timeout(800)
    for role in ("nav", "work", "tree", "table"):
        expect(select_button(page, role, a)).to_contain_text("保存後のタイトル")
    expect(item(page, "work", a)).to_contain_text("メモあり")
    expect(inspector_title(page)).to_have_text("保存後のタイトル")
    expect(factor_field(page, "memo")).to_have_value("保存後のメモ")
    assert len(fetches) >= 2


@pytest.mark.acceptance("E-E18")
def test_E_E18_draft_survives_another_add_and_a_generations_result(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "部分更新と下書き")
    open_edit(page, analysis_id, f"#sel={d}&step=2&view=work")
    expect_editor_ready(page, d)
    sent = posts(page)
    factor_field(page, "prevention_idea").fill("Dの下書き")

    # Another factor deleted elsewhere, and a factor added below A (the
    # selection of it: 編集を続ける): the partial update keeps the draft.
    e2e_server.http.post(f"/nodes/{c}/delete")
    add_factor(page, step_panel(page, 2).get_by_role("button", name="手動追加", exact=True), "別の一次要因E")
    switch_dialog(page).get_by_role("button", name="編集を続ける").click()
    expect(select_button(page, "nav", c)).to_have_count(0)
    expect(factor_field(page, "prevention_idea")).to_have_value("Dの下書き")
    expect(factor_status(page)).to_have_attribute("data-state", "dirty")
    expect(editor(page)).to_have_attribute("data-node-id", str(d))

    # A generation's result (二次 below the Yes parent A) is shown by a
    # partial update: the same editor, the draft, the focus.
    factor_field(page, "prevention_idea").focus()
    step_button(page, 3).click()
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    expect(page.locator(f'[data-group-parent="{a}"] [data-role="work-item"]')).to_have_count(4, timeout=15000)
    pump(page, lambda: generation_phase(page) == "idle", timeout=20)
    expect(factor_field(page, "prevention_idea")).to_have_value("Dの下書き")
    expect(factor_status(page)).to_have_attribute("data-state", "dirty")
    expect(inspector_title(page)).to_have_text("一次要因D")
    assert not [path for path in sent if path.endswith("/update")]
    factor_save(page).click()
    wait_until(lambda: e2e_server.get_node(d)["prevention_idea"] == "Dの下書き")


@pytest.mark.acceptance("E-E18")
def test_E_E18_the_edited_factor_removed_elsewhere_keeps_the_input_and_sends_nowhere(page, e2e_server, page_watch):
    analysis_id, a, b, c, d = build(e2e_server, "編集中の要因の外部削除")
    open_edit(page, analysis_id, f"#sel={c}&step=4&view=work")
    expect_editor_ready(page, c)
    page_watch.allow_console_error(r"status of 404")
    sent = posts(page)
    factor_field(page, "memo").fill("消えた要因の下書き")
    e2e_server.http.post(f"/nodes/{c}/delete")  # another tab

    # Saving: the factor's 404; the update tells it from the analysis' 404.
    factor_save(page).click()
    expect(toast(page, "要因を保存できませんでした：ノードが見つかりません", "error")).to_be_visible()
    expect(inspector(page).locator("[data-factor-gone]")).to_be_visible()
    expect(toast(page, "編集中の要因が見つからないため、入力内容を保存できません", "error")).to_have_count(1)
    expect(factor_message(page)).to_contain_text("編集中の要因が見つからないため、入力内容を保存できません")
    expect(factor_field(page, "memo")).to_have_value("消えた要因の下書き")
    expect(factor_field(page, "memo")).to_have_attribute("readonly", "")
    expect(factor_save(page)).to_be_disabled()
    expect(page.locator(".edit-gone")).to_have_count(0)  # the analysis is still there
    assert re.search(rf"sel={c}\b", page.url)  # not moved to the parent
    expect(select_button(page, "nav", c)).to_have_count(0)

    # Leaving: 保存して移動 sends nothing (never to another factor).
    leave_link(page).click()
    dialog = leave_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog.locator(f'[data-source-id="edit-factor-{c}"]')).to_have_attribute("data-save-result", "unsent")
    dialog.get_by_role("button", name="編集を続ける").click()
    assert sent == [f"/nodes/{c}/update"]

    # Choosing another factor: the three choices; 破棄して移動 leaves it.
    select_button(page, "nav", b).click()
    switch_dialog(page).get_by_role("button", name="破棄して移動").click()
    expect_selected(page, b, "二次要因B")
    expect_editor_ready(page, b)
    assert sent == [f"/nodes/{c}/update"]


@pytest.mark.acceptance("E-E18")
def test_E_E18_the_analysis_removed_keeps_the_input_and_stops(page, e2e_server, page_watch):
    analysis_id, a, b, c, d = build(e2e_server, "分析の外部削除")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    page_watch.allow_console_error(r"status of 404")
    sent = posts(page)
    factor_field(page, "memo").fill("消えた分析の下書き")
    e2e_server.delete_analysis(analysis_id)
    factor_save(page).click()
    expect(page.locator(".edit-gone")).to_be_visible()
    expect(factor_message(page)).to_have_text("分析が見つからないため、入力内容を保存できません（削除された可能性があります）。")
    expect(factor_field(page, "memo")).to_have_value("消えた分析の下書き")
    expect(factor_save(page)).to_be_disabled()
    assert sent == [f"/nodes/{a}/update"]


@pytest.mark.acceptance("E-E18")
def test_E_E18_generation_two_choices_no_factor_save_and_browsing_stays_free(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "生成中の切替")
    # C's details are read before the generation: while it runs the single
    # worker answers nothing else (plan 2.4; the waiting display is PR-6).
    open_edit(page, analysis_id, f"#sel={c}&step=4&view=work")
    expect_editor_ready(page, c)
    sent = posts(page)
    e2e_server.set_stub_mode("delay", delay_seconds=8)

    # ① typed, then a generation (its preparation saves the reference information).
    step_button(page, 1).click()
    page.fill("#systemContextInput", "生成で保存される構成")
    step_button(page, 3).click()
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    pump(page, lambda: any(path.endswith("/generate/level/2") for path in sent))
    assert generation_phase(page) == "running"
    step_button(page, 1).click()
    page.fill("#topEventInput", "生成中の頂上事象の下書き")

    # A draft: the save is not started …
    factor_field(page, "memo").fill("生成中の下書き")
    factor_save(page).click()
    expect(factor_message(page)).to_contain_text("生成の準備中・生成中・結果の反映中は保存できません")
    # … and a switch offers two choices with the reason, nothing to save.
    select_button(page, "nav", b).click()
    dialog = page.get_by_role("dialog", name="保存していない変更があります")
    expect(dialog.locator("[data-generating-reason]")).to_have_text(GENERATING_SWITCH)
    expect(dialog.get_by_role("button", name="保存して移動")).to_have_count(0)
    expect(dialog.get_by_role("button", name="編集を続ける")).to_be_focused()
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(inspector_title(page)).to_have_text("三次要因C")
    expect(factor_field(page, "memo")).to_have_value("生成中の下書き")
    select_button(page, "nav", b).click()
    dialog.get_by_role("button", name="破棄して移動").click()
    expect(inspector_title(page)).to_have_text("二次要因B")
    # B's details wait for the generation: nothing of C is left in its
    # fields, and nothing can be typed over them meanwhile.
    expect(editor(page)).to_have_attribute("data-node-id", str(b))
    expect(factor_field(page, "memo")).to_have_value("")
    expect(factor_field(page, "memo")).to_be_disabled()
    # Only the inspector's change was dropped; ① stays.
    expect(page.locator("#topEventInput")).to_have_value("生成中の頂上事象の下書き")

    # No draft (B still loading): browsing is never refused.
    select_button(page, "nav", d).click()
    expect(inspector_title(page)).to_have_text("一次要因D")
    expect(switch_dialog(page)).to_have_count(0)
    assert not [path for path in sent if path.startswith("/nodes/") and path.endswith("/update")]
    assert e2e_server.get_node(c)["memo"] == ""

    # After the generation: the three choices again.
    expect(step_panel(page, 3).locator(f'[data-group-parent="{a}"] [data-role="work-item"]')).to_have_count(4, timeout=20000)
    pump(page, lambda: generation_phase(page) == "idle", timeout=20)
    expect_editor_ready(page, d)
    factor_field(page, "memo").fill("生成後の下書き")
    select_button(page, "nav", b).click()
    dialog = switch_dialog(page)
    expect(dialog.get_by_role("button", name="保存して移動")).to_be_visible()
    expect(dialog.locator("ul").first.locator("li")).to_have_text(["要因「一次要因D」の内容", "頂上事象"])
    dialog.get_by_role("button", name="保存して移動").click()
    expect_selected(page, b, "二次要因B")
    assert e2e_server.get_node(d)["memo"] == "生成後の下書き"
    assert e2e_server.analysis(analysis_id)["top_event"] == "生成中の頂上事象の下書き"


@pytest.mark.acceptance("E-E18")
def test_E_E18_a_generation_that_ended_while_the_two_choices_were_open_asks_again(page, e2e_server):
    analysis_id, a, b, c, d = build(e2e_server, "生成の終了と2択")
    open_edit(page, analysis_id, f"#sel={c}&step=4&view=work")
    expect_editor_ready(page, c)
    sent = posts(page)
    e2e_server.set_stub_mode("delay", delay_seconds=3)
    step_button(page, 3).click()
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    pump(page, lambda: any(path.endswith("/generate/level/2") for path in sent))
    factor_field(page, "memo").fill("2択の間の下書き")
    select_button(page, "nav", d).click()
    dialog = page.get_by_role("dialog", name="保存していない変更があります")
    expect(dialog.locator("[data-generating-reason]")).to_be_visible()
    # The generation and its update end while the two choices are open.
    pump(page, lambda: generation_phase(page) == "idle", timeout=20)
    dialog.get_by_role("button", name="破棄して移動").click()
    # Judged again before discarding: idle now, so the three choices.
    three = switch_dialog(page)
    expect(three.get_by_role("button", name="保存して移動")).to_be_visible()
    expect(three.locator("[data-generating-reason]")).to_have_count(0)
    expect(factor_field(page, "memo")).to_have_value("2択の間の下書き")
    three.get_by_role("button", name="保存して移動").click()
    expect_selected(page, d, "一次要因D")
    assert e2e_server.get_node(c)["memo"] == "2択の間の下書き"


@pytest.mark.acceptance("E-E15")
@pytest.mark.parametrize("how", ["continue", "escape"])
def test_E_E15_after_a_partial_success_the_focus_returns_to_the_replaced_control(page, e2e_server, page_watch, how):
    """External review R-02 (2026-10-09): A's save succeeds, the reference
    information's fails; the partial update after A's save replaces the
    structure navigation (B's button is a new element) while the results are
    shown. 編集を続ける / Esc keep A and the unsaved reference information,
    and give the focus to the successor of the button that opened the dialog."""
    analysis_id, a, b, c, d = build(e2e_server, "一部成功の後のフォーカス")
    open_edit(page, analysis_id)
    expect_editor_ready(page, a)
    page_watch.allow_console_error(r"status of 500")
    page.route(f"**/analyses/{analysis_id}/context",
               lambda r: r.fulfill(status=500, json={"detail": "E2E: 参考情報だけ失敗"}))
    factor_field(page, "memo").fill("保存されるAのメモ")
    step_button(page, 1).click()
    page.fill("#systemContextInput", "保存されない構成")
    step_button(page, 2).click()
    opener = select_button(page, "nav", d)
    handle = opener.element_handle()
    opener.click()
    dialog = switch_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog.locator('[data-source-id="edit-context"]')).to_contain_text("失敗：E2E: 参考情報だけ失敗")
    pump(page, lambda: not handle.evaluate("(el) => el.isConnected"))  # the update replaced the nav
    if how == "continue":
        dialog.get_by_role("button", name="編集を続ける").click()
    else:
        page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(select_button(page, "nav", d)).to_be_focused()
    expect(inspector_title(page)).to_have_text("一次要因A")
    expect(factor_status(page)).to_have_attribute("data-state", "saved")
    expect(page.locator("#systemContextInput")).to_have_value("保存されない構成")
    expect(save_status(page, "systemContextInput")).to_have_attribute("data-state", "dirty")
    assert e2e_server.get_node(a)["memo"] == "保存されるAのメモ"

"""E2E: a generation under way (PR-6; J-01, plan 5.3, 5.9.1, 8.6).

E-G04  What is held back while it runs (judgements, saves, manual add,
       delete at its three points, another generation, exports, in-page
       links) — on the buttons, at the start of each operation and right
       before it is confirmed — and what stays free (selection, tabs, filter,
       scrolling, drafts); no overlay; everything back at the end.
E-G08  The browser's own confirmation while a generation runs, also without
       any draft; none after it.
E-G09  The preparation: every save in flight awaited and named, a failed one
       stops the generation (0 requests), the judgement queue of a factor,
       生成を取りやめる (a wait that ends later starts nothing and does not
       touch a later generation), the note after 10 s (no time limit).
E-G10  Details of a factor chosen during a generation: no GET, 取得待ち, the
       saved values read before it with their time, only the last choice read
       afterwards, an older answer dropped, a draft kept over a second read,
       a failed second read told apart from a failed first read.
E-G11  Saving is held back: the header title (Enter, leaving the input),
       the inspector; a switch with a draft asks two choices; after the end
       three.
E-G12  The restrictions end whatever happened: success, a partial failure,
       a network failure, an HTTP error, the stub's exception, an exception
       of the page's own code, a failed partial update; a slow update keeps
       them until it has ended.

A generation request is held in the browser (page.route) to keep the
generation running; nothing here is a statement about the server's safety
against other tabs or workers (plan 2.4, 5.3).
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.edit_helpers import (
    GENERATING_SWITCH,
    choose,
    delete_dialog,
    detail_gets,
    editor,
    expect_editor_ready,
    factor_field,
    factor_save,
    factor_status,
    force_click,
    gen_log,
    gen_status,
    generate_button,
    generation_requests,
    hold,
    inspector,
    item,
    judgement_button,
    leave_dialog,
    leave_link,
    log_row,
    nav_button,
    open_edit,
    phase,
    post_paths,
    pump,
    step_button,
    step_panel,
    tab,
    title_input,
    toast,
    wait_phase,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = [pytest.mark.e2e]

SINGLE = pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])


def setup(e2e_server, title="生成中の操作"):
    analysis_id = e2e_server.create_analysis(title, top_event="頂上", system_context="構成")
    a = e2e_server.add_level1(analysis_id, "親A")
    b = e2e_server.add_level1(analysis_id, "要因B")
    c = e2e_server.add_level1(analysis_id, "要因C")
    e2e_server.update_node(a, user_judgement="yes", memo="Aのメモ")
    e2e_server.update_node(b, description="Bの説明")
    e2e_server.update_node(c, description="Cの説明")
    return analysis_id, a, b, c


def start_held(page, analysis_id, level=2):
    """Start the normal generation of `level` and hold its first request."""
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/{level}")
    step_button(page, level + 1).click()
    generate_button(page, level).click()
    pump(page, lambda: len(held) == 1)
    assert phase(page) == "running"
    return held


def release(page, held):
    for route in held:
        route.continue_()
    wait_phase(page, "idle", timeout=15)


# ----- E-G04 --------------------------------------------------------------------

@pytest.mark.acceptance("E-G04")
def test_E_G04_writes_and_moves_are_held_back_browsing_is_free(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server)
    open_edit(page, analysis_id)
    choose(page, b)
    sent = post_paths(page)
    gets = []
    page.on("request", lambda request: gets.append(request.url) if "/export/" in request.url else None)
    held = start_held(page, analysis_id)
    expect(page.locator("#loadingOverlay")).to_have_count(0)  # J-05: no overlay
    status = gen_status(page)
    expect(status).to_be_visible()
    expect(status).to_contain_text("生成中（二次要因の通常生成・1件の親）")
    expect(status).to_contain_text("完了まで保存・評価・追加・削除・出力・画面の移動はできません")
    expect(page.locator("[data-edit-page]")).to_have_attribute("data-generation-phase", "running")

    # Buttons: off.
    for locator in (judgement_button(item(page, "work", a), a, "no"), generate_button(page, 2),
                    step_panel(page, 3).locator('[data-action="add"]').first,
                    inspector(page).locator('[data-action="delete"]'),
                    inspector(page).locator('[data-action="add"]'),
                    inspector(page).locator('[data-action="judgement"]').first,
                    factor_save(page)):
        expect(locator).to_be_disabled()
    expect(leave_link(page)).to_have_attribute("aria-disabled", "true")
    expect(page.locator('.app-header a[href="/"]').first).to_have_attribute("aria-disabled", "true")
    # The judgement buttons look disabled too (Windows check of 2026-10-21:
    # they looked as usual): dimmed as the other disabled buttons, the
    # not-allowed cursor, the chosen value (A: Yes) still told apart.
    chosen, other = (judgement_button(item(page, "work", a), a, value) for value in ("yes", "no"))
    for button in (chosen, other):
        expect(button).to_have_css("opacity", "0.55")
        expect(button).to_have_css("cursor", "not-allowed")
    expect(chosen).not_to_have_css("background-color", other.evaluate("(b) => getComputedStyle(b).backgroundColor"))

    # Their own checks: a stale enabled button sends nothing.
    force_click(judgement_button(item(page, "work", a), a, "no"))
    expect(toast(page, "生成中のため評価を変更できません", "warning")).to_be_visible()
    force_click(inspector(page).locator('[data-action="add"]'))
    expect(toast(page, "生成中のため手動追加できません", "error")).to_be_visible()
    force_click(inspector(page).locator('[data-action="delete"]'))  # opening the delete dialog
    expect(toast(page, "生成中のため削除できません", "error")).to_be_visible()
    expect(delete_dialog(page)).to_have_count(0)
    force_click(generate_button(page, 2))
    expect(toast(page, "別の生成の準備中または実行中です", "warning")).to_be_visible()
    step_button(page, 1).click()
    page.fill("#topEventInput", "生成中に書いた頂上事象")
    force_click(step_panel(page, 1).locator('[data-save-button="top-event"]'))
    expect(toast(page, "生成の準備中・生成中・結果の反映中は保存できません", "warning")).to_be_visible()
    # Exports (the download links) and in-page links, by mouse and keyboard.
    # aria-disabled links are still clicked by a user (force: no actionability wait).
    page.locator(".edit-header [data-ui-menu-button]").click()
    page.locator('.edit-header a[data-export-format="csv"]').click(force=True)
    expect(toast(page, "生成中のため出力できません", "warning")).to_be_visible()
    page.keyboard.press("Escape")
    page.evaluate("() => document.querySelectorAll('#ui-toasts .ui-toast__close').forEach((b) => b.click())")
    step_button(page, 5).click()
    step_panel(page, 5).locator('a[data-export-format="json"]').click(force=True)
    expect(toast(page, "生成中のため出力できません", "warning")).to_be_visible()
    leave_link(page).focus()
    page.keyboard.press("Enter")
    expect(toast(page, "生成中のため移動できません", "warning")).to_be_visible()
    page.locator('.app-header__nav a[href="/analyses/new"]').click(force=True)
    expect(page).to_have_url(re.compile(rf"/analyses/{analysis_id}(#.*)?$"))

    # Browsing is free: selection (no detail request), tabs, filter, typing.
    nav_button(page, c).click()
    expect(editor(page)).to_have_attribute("data-node-id", str(c))
    tab(page, "tree").click()
    expect(page.locator('[data-view-panel="tree"]')).to_be_visible()
    tab(page, "work").click()
    page.fill("#edit-filter-text", "要因")
    expect(page.locator("#edit-filter-count")).not_to_have_text("")
    page.fill("#edit-filter-text", "")
    page.wait_for_timeout(300)
    assert [p for p in sent if "/update" in p or "/delete" in p or "/children" in p or "add-level1" in p
            or p.endswith("/top-event") or p.endswith("/context") or p.endswith("/title")] == []
    assert gets == []

    release(page, held)
    # Back: the buttons, the links, the save of ①.
    expect(judgement_button(item(page, "work", a), a, "no")).to_be_enabled()
    for button in (chosen, other):
        expect(button).to_have_css("opacity", "1")
        expect(button).to_have_css("cursor", "pointer")
    expect(generate_button(page, 2)).to_be_enabled()
    expect(leave_link(page)).not_to_have_attribute("aria-disabled", "true")
    expect(status).to_be_hidden()
    expect(page.locator("[data-edit-page]")).to_have_attribute("data-generation-phase", "idle")
    step_button(page, 1).click()
    expect(page.locator("#topEventInput")).to_have_value("生成中に書いた頂上事象")
    expect(step_panel(page, 1).locator('[data-save-button="top-event"]')).to_be_enabled()
    step_button(page, 2).click()
    judgement_button(item(page, "work", a), a, "unknown").click()
    expect(toast(page, "評価を更新しました", "success")).to_be_visible()


@SINGLE
@pytest.mark.acceptance("E-G04")
def test_E_G04_delete_and_add_are_refused_when_confirmed_during_a_generation(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "削除の確定")
    open_edit(page, analysis_id)
    choose(page, b)
    sent = post_paths(page)
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/2")
    inspector(page).get_by_role("button", name="この要因を削除").click()
    dialog = delete_dialog(page)
    expect(dialog).to_be_visible()
    # The generation starts behind the open dialog (as another way to start it would).
    page.evaluate("() => document.querySelector('[data-action=\"generate\"][data-level=\"2\"]').click()")
    pump(page, lambda: len(held) == 1)
    dialog.get_by_role("button", name="削除する").click()
    expect(dialog).to_contain_text("生成中のため削除できません")
    assert [p for p in sent if p.endswith("/delete")] == []
    dialog.get_by_role("button", name="キャンセル").click()
    release(page, held)
    assert e2e_server.node_ids(analysis_id) >= {a, b, c}

    # The manual-add dialog: opened before a generation, confirmed during it.
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/2")
    inspector(page).get_by_role("button", name="手動追加", exact=True).click()
    page.fill("#add-factor-title", "生成中に確定する要因")
    page.evaluate("() => document.querySelector('[data-action=\"generate\"][data-level=\"2\"]').click()")
    pump(page, lambda: len(held) == 1)
    add = page.get_by_role("dialog", name="要因を手動追加")
    add.get_by_role("button", name="追加する").click()
    expect(add).to_contain_text("生成中のため手動追加できません")
    expect(page.locator("#add-factor-title")).to_have_value("生成中に確定する要因")
    add.get_by_role("button", name="キャンセル").click()
    release(page, held)
    assert [p for p in sent if p.endswith("/children") or p.endswith("/add-level1") or p.endswith("/delete")] == []


@SINGLE
@pytest.mark.acceptance("E-G04")
def test_E_G04_an_inconsistent_parents_buttons_stay_disabled_after_the_end(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "不整合の無効化")
    broken = e2e_server.insert_node(analysis_id, 2, None, title="親のない二次要因")
    open_edit(page, analysis_id)
    choose(page, broken)
    add = inspector(page).locator('[data-action="add"]')
    expect(add).to_be_disabled()
    held = start_held(page, analysis_id)
    release(page, held)
    expect(add).to_be_disabled()
    expect(inspector(page).locator('[data-action="generate-additional"]')).to_be_disabled()
    expect(generate_button(page, 2)).to_be_enabled()


# ----- E-G08 --------------------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("E-G08")
def test_E_G08_the_browser_asks_while_a_generation_runs_without_any_draft(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "生成中の離脱確認")
    open_edit(page, analysis_id)
    dialogs = record_dialogs(page, action="dismiss")
    page.reload()  # idle, nothing typed: no question
    assert dialogs == []
    held = start_held(page, analysis_id)
    page.evaluate("() => { window.__pr6Mark = 'kept'; window.location.reload(); }")
    pump(page, lambda: dialogs == ["beforeunload"])
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__pr6Mark") == "kept"  # dismissed: the page stays, the generation goes on
    assert phase(page) == "running"
    release(page, held)
    page.reload()
    assert dialogs == ["beforeunload"]  # none after the end


# ----- E-G09 --------------------------------------------------------------------

def start_preparing(page, level):
    step_button(page, level + 1).click()
    generate_button(page, level).click()
    pump(page, lambda: phase(page) == "preparing")


@pytest.mark.acceptance("E-G09")
@SINGLE
@pytest.mark.parametrize("kind", ["judgement", "factor", "top-event", "context", "title"])
def test_E_G09_a_save_in_flight_is_awaited_named_and_a_failure_stops_it(page, e2e_server, page_watch, kind):
    page_watch.allow_console_error(r"status of 500")
    analysis_id, a, b, c = setup(e2e_server, "先行する保存")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    if kind == "judgement":
        held = hold(page, f"**/nodes/{b}/update")
        judgement_button(item(page, "work", b), b, "yes").click()
        label = "評価（要因「要因B」）"
    elif kind == "factor":
        choose(page, b)
        held = hold(page, f"**/nodes/{b}/update")
        factor_field(page, "memo").fill("保存中のメモ")
        factor_save(page).click()
        label = "要因「要因B」の内容"
    elif kind == "title":
        held = hold(page, f"**/analyses/{analysis_id}/title")
        page.locator("[data-title-edit]").click()
        title_input(page).fill("保存中のタイトル")
        title_input(page).press("Enter")
        label = "分析タイトル"
    else:
        held = hold(page, f"**/analyses/{analysis_id}/{kind}")
        step_button(page, 1).click()
        field = "#topEventInput" if kind == "top-event" else "#systemContextInput"
        page.fill(field, "保存中の入力")
        step_panel(page, 1).locator(f'[data-save-button="{kind}"]').click()
        label = "頂上事象" if kind == "top-event" else "参考情報"
    pump(page, lambda: len(held) == 1)
    start_preparing(page, 2)
    status = gen_status(page)
    expect(status).to_contain_text("生成の準備中（二次要因の通常生成）")
    expect(status).to_contain_text(label)
    expect(status).to_contain_text("の保存が終わるのを待っています")
    expect(status.get_by_role("button", name="生成を取りやめる")).to_be_visible()
    expect(generate_button(page, 2)).to_be_disabled()
    held[0].fulfill(status=500, content_type="application/json", body='{"detail": "保存の失敗（検証用）"}')
    wait_phase(page, "idle")
    expect(toast(page, "先に送っていた保存に失敗したため、生成を開始しませんでした（生成の要求は送っていません）", "error")).to_be_visible()
    expect(toast(page, "保存の失敗（検証用）", "error").first).to_be_visible()
    assert requests == []
    assert e2e_server.stub_calls() == []
    expect(generate_button(page, 2)).to_be_enabled()
    if kind == "factor":
        expect(factor_field(page, "memo")).to_have_value("保存中のメモ")
    if kind == "title":
        expect(title_input(page)).to_have_value("保存中のタイトル")


@SINGLE
@pytest.mark.acceptance("E-G09")
def test_E_G09_a_save_in_flight_that_succeeds_lets_the_generation_go_on(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "先行する保存の成功")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = hold(page, f"**/nodes/{b}/update")
    judgement_button(item(page, "work", b), b, "yes").click()  # B becomes a Yes parent
    pump(page, lambda: len(held) == 1)
    start_preparing(page, 2)
    page.wait_for_timeout(300)
    assert requests == []
    held[0].continue_()
    wait_phase(page, "idle")
    assert [r["body"] for r in requests] == [{"parent_id": a}, {"parent_id": b}]


@SINGLE
@pytest.mark.acceptance("E-G09")
def test_E_G09_the_judgement_queue_of_a_factor_is_awaited_to_its_end(page, e2e_server, page_watch):
    page_watch.allow_console_error(r"status of 500")
    analysis_id, a, b, c = setup(e2e_server, "評価の連続保存")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = hold(page, f"**/nodes/{b}/update")
    judgement_button(item(page, "work", b), b, "yes").click()
    pump(page, lambda: len(held) == 1)
    judgement_button(item(page, "work", b), b, "no").click()  # queued behind the Yes
    start_preparing(page, 2)
    held[0].continue_()  # the Yes is saved; the queued No starts
    pump(page, lambda: len(held) == 2)
    page.wait_for_timeout(300)
    assert phase(page) == "preparing" and requests == []
    expect(gen_status(page)).to_contain_text("評価（要因「要因B」）")
    held[1].fulfill(status=500, content_type="application/json", body='{"detail": "評価の失敗（検証用）"}')
    wait_phase(page, "idle")
    assert requests == []
    expect(toast(page, "評価（要因「要因B」）：評価の失敗（検証用）", "error")).to_be_visible()


@SINGLE
@pytest.mark.acceptance("E-G09")
def test_E_G09_cancelling_sends_nothing_later_and_leaves_a_later_generation_alone(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "生成の取りやめ")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = hold(page, f"**/analyses/{analysis_id}/top-event")
    step_button(page, 1).click()
    page.fill("#topEventInput", "保存中の頂上事象")
    step_panel(page, 1).locator('[data-save-button="top-event"]').click()
    pump(page, lambda: len(held) == 1)
    start_preparing(page, 2)
    gen_status(page).get_by_role("button", name="生成を取りやめる").click()
    expect(toast(page, "生成を取りやめました。生成の要求は送っていません（送信済みの保存は取り消されません）", "info")).to_be_visible()
    assert phase(page) == "idle"
    expect(gen_status(page)).to_be_hidden()
    expect(generate_button(page, 2)).to_be_enabled()
    # A second generation, waiting for the same save and for one more.
    held_context = hold(page, f"**/analyses/{analysis_id}/context")
    step_button(page, 1).click()
    page.fill("#systemContextInput", "後の生成が待つ参考情報")
    step_panel(page, 1).locator('[data-save-button="context"]').click()
    pump(page, lambda: len(held_context) == 1)
    step_button(page, 3).click()
    generate_button(page, 2).click()
    pump(page, lambda: phase(page) == "preparing")
    held[0].continue_()  # the cancelled wait ends now: it must not touch the later generation
    page.wait_for_timeout(800)
    assert phase(page) == "preparing" and requests == []
    expect(gen_status(page)).to_contain_text("「参考情報（")
    expect(generate_button(page, 2)).to_be_disabled()
    expect(toast(page, "生成を開始しませんでした", "error")).to_have_count(0)
    held_context[0].continue_()
    wait_phase(page, "idle")
    assert [r["body"] for r in requests] == [{"parent_id": a}]
    assert e2e_server.analysis(analysis_id)["top_event"] == "保存中の頂上事象"  # the save was not cancelled
    expect(log_row(page, a)).to_contain_text("作成 3件")


@SINGLE
@pytest.mark.acceptance("E-G09")
def test_E_G09_cancelling_during_the_automatic_save(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "自動保存中の取りやめ")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = hold(page, f"**/analyses/{analysis_id}/context")
    step_button(page, 1).click()
    page.fill("#systemContextInput", "自動保存される参考情報")
    start_preparing(page, 2)
    pump(page, lambda: len(held) == 1)
    expect(gen_status(page)).to_contain_text("生成前の自動保存：参考情報を保存しています")
    gen_status(page).get_by_role("button", name="生成を取りやめる").click()
    assert phase(page) == "idle"
    held[0].continue_()
    page.wait_for_timeout(800)
    assert requests == []
    assert "自動保存される参考情報" in e2e_server.analysis(analysis_id)["analysis_context"]


@SINGLE
@pytest.mark.acceptance("E-G09")
def test_E_G09_after_10_seconds_a_note_and_no_time_limit(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "10秒を超える待機")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = hold(page, f"**/nodes/{b}/update")
    judgement_button(item(page, "work", b), b, "no").click()
    pump(page, lambda: len(held) == 1)
    start_preparing(page, 2)
    expect(page.locator("[data-gen-status-slow]")).to_have_count(0)
    page.wait_for_timeout(9000)
    expect(page.locator("[data-gen-status-slow]")).to_have_count(0)
    expect(page.locator("[data-gen-status-slow]")).to_contain_text(
        "サーバーが別の処理（生成など）を実行中の可能性があります", timeout=3000)
    page.wait_for_timeout(1500)
    assert phase(page) == "preparing" and requests == []  # still waiting: 10 s is no time limit
    held[0].continue_()
    wait_phase(page, "idle")
    assert [r["body"] for r in requests] == [{"parent_id": a}]


# ----- E-G10 --------------------------------------------------------------------

@pytest.mark.acceptance("E-G10")
def test_E_G10_no_detail_request_waiting_and_read_before_and_only_the_last_choice(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "取得待ち")
    open_edit(page, analysis_id)
    choose(page, a)  # A's details are read before the generation
    gets = detail_gets(page)
    held = start_held(page, analysis_id)
    # B: never read → 取得待ち, nothing of A's details.
    nav_button(page, b).click()
    expect(editor(page)).to_have_attribute("data-node-id", str(b))
    expect(editor(page)).to_have_attribute("data-phase", "waiting")
    expect(factor_status(page)).to_have_text("取得待ち")
    expect(inspector(page).locator("[data-detail-status]")).to_contain_text("生成の完了後に取得します（取得待ち）")
    for key in ("title", "description", "memo"):
        expect(factor_field(page, key)).to_be_disabled()
        expect(factor_field(page, key)).to_have_value("")
    expect(page.locator("[data-inspector-title]")).to_have_text("要因B")  # what the embedded data knows
    # A again: the saved values read before, with their time.
    nav_button(page, a).click()
    expect_editor_ready(page, a)
    expect(factor_field(page, "memo")).to_have_value("Aのメモ")
    expect(inspector(page).locator("[data-detail-read]")).to_contain_text(re.compile(r"生成の前（\d\d:\d\d:\d\d）に読み込んだ保存済みの内容です"))
    # B, then C: the last choice is C.
    nav_button(page, b).click()
    expect(editor(page)).to_have_attribute("data-phase", "waiting")
    nav_button(page, c).click()
    expect(editor(page)).to_have_attribute("data-phase", "waiting")
    page.wait_for_timeout(300)
    assert gets == []
    release(page, held)
    expect_editor_ready(page, c)
    expect(factor_field(page, "description")).to_have_value("Cの説明")
    page.wait_for_timeout(300)
    assert gets == [c]


@SINGLE
@pytest.mark.acceptance("E-G10")
def test_E_G10_a_second_read_keeps_the_draft_and_tells_a_changed_saved_value(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "再取得と下書き")
    open_edit(page, analysis_id)
    choose(page, b)
    held = start_held(page, analysis_id)
    factor_field(page, "memo").fill("生成中の下書き")
    e2e_server.update_node(b, description="別のタブで変えた説明")  # saved elsewhere meanwhile
    gets = detail_gets(page)
    release(page, held)
    pump(page, lambda: gets == [b])
    read_line = inspector(page).locator("[data-detail-read]")
    expect(read_line).to_contain_text("保存済みの値が変わっています")
    expect(factor_field(page, "memo")).to_have_value("生成中の下書き")  # the draft is never overwritten
    expect(factor_field(page, "description")).to_have_value("別のタブで変えた説明")  # not edited: the value read
    expect(factor_status(page)).to_have_text("入力中（未保存）")
    # 保存 sends the draft over the values read again (the other change stays).
    sent = []
    page.on("request", lambda r: sent.append(r.post_data_json) if r.method == "POST" and r.url.endswith(f"/nodes/{b}/update") else None)
    factor_save(page).click()
    expect(factor_status(page)).to_have_text("保存済み")
    assert sent[0]["memo"] == "生成中の下書き" and sent[0]["description"] == "別のタブで変えた説明"
    expect(read_line).to_be_hidden()


@SINGLE
@pytest.mark.acceptance("E-G10")
def test_E_G10_cancel_after_a_second_read_restores_the_values_read(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "再取得と取消")
    open_edit(page, analysis_id)
    choose(page, b)
    held = start_held(page, analysis_id)
    factor_field(page, "memo").fill("取り消す下書き")
    e2e_server.update_node(b, memo="別のタブのメモ")
    release(page, held)
    expect(inspector(page).locator("[data-detail-read]")).to_contain_text("保存済みの値が変わっています")
    expect(factor_field(page, "memo")).to_have_value("取り消す下書き")
    inspector(page).locator("[data-factor-cancel]").click()
    expect(factor_field(page, "memo")).to_have_value("別のタブのメモ")
    expect(factor_status(page)).to_have_text("保存済み")


@SINGLE
@pytest.mark.acceptance("E-G10")
def test_E_G10_an_older_answer_after_the_generation_is_dropped(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "古い応答")
    open_edit(page, analysis_id)
    held = start_held(page, analysis_id)
    nav_button(page, b).click()
    held_get = hold(page, f"**/nodes/{b}")
    release(page, held)
    pump(page, lambda: len(held_get) == 1)  # B's read after the generation, held
    choose(page, c)  # the user chose C meanwhile
    held_get[0].continue_()
    page.wait_for_timeout(500)
    expect(editor(page)).to_have_attribute("data-node-id", str(c))
    expect(factor_field(page, "description")).to_have_value("Cの説明")


@SINGLE
@pytest.mark.acceptance("E-G10")
def test_E_G10_a_failed_second_read_is_not_a_failed_first_read(page, e2e_server, page_watch):
    page_watch.allow_console_error(r"status of 500")
    analysis_id, a, b, c = setup(e2e_server, "再取得の失敗")
    open_edit(page, analysis_id)
    choose(page, a)
    held = start_held(page, analysis_id)
    failing = {"on": True}

    def node(route):
        if failing["on"]:
            route.fulfill(status=500, content_type="application/json", body='{"detail": "取得の失敗（検証用）"}')
        else:
            route.continue_()

    page.route(f"**/nodes/{a}", node)
    page.route(f"**/nodes/{b}", node)
    release(page, held)
    read_line = inspector(page).locator("[data-detail-read]")
    expect(read_line).to_contain_text("生成後に保存済みの内容を取り直せませんでした：取得の失敗（検証用）")
    expect(editor(page)).to_have_attribute("data-phase", "ready")  # still the values read before
    expect(factor_field(page, "memo")).to_have_value("Aのメモ")
    expect(factor_field(page, "memo")).to_be_enabled()
    failing["on"] = False
    inspector(page).get_by_role("button", name="取り直す").click()
    expect(read_line).to_be_hidden()
    # A first read that fails after a generation: 読み込めませんでした.
    failing["on"] = True
    held = start_held(page, analysis_id)
    nav_button(page, b).click()
    expect(editor(page)).to_have_attribute("data-phase", "waiting")
    release(page, held)
    expect(editor(page)).to_have_attribute("data-phase", "failed")
    expect(inspector(page).locator("[data-detail-status]")).to_contain_text("保存されている内容を読み込めませんでした")
    expect(factor_field(page, "memo")).to_be_disabled()


# ----- E-G11 --------------------------------------------------------------------

@pytest.mark.acceptance("E-G11")
def test_E_G11_title_and_inspector_saves_are_held_back_and_the_two_choices(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "生成中の保存の抑止")
    open_edit(page, analysis_id)
    choose(page, b)
    sent = post_paths(page)
    held = start_held(page, analysis_id)
    # The header title: Enter and leaving the input send nothing.
    page.locator("[data-title-edit]").click()
    title_input(page).fill("生成中のタイトル")
    title_input(page).press("Enter")
    error = page.locator("[data-title-error]")
    expect(error).to_have_text("生成中のため保存していません（生成が終わると保存できます）")
    factor_field(page, "memo").click()  # the focus leaves the title
    expect(error).to_be_visible()
    expect(title_input(page)).to_have_value("生成中のタイトル")
    # The inspector: 保存 is off, a stale click sends nothing, the reason stays.
    factor_field(page, "memo").fill("生成中のメモ")
    expect(factor_save(page)).to_be_disabled()
    force_click(factor_save(page))
    expect(inspector(page).locator("[data-factor-message]")).to_contain_text("生成の準備中・生成中・結果の反映中は保存できません")
    # A switch with a draft: two choices and the reason; 編集を続ける keeps it.
    nav_button(page, c).click()
    dialog = leave_dialog(page)
    expect(dialog.locator("[data-generating-reason]")).to_have_text(GENERATING_SWITCH)
    expect(dialog.get_by_role("button", name="保存して移動")).to_have_count(0)
    dialog.get_by_role("button", name="編集を続ける").click()
    expect(editor(page)).to_have_attribute("data-node-id", str(b))
    page.wait_for_timeout(300)
    assert [p for p in sent if not p.endswith("/generate/level/2")] == []
    release(page, held)
    # After the end: the second read keeps the draft; three choices again.
    expect(factor_field(page, "memo")).to_have_value("生成中のメモ")
    nav_button(page, c).click()
    expect(leave_dialog(page).get_by_role("button", name="保存して移動")).to_be_visible()
    leave_dialog(page).get_by_role("button", name="編集を続ける").click()
    title_input(page).press("Enter")
    expect(page.locator("[data-title-text]")).to_have_text("生成中のタイトル")
    assert e2e_server.analysis(analysis_id)["title"] == "生成中のタイトル"


@SINGLE
@pytest.mark.acceptance("E-G11")
def test_E_G11_no_draft_no_question(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "下書きなしの切替")
    open_edit(page, analysis_id)
    choose(page, b)
    held = start_held(page, analysis_id)
    nav_button(page, c).click()
    expect(leave_dialog(page)).to_have_count(0)
    expect(editor(page)).to_have_attribute("data-node-id", str(c))
    release(page, held)


# ----- E-G12 --------------------------------------------------------------------

def expect_back_to_normal(page, analysis_id, a, b):
    wait_phase(page, "idle", timeout=15)
    expect(gen_status(page)).to_be_hidden()
    expect(page.locator("[data-edit-page]")).to_have_attribute("data-generation-phase", "idle")
    expect(generate_button(page, 2)).to_be_enabled()
    expect(judgement_button(item(page, "work", b), b, "yes")).to_be_enabled()
    expect(step_panel(page, 3).locator('[data-action="add"]').first).to_be_enabled()
    expect(leave_link(page)).not_to_have_attribute("aria-disabled", "true")
    dialogs = record_dialogs(page, action="dismiss")
    page.evaluate("() => { window.__pr6Back = true; }")
    page.reload()  # nothing typed and idle: no browser question
    assert dialogs == []


@SINGLE
@pytest.mark.acceptance("E-G12")
@pytest.mark.parametrize("ending", ["success", "partial", "network", "http", "stub-error", "js-error"])
def test_E_G12_every_ending_lifts_the_restrictions(page, e2e_server, page_watch, ending):
    page_watch.allow_console_error(r"status of 50[02]")
    page_watch.allow_console_error(r"net::ERR_FAILED")
    analysis_id, a, b, c = setup(e2e_server, f"終了処理：{ending}")
    e2e_server.update_node(c, user_judgement="yes")  # two parents: A and C
    if ending == "partial":
        e2e_server.set_control(by_parent={"要因C": "error"})
    if ending == "stub-error":
        e2e_server.set_control(mode="error")
    open_edit(page, analysis_id)
    if ending == "network":
        page.route(f"**/analyses/{analysis_id}/generate/level/2", lambda route: route.abort())
    if ending == "http":
        page.route(f"**/analyses/{analysis_id}/generate/level/2",
                   lambda route: route.fulfill(status=502, content_type="text/plain", body="Bad Gateway"))
    if ending == "js-error":
        # An exception of the page's own code while it handles an answer (not
        # the server's): the answer's data throws when it is read.
        page.evaluate("""() => {
          const parse = JSON.parse;
          JSON.parse = function (text, ...rest) {
            const value = parse.call(this, text, ...rest);
            if (value && typeof value === 'object' && 'quality_summary' in value) {
              return new Proxy(value, { get() { throw new Error('E2E: 画面の処理の例外（検証用）'); } });
            }
            return value;
          };
        }""")
    step_button(page, 3).click()
    generate_button(page, 2).click()
    wait_phase(page, "idle", timeout=15)
    categories = {
        "success": ("created", "created"),
        "partial": ("created", "failed"),
        "network": ("network", "network"),
        "http": ("server-error", "server-error"),
        "stub-error": ("failed", "failed"),
    }
    if ending == "js-error":
        # PR-6 review R4: A's request was sent but its answer was not judged
        # (結果不明, not 生成中…), C was never sent (送信していません), nothing
        # is told as success or as 候補0件, and nothing stays 進行中.
        expect(page.locator("[data-gen-log-error]")).to_be_visible()
        expect(toast(page, "生成の処理中に画面のエラーが発生しました", "error")).to_be_visible()
        expect_js_error_rows(page, a, c, restored=False)
        expect(toast(page, "二次要因の通常生成：作成を確認できませんでした（1件の親は結果不明。詳細は生成ログ）",
                     "error", exact=True)).to_be_visible()
        for wrong in ("生成候補がありませんでした", "作成しました"):
            expect(page.locator("#ui-toasts .ui-toast").filter(has_text=wrong)).to_have_count(0)
    else:
        expect(log_row(page, a)).to_have_attribute("data-category", categories[ending][0])
        expect(log_row(page, c)).to_have_attribute("data-category", categories[ending][1])
    expect_back_to_normal(page, analysis_id, a, b)
    if ending == "js-error":
        step_button(page, 3).click()  # after the reload: the same, settled rows (restored)
        expect(page.locator("[data-gen-log-restored]")).to_be_visible()
        expect_js_error_rows(page, a, c, restored=True)


def expect_js_error_rows(page, a, c, *, restored):
    row_a, row_c = log_row(page, a), log_row(page, c)
    expect(row_a).to_have_attribute("data-category", "unknown")
    expect(row_a).to_contain_text("結果不明")
    expect(row_a).to_contain_text("画面の処理中にエラーが発生したため、この親の結果を確認できていません")
    expect(row_a).not_to_contain_text("再読み込みの時点")
    expect(row_c).to_have_attribute("data-category", "skipped")
    expect(row_c).to_contain_text("画面の処理中にエラーが発生したため、送信していません")
    log = page.locator("[data-gen-log]")
    expect(log).not_to_contain_text("生成中…")
    expect(log).not_to_contain_text("待機中")
    expect(log.locator("[data-gen-log-summary]")).to_contain_text("結果不明の親 1件")
    expect(log.locator("[data-gen-log-progress]")).to_have_text(
        "完了していました。" if restored else "完了：2件の親（要求ごとの結果は下の一覧）。")
    expect(page.locator('[data-gen-badge][data-category="running"], [data-gen-badge][data-category="waiting"]')).to_have_count(0)


@SINGLE
@pytest.mark.acceptance("E-G12")
def test_E_G12_a_slow_update_keeps_the_restrictions_until_it_has_ended(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "反映が遅い")
    open_edit(page, analysis_id)
    step_button(page, 3).click()
    held = []

    def page_fetch(route):
        if route.request.resource_type == "fetch":
            held.append(route)
        else:
            route.continue_()

    page.route(re.compile(rf".*/analyses/{analysis_id}$"), page_fetch)
    generate_button(page, 2).click()
    pump(page, lambda: len(held) == 1)
    assert phase(page) == "finishing"
    expect(gen_status(page)).to_contain_text("結果を反映しています")
    page.wait_for_timeout(3000)  # no time limit of its own
    assert phase(page) == "finishing"
    expect(judgement_button(item(page, "work", b), b, "yes")).to_be_disabled()
    leave_link(page).click(force=True)
    expect(toast(page, "生成中のため移動できません", "warning")).to_be_visible()
    held[0].continue_()
    expect_back_to_normal(page, analysis_id, a, b)
    expect(log_row(page, a)).to_contain_text("作成 3件")


@SINGLE
@pytest.mark.acceptance("E-G12")
@pytest.mark.parametrize("typed", [True, False], ids=["with-input", "without-input"])
def test_E_G12_a_failed_update_ends_it_too(page, e2e_server, page_watch, typed):
    page_watch.allow_console_error(r"status of 500")
    analysis_id, a, b, c = setup(e2e_server, "反映の失敗")
    open_edit(page, analysis_id)
    if typed:
        choose(page, b)
        factor_field(page, "memo").fill("入力中の下書き")  # never saved by the generation
    step_button(page, 3).click()
    failures = {"on": True}

    def page_fetch(route):
        if route.request.resource_type == "fetch" and failures["on"]:
            failures["on"] = False
            route.fulfill(status=500, content_type="text/plain", body="error")
        else:
            route.continue_()

    page.route(re.compile(rf".*/analyses/{analysis_id}$"), page_fetch)
    dialogs = record_dialogs(page, action="dismiss")
    generate_button(page, 2).click()
    if typed:
        wait_phase(page, "idle")
        # Typed input kept: no reload, the reason, the log, the parent unchecked.
        expect(toast(page, "最新の表示に更新できませんでした", "error")).to_be_visible()
        expect(page.locator("[data-gen-log-update]")).to_be_visible()
        expect(generate_button(page, 2)).to_be_enabled()
        expect(factor_field(page, "memo")).to_have_value("入力中の下書き")
    else:
        # Nothing typed: the existing reload, without the browser's question;
        # the log was stored before and comes back as the result from before.
        expect(page.locator("[data-gen-log-restored]")).to_be_visible(timeout=15000)
        assert dialogs == []
        assert phase(page) == "idle"
        expect(log_row(page, a)).to_contain_text("作成 3件")
        expect(generate_button(page, 2)).to_be_enabled()


# ----- PR-6 review (R1〜R3) ------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("E-G10")
@pytest.mark.parametrize("order", ["answer-after-the-save", "answer-while-saving"])
def test_E_G10_a_save_is_never_rolled_back_by_an_older_second_read(page, e2e_server, order):
    """R1: the read after a generation goes out with the old memo; the factor
    is saved (by 保存) before its answer arrives — after the save, or while
    the save is in flight. The answer is older than the save: the memo, its
    saved value and the next save keep the saved memo."""
    analysis_id, a, b, c = setup(e2e_server, f"再取得と保存：{order}")
    e2e_server.update_node(b, memo="旧メモ")
    open_edit(page, analysis_id)
    choose(page, b)
    held = start_held(page, analysis_id)
    factor_field(page, "memo").fill("新メモ")
    reads = []

    def read(route):
        if reads:
            route.continue_()
            return
        reads.append((route, route.fetch()))  # read now (the old memo), answered later

    page.route(f"**/nodes/{b}", read)
    held_save = []
    if order == "answer-while-saving":
        page.route(f"**/nodes/{b}/update", lambda route: held_save.append(route) if not held_save else route.continue_())
    gets = detail_gets(page)
    release(page, held)
    pump(page, lambda: len(reads) == 1)
    assert reads[0][1].json()["memo"] == "旧メモ"
    sent = []
    page.on("request", lambda r: sent.append(r.post_data_json)
            if r.method == "POST" and r.url.endswith(f"/nodes/{b}/update") else None)
    factor_save(page).click()
    if order == "answer-while-saving":
        pump(page, lambda: len(held_save) == 1)
        reads[0][0].fulfill(response=reads[0][1])  # the old answer arrives while the save is in flight
        page.wait_for_timeout(300)
        expect(factor_field(page, "memo")).to_have_value("新メモ")
        held_save[0].continue_()
        expect(factor_status(page)).to_have_text("保存済み")
    else:
        expect(factor_status(page)).to_have_text("保存済み")
        assert e2e_server.get_node(b)["memo"] == "新メモ"
        reads[0][0].fulfill(response=reads[0][1])  # the old answer arrives after the save
    page.wait_for_timeout(500)
    expect(factor_field(page, "memo")).to_have_value("新メモ")  # not the older answer's 旧メモ
    expect(factor_status(page)).to_have_text("保存済み")
    pump(page, lambda: len(gets) >= 2)  # read again once the save has ended
    page.wait_for_timeout(300)
    expect(factor_field(page, "memo")).to_have_value("新メモ")
    expect(inspector(page).locator("[data-detail-read]")).to_be_hidden()
    # A later save of another field keeps the saved memo.
    factor_field(page, "description").fill("別の欄の変更")
    factor_save(page).click()
    expect(factor_status(page)).to_have_text("保存済み")
    assert sent[-1]["memo"] == "新メモ" and sent[-1]["description"] == "別の欄の変更"
    assert e2e_server.get_node(b)["memo"] == "新メモ"
    # The cache is the saved one too: shown again during the next generation.
    held = start_held(page, analysis_id)
    nav_button(page, c).click()
    nav_button(page, b).click()
    expect_editor_ready(page, b)
    expect(factor_field(page, "memo")).to_have_value("新メモ")
    expect(factor_field(page, "description")).to_have_value("別の欄の変更")
    release(page, held)


@SINGLE
@pytest.mark.acceptance("E-G10")
def test_E_G10_save_and_go_does_not_cross_a_second_read_either(page, e2e_server, page_watch):
    """R1 through 保存して移動 (the other way into the same save): the
    factor is saved, the reference information fails, so the page stays on
    the factor (編集を続ける) — and then the older read arrives."""
    page_watch.allow_console_error(r"status of 500")
    analysis_id, a, b, c = setup(e2e_server, "再取得と保存して移動")
    e2e_server.update_node(b, memo="旧メモ")
    open_edit(page, analysis_id)
    choose(page, b)
    held = start_held(page, analysis_id)
    factor_field(page, "memo").fill("新メモ")
    reads = []
    page.route(f"**/nodes/{b}", lambda route: route.continue_() if reads else reads.append((route, route.fetch())))
    page.route(f"**/analyses/{analysis_id}/context",
               lambda route: route.fulfill(status=500, content_type="application/json", body='{"detail": "参考情報だけ失敗（検証用）"}'))
    release(page, held)
    pump(page, lambda: len(reads) == 1)
    step_button(page, 1).click()
    page.fill("#systemContextInput", "保存できない参考情報")
    nav_button(page, c).click()
    dialog = leave_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog.locator('[data-save-result="saved"]')).to_have_count(1)  # the factor
    expect(dialog.locator('[data-save-result="failed"]')).to_have_count(1)  # the reference information
    dialog.get_by_role("button", name="編集を続ける").click()
    expect(editor(page)).to_have_attribute("data-node-id", str(b))
    assert e2e_server.get_node(b)["memo"] == "新メモ"
    reads[0][0].fulfill(response=reads[0][1])  # the older answer arrives now
    page.wait_for_timeout(500)
    expect(factor_field(page, "memo")).to_have_value("新メモ")
    expect(factor_status(page)).to_have_text("保存済み")
    sent = []
    page.on("request", lambda r: sent.append(r.post_data_json)
            if r.method == "POST" and r.url.endswith(f"/nodes/{b}/update") else None)
    factor_field(page, "description").fill("別の欄の変更")
    factor_save(page).click()
    expect(factor_status(page)).to_have_text("保存済み")
    assert sent[-1]["memo"] == "新メモ"
    assert e2e_server.get_node(b)["memo"] == "新メモ"


EXPORTS = (
    ("header", lambda page: page.locator('.edit-header a[data-export-format="csv"]')),
    ("step5", lambda page: step_panel(page, 5).locator('a[data-export-format="json"]')),
)


@SINGLE
@pytest.mark.acceptance("E-G04")
def test_E_G04_exports_are_refused_with_modifier_keys_and_the_middle_button(page, e2e_server):
    """R2 (Codex P2 on PR #22): Ctrl / Shift / Alt / Meta with the click and
    the middle button (auxclick) request no export while a generation is
    under way; afterwards the exports work again."""
    analysis_id, a, b, c = setup(e2e_server, "生成中の出力")
    open_edit(page, analysis_id)
    # An export starts a download (Playwright does not route download
    # navigations): every download of every tab, and every tab opened.
    downloads, opened = [], []
    page.on("download", lambda d: downloads.append(d.url))
    page.context.on("page", lambda p: (opened.append(p.url), p.on("download", lambda d: downloads.append(d.url))))
    pages_before = len(page.context.pages)
    held = start_held(page, analysis_id)

    def link(where):
        if where == "header":
            panel = page.locator(".edit-header [data-ui-menu-panel]")
            if not panel.is_visible():
                page.locator(".edit-header [data-ui-menu-button]").click()
        else:
            if page.locator(".edit-header [data-ui-menu-panel]").is_visible():
                page.locator(".edit-header [data-ui-menu-button]").click()  # close the header's menu
            step_button(page, 5).click()
        return dict(EXPORTS)[where](page)

    def chosen(where):
        # A click on an item closes the header's menu, after the click
        # (common/menu.js: a timeout): wait for it, so that the next step
        # starts from a closed menu, never from one about to close (the
        # middle button sends no click: the menu stays open).
        if where == "header":
            expect(page.locator(".edit-header [data-ui-menu-panel]")).to_be_hidden()

    for where, _ in EXPORTS:
        for modifiers in (["Control"], ["Shift"], ["Alt"], ["Meta"]):
            page.evaluate("() => document.querySelectorAll('#ui-toasts .ui-toast__close').forEach((b) => b.click())")
            link(where).click(modifiers=modifiers, force=True)
            expect(toast(page, "生成中のため出力できません", "warning")).to_be_visible()
            chosen(where)
        page.evaluate("() => document.querySelectorAll('#ui-toasts .ui-toast__close').forEach((b) => b.click())")
        link(where).click(button="middle", force=True)
        expect(toast(page, "生成中のため出力できません", "warning")).to_be_visible()
    page.wait_for_timeout(500)
    assert downloads == [] and opened == []
    assert len(page.context.pages) == pages_before  # no tab or window opened
    release(page, held)
    # Back to normal: both ways export again.
    page.evaluate("() => document.querySelectorAll('#ui-toasts .ui-toast__close').forEach((b) => b.click())")
    for where, _ in EXPORTS:
        with page.expect_download() as download:
            link(where).click()
        assert download.value.suggested_filename.startswith(f"fta_{analysis_id}.")
        chosen(where)
    assert len(downloads) == 2 and all("/export/" in url for url in downloads)  # the detector sees exports


@SINGLE
@pytest.mark.acceptance("E-G09")
@pytest.mark.acceptance("E-G10")
@pytest.mark.parametrize("ending", ["cancel", "save-failure", "page-error-before-the-log"])
def test_E_G09_details_held_back_by_a_preparation_are_read_when_it_ends(page, e2e_server, page_watch, ending):
    """R3: a factor never read is chosen while a preparation waits; the
    preparation ends without generating (取りやめ, a failed save before it,
    an exception of the page before the log began): no generation request,
    and the factor's details are read and can be edited."""
    page_watch.allow_console_error(r"status of 500")
    analysis_id, a, b, c = setup(e2e_server, f"準備の終了と詳細：{ending}")
    open_edit(page, analysis_id)
    choose(page, a)
    requests = generation_requests(page)
    held = hold(page, f"**/analyses/{analysis_id}/top-event")
    step_button(page, 1).click()
    page.fill("#topEventInput", "保存中の頂上事象")
    step_panel(page, 1).locator('[data-save-button="top-event"]').click()
    pump(page, lambda: len(held) == 1)
    if ending == "page-error-before-the-log":
        # An exception of the page's own code when the log begins.
        page.evaluate("""() => {
          const replace = Element.prototype.replaceChildren;
          Element.prototype.replaceChildren = function (...nodes) {
            if (this.matches && this.matches('[data-gen-log-slot]') && nodes.length) throw new Error('E2E: 例外（検証用）');
            return replace.apply(this, nodes);
          };
        }""")
    start_preparing(page, 2)
    gets = detail_gets(page)
    nav_button(page, c).click()  # never read: 取得待ち
    expect(editor(page)).to_have_attribute("data-phase", "waiting")
    if ending == "cancel":
        gen_status(page).get_by_role("button", name="生成を取りやめる").click()
        held[0].continue_()
    elif ending == "save-failure":
        held[0].fulfill(status=500, content_type="application/json", body='{"detail": "保存の失敗（検証用）"}')
    else:
        held[0].continue_()
        expect(toast(page, "生成を開始できませんでした（画面の処理でエラーが発生しました。生成の要求は送っていません）",
                     "error")).to_be_visible()
    wait_phase(page, "idle")
    expect_editor_ready(page, c)
    expect(factor_field(page, "description")).to_have_value("Cの説明")
    factor_field(page, "memo").fill("準備の後のメモ")
    expect(factor_status(page)).to_have_text("入力中（未保存）")
    page.wait_for_timeout(300)
    assert gets == [c]
    assert requests == [] and e2e_server.stub_calls() == []
    if ending == "page-error-before-the-log":
        assert page.evaluate("(key) => sessionStorage.getItem(key)", f"fta:genlog:v1:{analysis_id}") is None

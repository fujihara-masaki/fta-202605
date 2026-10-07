"""E2E: leaving the edit screen with unsaved input (PR-4, E-E12・E-E20; plan
5.1, 5.2, 5.9.3, 8.4-4・4-2, J-12).

E-E12 — the three choices for ①'s input on in-page links (一覧へ, the
header's links): 編集を続ける and Esc keep everything and give the focus
back, 破棄して移動 leaves without saving, 保存して移動 saves in order and
leaves only when everything was saved; a partial failure shows each source as
保存済み / 失敗：理由, 再試行 sends the failed one only, and 破棄して移動 then
says that what was saved stays saved. Browser navigation gets the browser's
own confirmation only (reload: dismissed keeps the input, accepted leaves);
nothing unsaved: no question at all.

E-E20 — the save coordinator's contract (js/common/unsaved.js), with a
factor source made by js/pages/edit/factor-source.js (the inspector that will
use it is PR-5: here the test registers it, as PR-5's inspector will):
validation of every source before anything is sent, the order 要因 → 頂上事象 →
参考情報, the target fixed when editing started (whatever is selected later),
a failure that does not stop the other sources, 再試行 for the failed ones
only, 未送信 for sources whose analysis is gone, saves in flight awaited
(after 10 s the dialog says why), and nothing accepted while a generation is
prepared, runs or is finished.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.e2e.edit_helpers import (
    leave_dialog,
    leave_link,
    open_edit,
    post_paths,
    save_status,
    select_button,
    step_button,
    step_panel,
    toast,
    wait_until,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e


def expect_stays(page, e2e_server, analysis_id) -> None:
    """Still the edit screen (its state may be in the hash)."""
    expect(page).to_have_url(re.compile(re.escape(f"{e2e_server.url}/analyses/{analysis_id}") + r"(#.*)?$"))


def results(dialog):
    return dialog.locator("[data-save-results] li")


def result_of(dialog, source_id):
    return dialog.locator(f'[data-save-results] li[data-source-id="{source_id}"]')


# ----- E-E12 --------------------------------------------------------------------

@pytest.mark.acceptance("E-E12")
def test_E_E12_nothing_unsaved_leaves_without_a_question(page, e2e_server):
    analysis_id = e2e_server.create_analysis("確認なしで移動", top_event="頂上")
    open_edit(page, analysis_id)
    dialogs = record_dialogs(page)
    page.fill("#topEventInput", "頂上（変更）")
    page.fill("#topEventInput", " 頂上 ")  # back to the saved value
    leave_link(page).click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert dialogs == []


@pytest.mark.acceptance("E-E12")
def test_E_E12_continue_and_escape_keep_the_input_and_the_focus(page, e2e_server):
    analysis_id = e2e_server.create_analysis("編集を続ける", top_event="頂上")
    open_edit(page, analysis_id)
    sent = post_paths(page)
    page.fill("#systemContextInput", "続けて編集する構成")

    leave_link(page).click()
    dialog = leave_dialog(page)
    expect(dialog).to_be_visible()
    expect(dialog.locator("ul").first).to_have_text("参考情報（システム構成・対象範囲／障害発生時の状況・観測事実）")
    expect(dialog.get_by_role("button", name="編集を続ける")).to_be_focused()
    dialog.get_by_role("button", name="編集を続ける").click()
    expect(dialog).to_have_count(0)
    expect(leave_link(page)).to_be_focused()

    header_link = page.locator(".app-header").get_by_role("link", name="新規作成")
    header_link.click()
    expect(leave_dialog(page)).to_be_visible()
    page.keyboard.press("Escape")
    expect(leave_dialog(page)).to_have_count(0)
    expect(header_link).to_be_focused()
    expect_stays(page, e2e_server, analysis_id)
    expect(page.locator("#systemContextInput")).to_have_value("続けて編集する構成")
    expect(save_status(page, "systemContextInput")).to_have_attribute("data-state", "dirty")
    assert sent == []


@pytest.mark.acceptance("E-E12")
def test_E_E12_discard_and_go(page, e2e_server):
    analysis_id = e2e_server.create_analysis("破棄して移動", top_event="頂上")
    open_edit(page, analysis_id)
    sent = post_paths(page)
    page.fill("#topEventInput", "破棄する頂上事象")
    leave_link(page).click()
    leave_dialog(page).get_by_role("button", name="破棄して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert sent == []
    assert e2e_server.analysis(analysis_id)["top_event"] == "頂上"


@pytest.mark.acceptance("E-E12")
def test_E_E12_save_and_go_saves_in_order_then_leaves(page, e2e_server):
    analysis_id = e2e_server.create_analysis("保存して移動", top_event="頂上")
    open_edit(page, analysis_id)
    sent = post_paths(page)
    page.fill("#incidentContextInput", "保存して移動する状況")
    page.fill("#topEventInput", "保存して移動する頂上事象")
    leave_link(page).click()
    dialog = leave_dialog(page)
    expect(dialog.locator("ul").first.locator("li")).to_have_text(
        ["頂上事象", "参考情報（システム構成・対象範囲／障害発生時の状況・観測事実）"])
    dialog.get_by_role("button", name="保存して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert sent == [f"/analyses/{analysis_id}/top-event", f"/analyses/{analysis_id}/context"]
    stored = e2e_server.analysis(analysis_id)
    assert stored["top_event"] == "保存して移動する頂上事象"
    assert json.loads(stored["analysis_context"])["incident_context"] == "保存して移動する状況"


@pytest.mark.acceptance("E-E12")
def test_E_E12_partial_failure_retry_sends_the_failed_one_only(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("一部の失敗", top_event="頂上")
    open_edit(page, analysis_id)
    page_watch.allow_console_error(r"status of 500")
    sent = post_paths(page)
    route = f"**/analyses/{analysis_id}/context"
    page.route(route, lambda r: r.fulfill(status=500, json={"detail": "E2E: 参考情報だけ失敗させました"}))
    page.fill("#topEventInput", "保存できる頂上事象")
    page.fill("#systemContextInput", "保存できない構成")

    leave_link(page).click()
    dialog = leave_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog.locator("[data-save-results]")).to_contain_text("保存できなかった変更があるため、移動していません。")
    expect(result_of(dialog, "edit-top-event")).to_have_text("頂上事象：保存済み")
    expect(result_of(dialog, "edit-context")).to_have_text(
        "参考情報（システム構成・対象範囲／障害発生時の状況・観測事実）：失敗：E2E: 参考情報だけ失敗させました")
    expect(result_of(dialog, "edit-context")).to_have_attribute("data-save-result", "failed")
    expect(dialog.locator("[data-partial-note]")).to_have_text(
        "保存済みの項目は取り消されません。「破棄して移動」を選ぶと、失敗した項目（未送信を含む）の入力だけが破棄されます。")
    expect(dialog.get_by_role("button", name="再試行")).to_be_focused()
    expect_stays(page, e2e_server, analysis_id)
    # The saved one is saved on the page at once; the failed one stays unsaved.
    expect(save_status(page, "topEventInput")).to_have_attribute("data-state", "saved")
    expect(save_status(page, "systemContextInput")).to_have_attribute("data-state", "dirty")
    assert sent == [f"/analyses/{analysis_id}/top-event", f"/analyses/{analysis_id}/context"]

    # 再試行 still failing: the failed one only.
    dialog.get_by_role("button", name="再試行").click()
    expect(dialog.get_by_role("button", name="再試行")).to_be_enabled()
    wait_until(lambda: len(sent) == 3)
    assert sent[2] == f"/analyses/{analysis_id}/context"

    page.unroute(route)
    dialog.get_by_role("button", name="再試行").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert sent[3:] == [f"/analyses/{analysis_id}/context"]  # the top event was not sent again
    assert json.loads(e2e_server.analysis(analysis_id)["analysis_context"])["system_context"] == "保存できない構成"


@pytest.mark.acceptance("E-E12")
def test_E_E12_discard_after_a_partial_success(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("一部成功の後の破棄", top_event="頂上")
    open_edit(page, analysis_id)
    page_watch.allow_console_error(r"ERR_FAILED")
    page.route(f"**/analyses/{analysis_id}/context", lambda r: r.abort())  # a communication error
    page.fill("#topEventInput", "保存される頂上事象")
    page.fill("#incidentContextInput", "破棄される状況")
    leave_link(page).click()
    dialog = leave_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(result_of(dialog, "edit-context")).to_contain_text("失敗：サーバーに接続できませんでした（通信エラー）")
    expect(dialog.locator("[data-partial-note]")).to_be_visible()
    dialog.get_by_role("button", name="破棄して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    stored = e2e_server.analysis(analysis_id)
    assert stored["top_event"] == "保存される頂上事象"  # not undone
    assert stored["analysis_context"] == ""


@pytest.mark.acceptance("E-E12")
def test_E_E12_browser_navigation_gets_the_browsers_confirmation_only(page, e2e_server):
    analysis_id = e2e_server.create_analysis("ブラウザの確認", top_event="頂上")
    open_edit(page, analysis_id)
    answers = {"action": "dismiss"}
    dialogs = []

    def answer(dialog):
        dialogs.append(dialog.type)
        if answers["action"] == "accept":
            dialog.accept()
        else:
            dialog.dismiss()

    page.on("dialog", answer)
    page.fill("#topEventInput", "再読み込みの前の入力")
    page.evaluate("() => { window.__pr4Mark = 'kept'; window.location.reload(); }")
    wait_until(lambda: dialogs == ["beforeunload"])
    page.wait_for_timeout(300)
    # Dismissed: the page and the input stay; no in-page dialog.
    assert page.evaluate("() => window.__pr4Mark") == "kept"
    expect(page.locator("#topEventInput")).to_have_value("再読み込みの前の入力")
    expect(leave_dialog(page)).to_have_count(0)

    answers["action"] = "accept"
    page.reload()
    assert dialogs == ["beforeunload", "beforeunload"]
    expect(page.locator("#topEventInput")).to_have_value("頂上")  # nothing is stored in the browser
    assert e2e_server.analysis(analysis_id)["top_event"] == "頂上"


@pytest.mark.acceptance("E-E12")
def test_E_E12_title_being_saved_asks_the_browser_too(page, e2e_server):
    analysis_id = e2e_server.create_analysis("タイトルの離脱確認")
    open_edit(page, analysis_id)
    dialogs = record_dialogs(page, action="accept")
    page.locator("[data-title-edit]").click()
    page.reload()  # opened, unchanged
    assert dialogs == []
    page.locator("[data-title-edit]").click()
    page.fill("#analysisTitleInput", "保存していないタイトル")
    page.reload()
    assert dialogs == ["beforeunload"]


# ----- E-E20 --------------------------------------------------------------------

REGISTER_FACTOR = """async ([analysisId, nodeId, title]) => {
  const unsaved = await import('/static/js/common/unsaved.js');
  const { createFactorSource } = await import('/static/js/pages/edit/factor-source.js');
  // A stand-in for PR-5's inspector draft: the factor whose editing started.
  const draft = { title, memo: '契約の確認のメモ' };
  const app = { analysisId, gone: false };
  const source = createFactorSource({
    app, nodeId, label: `要因「${title}」のタイトル・メモ`,
    read: () => draft,
    saved: { title, memo: '' },
    onDiscard: () => { draft.memo = ''; },
  });
  window.__e2eFactorDraft = draft;
  window.__e2eFactorTarget = source.target;
  window.__e2eUnregister = unsaved.registerSource(source);
  return unsaved.targetOf(source);
}"""


def register_factor(page, analysis_id, node_id, title):
    return page.evaluate(REGISTER_FACTOR, [analysis_id, node_id, title])


@pytest.mark.acceptance("E-E20")
def test_E_E20_every_source_is_validated_before_anything_is_sent(page, e2e_server):
    analysis_id = e2e_server.create_analysis("契約：検査", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    open_edit(page, analysis_id)
    sent = post_paths(page)
    register_factor(page, analysis_id, a, "一次要因A")
    page.evaluate("() => { window.__e2eFactorDraft.title = '  '; }")  # invalid: required
    step_button(page, 1).click()
    page.fill("#topEventInput", "検査で止まる頂上事象")
    leave_link(page).click()
    dialog = leave_dialog(page)
    expect(dialog.locator("ul").first.locator("li")).to_have_text(["要因「一次要因A」のタイトル・メモ", "頂上事象"])
    dialog.get_by_role("button", name="保存して移動").click()
    expect(dialog).to_contain_text("入力に不備があるため保存していません（何も送信していません）。")
    expect(dialog).to_contain_text("要因「一次要因A」のタイトル・メモ：要因タイトルは必須です")
    page.wait_for_timeout(300)
    assert sent == []
    expect_stays(page, e2e_server, analysis_id)


@pytest.mark.acceptance("E-E20")
def test_E_E20_order_and_the_target_fixed_when_editing_started(page, e2e_server):
    analysis_id = e2e_server.create_analysis("契約：順番と対象", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    open_edit(page, analysis_id)
    sent = post_paths(page)
    target = register_factor(page, analysis_id, a, "一次要因A")
    assert target == {"analysisId": analysis_id, "nodeId": a}
    # Another factor is selected and the caller's object is changed: the
    # coordinator keeps the target of when editing started.
    select_button(page, "nav", b).click()
    page.evaluate(f"() => {{ window.__e2eFactorTarget.nodeId = {b}; }}")
    step_button(page, 1).click()
    page.fill("#systemContextInput", "順番の確認の構成")
    page.fill("#topEventInput", "順番の確認の頂上事象")
    leave_link(page).click()
    leave_dialog(page).get_by_role("button", name="保存して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert sent == [f"/nodes/{a}/update", f"/analyses/{analysis_id}/top-event", f"/analyses/{analysis_id}/context"]
    assert e2e_server.get_node(a)["memo"] == "契約の確認のメモ"
    assert e2e_server.get_node(b)["memo"] == ""
    assert e2e_server.get_node(a)["user_judgement"] == "unknown"  # the judgement is never sent


@pytest.mark.acceptance("E-E20")
def test_E_E20_a_failure_does_not_stop_the_others_and_retry_sends_it_only(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("契約：一部失敗", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    open_edit(page, analysis_id)
    page_watch.allow_console_error(r"status of 500")
    sent = post_paths(page)
    route = f"**/nodes/{a}/update"
    page.route(route, lambda r: r.fulfill(status=500, json={"detail": "E2E: 要因の保存に失敗させました"}))
    register_factor(page, analysis_id, a, "一次要因A")
    step_button(page, 1).click()
    page.fill("#topEventInput", "続けて保存される頂上事象")
    leave_link(page).click()
    dialog = leave_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(result_of(dialog, f"edit-factor-{a}")).to_have_text(
        "要因「一次要因A」のタイトル・メモ：失敗：E2E: 要因の保存に失敗させました")
    expect(result_of(dialog, "edit-top-event")).to_have_text("頂上事象：保存済み")
    assert sent == [f"/nodes/{a}/update", f"/analyses/{analysis_id}/top-event"]
    assert e2e_server.analysis(analysis_id)["top_event"] == "続けて保存される頂上事象"

    page.unroute(route)
    dialog.get_by_role("button", name="再試行").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert sent[2:] == [f"/nodes/{a}/update"]
    assert e2e_server.get_node(a)["memo"] == "契約の確認のメモ"


@pytest.mark.acceptance("E-E20")
def test_E_E20_sources_of_a_gone_analysis_are_not_sent(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("契約：未送信", top_event="頂上")
    open_edit(page, analysis_id)
    page_watch.allow_console_error(r"status of 404")
    sent = post_paths(page)
    page.route(f"**/analyses/{analysis_id}/top-event",
               lambda r: r.fulfill(status=404, json={"detail": "分析が見つかりません"}))
    page.fill("#topEventInput", "消えた分析の頂上事象")
    page.fill("#systemContextInput", "消えた分析の構成")
    leave_link(page).click()
    dialog = leave_dialog(page)
    dialog.get_by_role("button", name="保存して移動").click()
    expect(result_of(dialog, "edit-top-event")).to_have_text("頂上事象：失敗：分析が見つかりません")
    expect(result_of(dialog, "edit-context")).to_have_attribute("data-save-result", "unsent")
    expect(result_of(dialog, "edit-context")).to_contain_text("未送信：保存先が見つからないため送信していません")
    assert sent == [f"/analyses/{analysis_id}/top-event"]
    expect(dialog.locator("[data-partial-note]")).to_have_count(0)  # nothing was saved


@pytest.mark.acceptance("E-E20")
def test_E_E20_saves_in_flight_are_awaited_and_a_slow_one_is_explained(page, e2e_server):
    analysis_id = e2e_server.create_analysis("契約：送信中の保存", top_event="頂上")
    open_edit(page, analysis_id)
    held = []
    page.route(f"**/analyses/{analysis_id}/top-event", lambda route: held.append(route))
    page.fill("#topEventInput", "送信中の頂上事象")
    step_panel(page, 1).get_by_role("button", name="頂上事象を保存").click()
    wait_until(lambda: len(held) == 1)
    leave_link(page).click()
    waiting = page.get_by_role("dialog", name="保存の完了を待っています")
    expect(waiting).to_be_visible()
    expect(waiting).to_contain_text("サーバーが別の処理（生成など）を実行中の可能性があります。", timeout=12000)
    expect_stays(page, e2e_server, analysis_id)
    held[0].continue_()  # the request was never cancelled; then the page moves
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert e2e_server.analysis(analysis_id)["top_event"] == "送信中の頂上事象"


@pytest.mark.acceptance("E-E20")
def test_E_E20_nothing_is_accepted_while_a_generation_runs(page, e2e_server):
    analysis_id = e2e_server.create_analysis("契約：生成中", top_event="頂上")
    open_edit(page, analysis_id)
    sent = post_paths(page)
    e2e_server.set_stub_mode("delay", delay_seconds=6)
    step_button(page, 2).click()
    step_panel(page, 2).get_by_role("button", name="一次要因を生成").click()
    wait_until(lambda: any(path.endswith("/generate/level/1") for path in sent))
    # The legacy overlay of the 一次 generation (until PR-6) holds the mouse,
    # not the keyboard (B-1): the controls are used by their click events.
    step_button(page, 1).dispatch_event("click")
    page.fill("#topEventInput", "生成中に入力した頂上事象")
    leave_link(page).dispatch_event("click")
    expect(toast(page, "生成の準備中・生成中・結果の反映中は保存できません。", "warning")).to_be_visible()
    expect(leave_dialog(page)).to_have_count(0)
    expect_stays(page, e2e_server, analysis_id)
    # The title is not sent either while the generation runs.
    page.locator("[data-title-edit]").dispatch_event("click")
    expect(page.locator("#analysisTitleInput")).to_be_focused()
    page.locator("#analysisTitleInput").fill("生成中のタイトル")
    page.keyboard.press("Enter")
    expect(page.locator("[data-title-error]")).to_have_text("生成中のため保存していません（生成が終わると保存できます）")
    assert [path for path in sent if path.endswith("/top-event") or path.endswith("/title")] == []

    # Once the generation and its update are done, leaving works again.
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(4, timeout=15000)
    page.wait_for_function("async () => (await import('/static/js/common/unsaved.js')).getGenerationPhase() === 'idle'")
    page.keyboard.press("Enter")  # the title, now
    expect(page.locator("#analysisTitle")).to_have_text("生成中のタイトル")
    leave_link(page).click()
    leave_dialog(page).get_by_role("button", name="保存して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert e2e_server.analysis(analysis_id)["top_event"] == "生成中に入力した頂上事象"

"""E2E: the save coordinator and the generation's preparation and finishing
(PR-4, E-E20; plan 5.9.1 steps 1-4, 5.9.3-1). Regression tests for the
review of PR #20 (f9b68bb):

1. Preparation waits for every judgement save, also one queued for the same
   factor that starts when the earlier one ends: the parents of the
   generation are fixed only after the last one was saved.
2. Leaving waits for a save in flight; a generation that starts meanwhile is
   seen after the wait (and before anything is discarded or saved), so the
   three choices are not offered while the reference information is being
   saved for the generation.
3. The finishing phase lasts until the partial update after the generation
   has succeeded or failed, also when its answer takes longer than 15 s.

The phases are read from js/common/unsaved.js (getGenerationPhase). The
generation itself is the stub's (no real LLM).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import pytest

from tests.e2e.edit_helpers import (
    item,
    judgement_button,
    leave_dialog,
    open_edit,
    post_paths,
    step_button,
    step_panel,
    toast,
)
from tests.e2e.support import expect

pytestmark = [pytest.mark.e2e, pytest.mark.acceptance("E-E20")]

PHASE = "async () => (await import('/static/js/common/unsaved.js')).getGenerationPhase()"
IDLE = "async () => (await import('/static/js/common/unsaved.js')).getGenerationPhase() === 'idle'"
GENERATING = "生成の準備中・生成中・結果の反映中は保存できません。"


def pump_until(page, check, timeout_ms: int = 10000) -> None:
    """Wait for a condition on route callbacks: the page's waits let
    Playwright dispatch them (time.sleep would not)."""
    waited = 0
    while not check():
        assert waited < timeout_ms, "condition not met within the timeout"
        page.wait_for_timeout(50)
        waited += 50


def phase(page) -> str:
    return page.evaluate(PHASE)


def stays(page, e2e_server, analysis_id) -> None:
    expect(page).to_have_url(re.compile(re.escape(f"{e2e_server.url}/analyses/{analysis_id}") + r"(#.*)?$"))


def is_page_fetch(request, analysis_id: int) -> bool:
    return (request.method == "GET" and request.resource_type == "fetch"
            and urlparse(request.url).path == f"/analyses/{analysis_id}")


def test_E_E20_preparation_waits_for_a_queued_judgement_of_the_same_factor(page, e2e_server):
    analysis_id = e2e_server.create_analysis("連続する評価と生成", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    e2e_server.update_node(a, user_judgement="no")
    e2e_server.update_node(b, user_judgement="yes")
    open_edit(page, analysis_id)
    sent = post_paths(page)
    held = []
    page.route(f"**/nodes/{a}/update", lambda route: held.append(route))

    # A: Yes, then No while the Yes is in flight (queued for the same factor).
    judgement_button(item(page, "work", a), a, "yes").click()
    pump_until(page, lambda: len(held) == 1)
    judgement_button(item(page, "work", a), a, "no").click()
    step_button(page, 3).click()
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()

    held[0].continue_()  # the Yes is saved; the queued No starts and is held
    pump_until(page, lambda: len(held) == 2)
    page.wait_for_timeout(800)
    assert [p for p in sent if "/generate/" in p] == []  # nothing generated while the No is in flight
    assert phase(page) == "preparing"

    held[1].continue_()  # the No is saved: only B is a Yes parent now
    expect(page.locator(f'[data-group-parent="{b}"] [data-role="work-item"]')).to_have_count(3)
    calls = e2e_server.stub_calls()
    assert [(c["target_level"], c["parent_factor"]) for c in calls] == [(2, "一次要因B")]
    assert e2e_server.judgement(a) == "no"
    assert [p for p in sent if "/generate/" in p] == [f"/analyses/{analysis_id}/generate/level/2"]


def test_E_E20_a_generation_started_while_leaving_waits_is_not_overridden(page, e2e_server):
    analysis_id = e2e_server.create_analysis("離脱の待機と生成", top_event="頂上")
    open_edit(page, analysis_id)
    held_top, held_context = [], []
    page.route(f"**/analyses/{analysis_id}/top-event", lambda route: held_top.append(route))
    page.route(f"**/analyses/{analysis_id}/context", lambda route: held_context.append(route))

    page.fill("#topEventInput", "保存中の頂上事象")
    step_panel(page, 1).get_by_role("button", name="頂上事象を保存").click()
    pump_until(page, lambda: len(held_top) == 1)
    page.fill("#systemContextInput", "未保存の参考情報")
    # 一覧へ (waiting for the top event), then — before the waiting dialog
    # shows — the 一次 generation, whose preparation waits as well.
    page.evaluate("""() => {
      document.querySelector('.edit-header [data-leave-link]').click();
      document.querySelector('[data-action="legacy-generate"][data-level="1"]').click();
    }""")
    assert phase(page) == "preparing"

    held_top[0].continue_()  # the top event is saved; the generation saves the reference information
    pump_until(page, lambda: len(held_context) == 1)
    expect(toast(page, GENERATING, "warning")).to_be_visible()
    page.wait_for_timeout(500)
    expect(leave_dialog(page)).to_have_count(0)  # no three choices while it is being saved
    stays(page, e2e_server, analysis_id)
    expect(page.locator("#systemContextInput")).to_have_value("未保存の参考情報")

    held_context[0].continue_()
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(4)
    stays(page, e2e_server, analysis_id)
    assert e2e_server.analysis(analysis_id)["top_event"] == "保存中の頂上事象"
    assert "未保存の参考情報" in e2e_server.analysis(analysis_id)["analysis_context"]


@pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])
@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_E_E20_finishing_lasts_until_the_partial_update_has_ended(page, e2e_server, page_watch, viewport, outcome):
    analysis_id = e2e_server.create_analysis("反映中の状態", top_event="頂上")
    open_edit(page, analysis_id)
    page_watch.allow_console_error(r"status of 500")
    held = []

    def hold_page_fetch(route):
        if is_page_fetch(route.request, analysis_id):
            held.append(route)
        else:
            route.continue_()

    page.route(f"**/analyses/{analysis_id}", hold_page_fetch)
    step_button(page, 2).click()
    step_panel(page, 2).get_by_role("button", name="一次要因を生成").click()
    pump_until(page, lambda: len(held) == 1)
    # Typed input (① is not the open step): a failed update does not reload.
    page.evaluate("""() => {
      const field = document.getElementById('incidentContextInput');
      field.value = '入力中の状況';
      field.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    assert phase(page) == "finishing"
    page.wait_for_timeout(16000)  # longer than the former 15 s limit
    assert phase(page) == "finishing"
    page.locator(".edit-header [data-leave-link]").dispatch_event("click")
    expect(toast(page, GENERATING, "warning")).to_be_visible()
    expect(leave_dialog(page)).to_have_count(0)

    if outcome == "success":
        held[0].continue_()
        expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(4)
    else:
        held[0].fulfill(status=500, json={"detail": "E2E：生成後の部分更新に失敗（検証用）"})
        expect(toast(page, "最新の表示に更新できませんでした（E2E：生成後の部分更新に失敗（検証用））。", "error")).to_be_visible()
    page.wait_for_function(IDLE)
    expect(page.locator("#incidentContextInput")).to_have_value("入力中の状況")


def test_E_E20_discard_is_refused_while_a_save_is_in_flight(page, e2e_server):
    analysis_id = e2e_server.create_analysis("送信中の保存と破棄", top_event="頂上")
    open_edit(page, analysis_id)
    held = []
    page.route(f"**/analyses/{analysis_id}/context", lambda route: held.append(route))
    page.fill("#topEventInput", "破棄される頂上事象")
    page.fill("#systemContextInput", "送信中の参考情報")
    page.locator(".edit-header [data-leave-link]").click()
    dialog = leave_dialog(page)
    expect(dialog).to_be_visible()
    # A save of the reference information starts while the dialog is open
    # (as by a generation's preparation): 破棄して移動 must not drop it.
    page.evaluate("""async () => {
      const unsaved = await import('/static/js/common/unsaved.js');
      unsaved.saveSource(unsaved.getSource('edit-context'));
    }""")
    pump_until(page, lambda: len(held) == 1)
    dialog.get_by_role("button", name="破棄して移動").click()
    expect(dialog).to_contain_text("送信中の保存があります。保存が終わってから選んでください")
    stays(page, e2e_server, analysis_id)
    expect(page.locator("#topEventInput")).to_have_value("破棄される頂上事象")

    held[0].continue_()
    expect(page.locator('[data-save-status="systemContextInput"]')).to_have_attribute("data-state", "saved")
    dialog.get_by_role("button", name="破棄して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert "送信中の参考情報" in e2e_server.analysis(analysis_id)["analysis_context"]
    assert e2e_server.analysis(analysis_id)["top_event"] == "頂上"

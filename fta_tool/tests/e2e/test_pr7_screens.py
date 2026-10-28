"""E2E: PR-7 representative screens of a generation, kept for the visual
review (PR-6's improvement idea 案b, 2026-10-20) at the base size and the
two smallest of PR-7 (Edge at 150 %: 1275x609, 1366x768 at 125 %:
1093x500): the operation bar, preparing (a save awaited), the details
waiting for the end of a generation (取得待ち), the log of a partial failure,
and the log after a reload. The log is kept right after the generation
(with its notifications over the lower part of the work area, as the user
sees it) and once the notifications that close by themselves are gone.

In each state the test checks that it was reached and that the controls of
that state are visible, inside the display area and on top (E-V01); the
screens themselves (--e2e-screens) are not part of the verdict: they are
looked at by eye (manual-check-pr7.md 6.2).
"""

from __future__ import annotations

import re

import pytest

from tests.e2e import acceptance
from tests.e2e.edit_helpers import (
    expect_editor_ready,
    factor_save,
    gen_log,
    gen_status,
    hold,
    item,
    judgement_button,
    open_edit,
    pump,
    select_button,
    step_button,
    step_panel,
    wait_phase,
)
from tests.e2e.layout_checks import reach
from tests.e2e.support import expect, save_screenshot

pytestmark = pytest.mark.e2e

CASES = [case for case in acceptance.BASE_CASES if case.label == "1280x800"] + [
    case for case in acceptance.PR7_CASES if case.label in ("edge150-1275x609", "1093x500")]


def keep(page, request, name: str) -> None:
    folder = acceptance.screens_dir(request.config)
    if folder is None:
        return
    slug = re.sub(r"[^\w.-]+", "-", request.node.name)[:90]
    acceptance.add_screenshot(request.node, name, save_screenshot(page, folder / f"{slug}--{name}.png"))


@pytest.mark.acceptance("E-V01")
@pytest.mark.parametrize("viewport", [pytest.param(case, id=case.label) for case in CASES], indirect=True)
def test_E_V01_representative_screens_of_a_generation(page, e2e_server, page_watch, display_case, request):
    page_watch.allow_console_error(r"status of 500")  # the parent that fails on purpose
    analysis_id = e2e_server.create_analysis("代表画面", top_event="ログインできない")
    a = e2e_server.add_level1(analysis_id, "一次要因A（作成される親）")
    b = e2e_server.add_level1(analysis_id, "一次要因B（失敗する親）")
    c = e2e_server.add_child(a, "二次要因C")
    for node in (a, b):
        e2e_server.update_node(node, user_judgement="yes")
    open_edit(page, analysis_id, f"#sel={c}&step=3&view=work")
    expect_editor_ready(page, c)
    generate = step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成")

    # The operation bar.
    reach(generate, name="操作バーの生成")
    reach(step_panel(page, 3).locator('[data-opbar-kinds="2"]'), name="操作バーの説明")
    keep(page, request, "操作バー")

    # Preparing: a judgement save in flight is awaited and named.
    held = hold(page, f"**/nodes/{c}/update")
    judgement_button(item(page, "work", c), c, "no").click()
    pump(page, lambda: len(held) == 1)
    generate.click()
    pump(page, lambda: page.evaluate(
        "async () => (await import('/static/js/common/unsaved.js')).getGenerationPhase()") == "preparing")
    expect(gen_status(page)).to_contain_text("の保存が終わるのを待っています")
    reach(gen_status(page).get_by_role("button", name="生成を取りやめる"), name="生成を取りやめる")
    keep(page, request, "生成の準備中")

    # Running, with a factor chosen meanwhile: its details wait (取得待ち).
    e2e_server.set_control(mode="delay", delay_seconds=2, by_parent={"一次要因B（失敗する親）": "error"})
    held[0].continue_()
    wait_phase(page, "running")
    step_button(page, 2).click()
    select_button(page, "work", b).click()
    expect(page.locator("[data-factor-editor]")).to_have_attribute("data-phase", "waiting")
    reach(gen_status(page).locator("[data-gen-status-text]").first, name="生成中の状態表示")
    reach(factor_save(page), name="保存（取得待ち。押せないが見える）")
    keep(page, request, "生成中・取得待ち")

    # The log of a partial failure (one parent created, one failed).
    wait_phase(page, "idle", timeout=30)
    step_button(page, 3).click()
    log = gen_log(page)
    expect(log.locator('[data-gen-row] [data-category="created"]')).to_have_count(1)
    expect(log.locator('[data-gen-row] [data-category="failed"]')).to_have_count(1)
    reach(log.locator("[data-gen-log-close]"), name="生成ログを閉じる")
    keep(page, request, "部分失敗の生成ログ（終了の直後。通知が重なる）")
    # The success and warning notifications close by themselves (3 s / 6 s, J-24).
    expect(page.locator('#ui-toasts .ui-toast:not([data-toast-type="error"])')).to_have_count(0, timeout=10000)
    keep(page, request, "部分失敗の生成ログ（自動で閉じる通知が消えた後）")

    # After a reload: the log of this tab is shown again, marked as such.
    page.reload()
    expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    expect(gen_log(page).locator("[data-gen-log-restored]")).to_be_visible()
    reach(gen_log(page).locator("[data-gen-log-close]"), name="生成ログを閉じる（再読み込み後）")
    keep(page, request, "再読み込み後の生成ログ")

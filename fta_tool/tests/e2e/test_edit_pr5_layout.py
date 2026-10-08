"""E2E: the controls PR-5 added are visible, readable and not covered
(PR5-LAYOUT) — the part of the visual check that can be automated, as
PR4-LAYOUT for PR-4.

At 1280×800 and the display areas measured on the user's PC (Chrome
1905×945, Edge 1912×914; the same cases and the same size check as
PR3-LAYOUT: only chrome-1905x945 may differ by +1 CSS px, as decided on
2026-10-06), with the three panes still side by side and no horizontal
scroll of the page:
- the inspector's editor: the seven fields with their labels, the save
  status, 保存・取消 (kept at the bottom of the inspector while the editor is
  in view) and a failure message, with an error notification shown;
- the switch dialog (three choices) of R-01;
- the delete dialog (name, counts, the note on when they were counted, the
  draft note, キャンセル・削除する) and the manual-add dialog (place, fields,
  an error, キャンセル・追加する) inside the display area.
Text is at least 12 CSS px. Reading the screens on the user's Windows PC
(Chrome, Edge) stays a short manual check (docs/manual-check-pr5.md), and
zoom levels and narrow widths are PR-7.
"""

from __future__ import annotations

import pytest

from tests.e2e import acceptance
from tests.e2e.edit_helpers import (
    FACTOR_FIELDS,
    add_dialog,
    delete_dialog,
    expect_editor_ready,
    factor_cancel,
    factor_field,
    factor_message,
    factor_save,
    factor_status,
    inspector,
    leave_dialog,
    open_edit,
    select_button,
    step_panel,
    toast,
)
from tests.e2e.support import expect
from tests.e2e.test_edit_page import LAYOUT_CASES, check_layout, display_area
from tests.e2e.test_edit_pr4_layout import check_reachable, inside, readable

pytestmark = [pytest.mark.e2e, pytest.mark.acceptance("PR5-LAYOUT")]

LONG = "長い要因名の表示の確認" * 6


@pytest.mark.parametrize("viewport, allowed",
                         [(size, acceptance.VIEWPORT_ALLOWED.get(case, 0)) for case, size in LAYOUT_CASES.items()],
                         indirect=["viewport"], ids=list(LAYOUT_CASES))
def test_PR5_inspector_editor_and_dialogs_are_visible_and_not_covered(page, e2e_server, viewport, allowed, page_watch):
    analysis_id = e2e_server.create_analysis("PR-5の表示の確認", top_event="頂上事象")
    a = e2e_server.add_level1(analysis_id, LONG, "説明" * 40)
    b = e2e_server.add_child(a, "二次要因B")
    e2e_server.add_child(b, "三次要因C")
    d = e2e_server.add_level1(analysis_id, "一次要因D")
    e2e_server.update_node(a, memo="メモ" * 60, evidence="根拠" * 60, prevention_idea="再発防止" * 40)
    width, height = display_area(page, viewport, allowed, lambda: open_edit(page, analysis_id))
    expect_editor_ready(page, a)
    page_watch.allow_console_error(r"status of 500")

    # An error that stays (J-24) while the editor is used.
    page.route(f"**/nodes/{a}/update",
               lambda route: route.fulfill(status=500, json={"detail": "E2E: 表示の確認のための失敗"}))
    factor_field(page, "memo").fill("表示の確認のメモ")
    factor_save(page).click()
    expect(toast(page, "E2E: 表示の確認のための失敗", "error")).to_be_visible()
    expect(factor_message(page)).to_contain_text("E2E: 表示の確認のための失敗")
    check_layout(page, width, height, [factor_save(page), factor_cancel(page)])
    controls = [factor_status(page), factor_message(page), factor_save(page), factor_cancel(page)]
    controls += [factor_field(page, key) for key in FACTOR_FIELDS]
    controls += [inspector(page).locator(f'label[for="factor-{a}-{key}"]') for key in FACTOR_FIELDS]
    check_reachable(page, width, height, controls)
    for control in controls:
        readable(page, control)
    # 保存・取消 stay at the bottom of the inspector while its fields scroll.
    inspector(page).locator(f'label[for="factor-{a}-title"]').scroll_into_view_if_needed()
    inside(page, factor_save(page), width, height)
    inside(page, factor_cancel(page), width, height)
    page.unroute(f"**/nodes/{a}/update")

    # The switch dialog (three choices).
    select_button(page, "nav", d).click()
    dialog = leave_dialog(page)
    for name in ("編集を続ける", "破棄して移動", "保存して移動"):
        inside(page, dialog.get_by_role("button", name=name), width, height)
        readable(page, dialog.get_by_role("button", name=name))
    readable(page, dialog.locator("ul").first.locator("li").first)
    dialog.get_by_role("button", name="編集を続ける").click()

    # The delete dialog (the draft note included).
    inspector(page).get_by_role("button", name="この要因を削除").click()
    dialog = delete_dialog(page)
    for part in ("[data-delete-title]", "[data-delete-count]", "[data-delete-when]", "[data-delete-draft]"):
        expect(dialog.locator(part)).to_be_visible()
        readable(page, dialog.locator(part))
    for name in ("キャンセル", "削除する"):
        inside(page, dialog.get_by_role("button", name=name), width, height)
        readable(page, dialog.get_by_role("button", name=name))
    dialog.get_by_role("button", name="キャンセル").click()

    # The manual-add dialog, with an error.
    step_panel(page, 2).get_by_role("button", name="手動追加", exact=True).click()
    dialog = add_dialog(page)
    dialog.get_by_role("button", name="追加する").click()
    expect(dialog.locator(".ui-dialog__error")).to_have_text("要因タイトルを入力してください")
    for part in (dialog.locator("[data-add-place]"), page.locator("#add-factor-title"),
                 page.locator("#add-factor-description"), dialog.locator(".ui-dialog__error"),
                 dialog.get_by_role("button", name="キャンセル"), dialog.get_by_role("button", name="追加する")):
        inside(page, part, width, height)
        readable(page, part)
    dialog.get_by_role("button", name="キャンセル").click()
    assert page.evaluate("() => document.documentElement.scrollWidth") <= width
    assert e2e_server.get_node(a)["memo"] != "表示の確認のメモ"

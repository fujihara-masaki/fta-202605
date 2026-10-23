"""E2E: the controls PR-4 added are visible, readable and not covered
(PR4-LAYOUT) — the part of the visual check that can be automated.

At 1280×800 and the display areas measured on the user's PC (Chrome
1905×945, Edge 1912×914; the same cases and the same size check as
PR3-LAYOUT, tests/e2e/test_edit_page.py: only chrome-1905x945 may differ by
+1 CSS px, as decided on 2026-10-06), with the three panes still side by side
and no horizontal scroll of the page:
- the header with a 255-character title, its ✎, the export menu and 一覧へ;
  the open title editor (input, 保存, 取消, the help and an error);
- ① (save statuses, both save buttons, the explanation of the automatic
  save, a failure message);
- ⑤ (the counts, the table of what each format contains, the export links);
- the leave dialog with the three choices, and after a partial failure with
  the results, 再試行, 破棄して移動 and 編集を続ける inside the display area.
Text is at least 12 CSS px. This is a check in the test browser at assumed
and measured sizes; reading the screens on the user's Windows PC (Chrome,
Edge) stays a short manual check (docs/manual-check-pr4.md), and zoom levels
are PR-7.
"""

from __future__ import annotations

import pytest

from tests.e2e import acceptance
from tests.e2e.edit_helpers import leave_dialog, leave_link, open_edit, save_button, step_button, step_panel
from tests.e2e.support import expect
from tests.e2e.test_edit_page import LAYOUT_CASES, check_layout, covered, display_area

pytestmark = [pytest.mark.e2e, pytest.mark.acceptance("PR4-LAYOUT")]

LONG_TITLE = "長い分析タイトル" * 31 + "末尾まで"  # 252 characters


def covered_when_scrolled_to(page, locator) -> bool:
    """Scrolled to the middle of its pane, as a user would to reach it: is
    something else drawn over it? (The shared notifications sit over the
    bottom centre; the panes leave room to scroll above them.)"""
    return not locator.evaluate("""(el) => {
      el.scrollIntoView({ block: 'center', inline: 'nearest' });
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return el === hit || el.contains(hit);
    }""")


def check_reachable(page, width: int, height: int, controls: list) -> None:
    for control in controls:
        expect(control).to_be_visible()
        assert not covered_when_scrolled_to(page, control), control
        box = control.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1, box
    assert page.evaluate("() => document.documentElement.scrollWidth") <= width


def readable(page, locator, minimum: float = 12) -> None:
    size = locator.evaluate("(el) => parseFloat(getComputedStyle(el).fontSize)")
    assert size >= minimum, f"文字が小さすぎる（{size}px）"


def inside(page, locator, width: int, height: int) -> None:
    box = locator.bounding_box()
    assert box is not None
    assert box["x"] >= 0 and box["y"] >= 0, box
    assert box["x"] + box["width"] <= width + 1 and box["y"] + box["height"] <= height + 1, box
    assert not covered(page, locator), locator


@pytest.mark.parametrize("viewport, allowed",
                         [(size, acceptance.VIEWPORT_ALLOWED.get(case, 0)) for case, size in LAYOUT_CASES.items()],
                         indirect=["viewport"], ids=list(LAYOUT_CASES))
def test_PR4_new_controls_are_visible_and_not_covered(page, e2e_server, viewport, allowed, page_watch):
    analysis_id = e2e_server.create_analysis(LONG_TITLE, top_event="頂上事象")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    e2e_server.insert_node(analysis_id, 2, 999999, title="親不在の二次要因")
    width, height = display_area(page, viewport, allowed, lambda: open_edit(page, analysis_id))
    header = page.locator(".edit-header")
    title_controls = [page.locator("#analysisTitle"), page.locator("[data-title-edit]"),
                      header.locator("[data-ui-menu-button]"), header.get_by_role("link", name="一覧へ")]
    check_layout(page, width, height, title_controls)
    for control in title_controls:
        readable(page, control)

    # The title editor, with an error.
    page.locator("[data-title-edit]").click()
    page.fill("#analysisTitleInput", "")
    page.locator("#analysisTitleInput").press("Enter")
    editor = page.locator("[data-title-editor]")
    editor_controls = [page.locator("#analysisTitleInput"), editor.get_by_role("button", name="保存"),
                       editor.get_by_role("button", name="取消"), page.locator("#analysisTitleHelp"),
                       page.locator("[data-title-error]"), header.get_by_role("link", name="一覧へ")]
    check_layout(page, width, height, editor_controls)
    for control in editor_controls:
        readable(page, control)
    editor.get_by_role("button", name="取消").click()

    # ①, with a failure message.
    page_watch.allow_console_error(r"status of 500")
    page.route(f"**/analyses/{analysis_id}/context",
               lambda route: route.fulfill(status=500, json={"detail": "E2E: 表示の確認のための失敗"}))
    step_button(page, 1).click()
    page.fill("#systemContextInput", "失敗させる構成")
    save_button(page, "context").click()
    expect(page.locator('[data-save-message="context"]')).to_contain_text("E2E: 表示の確認のための失敗")
    step1 = [page.locator("[data-autosave-note]").first, page.locator('[data-save-status="topEventInput"]'),
             page.locator('[data-save-status="systemContextInput"]'),
             page.locator('[data-save-status="incidentContextInput"]'),
             save_button(page, "top-event"), save_button(page, "context"),
             page.locator('[data-save-message="context"]')]
    check_layout(page, width, height, [])
    check_reachable(page, width, height, step1)
    for control in step1:
        readable(page, control)

    # ⑤.
    step_button(page, 5).click()
    step5 = [page.locator("[data-summary-table]"), page.locator('[data-summary-row="anomaly"]'),
             page.locator("[data-export-table]"),
             *[step_panel(page, 5).locator(f'a[data-export-format="{fmt}"]') for fmt in ("json", "csv", "markdown")]]
    check_layout(page, width, height, [])
    check_reachable(page, width, height, step5)
    for control in step5:
        readable(page, control)

    # The leave dialog, then its results after a partial failure.
    step_button(page, 1).click()
    page.fill("#topEventInput", "保存される頂上事象")
    leave_link(page).click()
    dialog = leave_dialog(page)
    buttons = [dialog.get_by_role("button", name=name) for name in ("編集を続ける", "破棄して移動", "保存して移動")]
    for button in buttons:
        inside(page, button, width, height)
        readable(page, button)
    buttons[2].click()
    expect(dialog.locator("[data-save-results]")).to_be_visible()
    for name in ("編集を続ける", "破棄して移動", "再試行"):
        inside(page, dialog.get_by_role("button", name=name), width, height)
    expect(dialog.locator("[data-partial-note]")).to_be_visible()
    readable(page, dialog.locator("[data-save-results] li").first)
    assert page.evaluate("() => document.documentElement.scrollWidth") <= width
    assert e2e_server.get_node(a)["title"] == "一次要因A"

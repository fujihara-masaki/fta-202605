"""E2E: ⑤ 確認・出力 and the header's export menu (PR-4, E-E13; plan 8.4-5・6,
UI-04).

- The counts per level (件数・Yes・No・未評価・要確認・直接要因) come from the
  page's data, not from what is shown: a filter that hides factors does not
  change them; a judgement saved on the page and a partial update (a factor
  added elsewhere) change them. Factors with an inconsistent parent link are
  counted in a row of their own. 直接要因 (直接要因評価「直接要因」) is not Yes.
- The table of what each format contains is shown (T-06 checks it against
  the exports); the three export links of ⑤ and the header menu download the
  same files as the export URLs.
- The header menu is the list's: button with aria-expanded, keyboard, Esc
  back to the button, download links. Downloading while ① has unsaved input
  asks nothing (no in-page dialog, no browser confirmation) and keeps the
  input. (A title being edited is saved when the focus leaves it for the
  menu, by design: E-E11.)
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.edit_helpers import (
    item,
    judgement_button,
    leave_dialog,
    open_edit,
    step_button,
    step_panel,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = [pytest.mark.e2e, pytest.mark.acceptance("E-E13")]

COLUMNS = ("total", "yes", "no", "unknown", "warning", "direct")


def counts(page, row: str) -> list[str]:
    return [page.locator(f'[data-summary-row="{row}"] [data-summary-cell="{c}"]').inner_text() for c in COLUMNS]


def summary_analysis(e2e_server):
    analysis_id = e2e_server.create_analysis("⑤の件数", top_event="頂上")
    a = e2e_server.add_level1(analysis_id, "一次要因A")
    b = e2e_server.add_level1(analysis_id, "一次要因B")
    c = e2e_server.add_child(a, "二次要因C")
    e2e_server.update_node(a, user_judgement="yes", direct_cause_status="direct")
    e2e_server.update_node(b, direct_cause_status="likely")  # 可能性高: not 直接要因
    e2e_server.set_warning(c, "既存要因に類似")
    orphan = e2e_server.insert_node(analysis_id, 2, 999999, title="親不在の二次要因", judgement="no")
    return analysis_id, {"a": a, "b": b, "c": c, "orphan": orphan}


def test_E_E13_counts_come_from_the_data_and_follow_judgements_and_updates(page, e2e_server):
    analysis_id, ids = summary_analysis(e2e_server)
    open_edit(page, analysis_id)
    step_button(page, 5).click()
    expect(page.locator('[data-summary-row="1"] [data-summary-cell="total"]')).to_have_text("2")
    assert counts(page, "1") == ["2", "1", "0", "1", "0", "1"]
    assert counts(page, "2") == ["1", "0", "0", "1", "1", "0"]
    assert counts(page, "3") == ["0"] * 6
    assert counts(page, "anomaly") == ["1", "0", "1", "0", "0", "0"]
    assert counts(page, "all") == ["4", "1", "1", "2", "1", "1"]
    expect(page.locator("[data-summary-anomaly-note]")).to_be_visible()

    # A filter that hides factors does not change the counts.
    page.fill("#edit-filter-text", "一次要因A")
    page.wait_for_timeout(200)
    assert counts(page, "1") == ["2", "1", "0", "1", "0", "1"]
    page.fill("#edit-filter-text", "")

    # A judgement saved on the page: Yes for B (its 直接要因評価 stays 可能性高).
    step_button(page, 2).click()
    judgement_button(item(page, "work", ids["b"]), ids["b"], "yes").click()
    expect(item(page, "work", ids["b"])).to_have_attribute("data-judgement", "yes")
    step_button(page, 5).click()
    expect(page.locator('[data-summary-row="1"] [data-summary-cell="yes"]')).to_have_text("2")
    assert counts(page, "1") == ["2", "2", "0", "0", "0", "1"]
    assert counts(page, "all") == ["4", "2", "1", "1", "1", "1"]

    # A partial update after a change elsewhere: a third 一次要因, 直接要因.
    d = e2e_server.add_level1(analysis_id, "一次要因D")
    e2e_server.update_node(d, direct_cause_status="direct", user_judgement="no")
    page.evaluate("() => window.ftaEditBridge.refresh({})")
    expect(page.locator('[data-summary-row="1"] [data-summary-cell="total"]')).to_have_text("3")
    assert counts(page, "1") == ["3", "2", "1", "0", "0", "2"]
    assert counts(page, "all") == ["5", "2", "2", "1", "1", "2"]
    expect(step_button(page, 2)).to_contain_text("3件・未評価0")


def test_E_E13_export_table_and_links_download_the_exports(page, e2e_server):
    analysis_id, _ = summary_analysis(e2e_server)
    open_edit(page, analysis_id)
    step_button(page, 5).click()
    table = page.locator("[data-export-table]")
    expect(table).to_be_visible()
    expect(table.locator('[data-export-item="title"] td')).to_have_text(
        ["あり", "なし", "なし（見出しは固定の「FTA分析結果」）"])
    expect(table.locator('[data-export-item="description"] td[data-format="markdown"]')).to_have_text("なし")
    expect(table.locator('[data-export-item="context"] td[data-format="csv"]')).to_have_text("なし")

    for fmt, name, suffix in (("json", "JSON", "json"), ("csv", "CSV", "csv"), ("markdown", "Markdown", "md")):
        link = step_panel(page, 5).locator(f'a[data-export-format="{fmt}"]')
        expect(link).to_have_attribute("href", f"/analyses/{analysis_id}/export/{fmt}")
        expect(link).to_have_attribute("download", "")
        expect(link).to_contain_text(name)
        with page.expect_download() as download_info:
            link.click()
        assert download_info.value.suggested_filename == f"fta_{analysis_id}.{suffix}"
        with open(download_info.value.path(), "rb") as handle:
            assert handle.read() == e2e_server.export(analysis_id, fmt)


def test_E_E13_header_menu_is_the_lists_and_downloads_ask_nothing(page, e2e_server):
    analysis_id, _ = summary_analysis(e2e_server)
    open_edit(page, analysis_id)
    dialogs = record_dialogs(page)
    header = page.locator(".edit-header")
    button = header.locator("[data-ui-menu-button]")
    panel = header.locator("[data-ui-menu-panel]")
    expect(button).to_have_attribute("aria-expanded", "false")

    button.focus()
    page.keyboard.press("Enter")
    expect(panel).to_be_visible()
    links = panel.locator("a")
    expect(links).to_have_count(3)
    for index, fmt in enumerate(("json", "csv", "markdown")):
        expect(links.nth(index)).to_have_attribute("href", f"/analyses/{analysis_id}/export/{fmt}")
        expect(links.nth(index)).to_have_attribute("download", "")
    page.keyboard.press("Tab")
    expect(links.nth(0)).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(links.nth(1)).to_be_focused()
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    expect(button).to_be_focused()

    # Unsaved ①: downloading asks nothing and keeps the input.
    step_button(page, 1).click()
    page.fill("#topEventInput", "出力中も保持する頂上事象")
    for name, fmt, suffix in (("JSON", "json", "json"), ("CSV", "csv", "csv"), ("Markdown", "markdown", "md")):
        button.click()
        with page.expect_download() as download_info:
            panel.get_by_role("link", name=re.compile(name)).click()
        assert download_info.value.suggested_filename == f"fta_{analysis_id}.{suffix}"
        with open(download_info.value.path(), "rb") as handle:
            assert handle.read() == e2e_server.export(analysis_id, fmt)
    step_button(page, 5).click()
    with page.expect_download():
        step_panel(page, 5).locator('a[data-export-format="csv"]').click()
    page.wait_for_timeout(300)
    assert dialogs == []
    expect(leave_dialog(page)).to_have_count(0)
    expect(page).to_have_url(re.compile(re.escape(f"{e2e_server.url}/analyses/{analysis_id}") + r"(#.*)?$"))
    expect(page.locator("#topEventInput")).to_have_value("出力中も保持する頂上事象")

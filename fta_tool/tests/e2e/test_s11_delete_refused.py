"""E2E: the server's S-11 refusals as the existing screens show them
(docs/pr8-s11-s12-options.md section 6). S11-DELETE-REFUSED.

The screens are unchanged; what changed is the server's answer (HTTP 409 and
a Japanese reason instead of removing factors of another analysis with 200,
or failing with 500 on a loop). The data the server refuses is written
straight into the E2E server's temporary database (tests/e2e/support.py
insert_node / set_parent) — on the edit screen after the page was shown,
which is the case the screen's own check (判断2, made on the data as
fetched) cannot see. The user's database is never used.

* S11-DELETE-REFUSED  a refused delete shows the server's reason in the
         existing dialog — the list's 「分析を削除しますか？」 and the edit
         screen's 「要因を削除しますか？」 — after 「削除できませんでした：」;
         the row / the factor and its draft stay, and the database does not
         change (every column of every row). A factor of another analysis
         below, and a loop, are each shown; a normal delete still works.
"""

from __future__ import annotations

import pytest

from tests.e2e.edit_helpers import (
    choose,
    delete_dialog,
    expect_editor_ready,
    factor_cancel,
    factor_field,
    inspector,
    open_edit,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = pytest.mark.e2e

SINGLE = pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])

LIST_FOREIGN = ("削除できませんでした：この分析の要因の子孫に別の分析の要因が1件含まれます。"
                "削除すると別の分析の要因も削除されるため、何も削除していません。")
LIST_CYCLE = ("削除できませんでした：この分析と一緒に削除される範囲で、親子関係が循環しています（親子関係の不整合）。"
              "安全に削除できないため、何も削除していません。")
NODE_FOREIGN = ("削除できませんでした：この要因の子孫に別の分析の要因が1件含まれます。"
                "削除すると別の分析の要因も削除されるため、何も削除していません。")
NODE_CYCLE = ("削除できませんでした：この要因と一緒に削除される範囲で、親子関係が循環しています（親子関係の不整合）。"
              "安全に削除できないため、何も削除していません。")


def dump(e2e_server) -> tuple:
    """Every row of both tables, every column."""
    return (tuple(e2e_server.query("SELECT * FROM analyses ORDER BY id")),
            tuple(e2e_server.query("SELECT * FROM nodes ORDER BY id")))


def list_row(page, analysis_id):
    return page.locator(f'tr[data-analysis-id="{analysis_id}"]')


# ----- S11-DELETE-REFUSED ----------------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("S11-DELETE-REFUSED")
def test_S11_list_delete_refused_shows_the_reason_and_changes_nothing(page, page_watch, e2e_server):
    page_watch.allow_console_error(r"status of 409")
    x = e2e_server.create_analysis("別分析の要因が下にある分析", top_event="頂上X")
    x1 = e2e_server.add_level1(x, "Xの一次要因")
    y = e2e_server.create_analysis("下にぶら下がる分析", top_event="頂上Y")
    e2e_server.insert_node(y, 2, x1, title="Xの要因を親にするYの要因")
    z = e2e_server.create_analysis("循環を含む分析", top_event="頂上Z")
    z1 = e2e_server.add_level1(z, "Zの一次要因")
    z2 = e2e_server.add_child(z1, "Zの二次要因")
    e2e_server.set_parent(z1, z2)  # z1 ⇄ z2
    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    dialogs = record_dialogs(page)
    before = dump(e2e_server)

    for analysis_id, reason in ((x, LIST_FOREIGN), (z, LIST_CYCLE)):
        list_row(page, analysis_id).locator('[data-action="delete"]').click()
        dialog = page.get_by_role("dialog", name="分析を削除しますか？")
        dialog.get_by_role("button", name="削除する").click()
        expect(dialog.locator(".ui-dialog__error")).to_have_text(reason)
        expect(dialog.get_by_role("button", name="キャンセル")).to_be_focused()
        dialog.get_by_role("button", name="キャンセル").click()
        expect(dialog).to_have_count(0)
        expect(list_row(page, analysis_id)).to_have_count(1)
        assert dump(e2e_server) == before
    expect(page.locator("[data-analysis-count]")).to_have_text("3")
    assert dialogs == []

    # A normal analysis is still deleted from the same list.
    list_row(page, y).locator('[data-action="delete"]').click()
    page.get_by_role("dialog", name="分析を削除しますか？").get_by_role("button", name="削除する").click()
    expect(list_row(page, y)).to_have_count(0)
    assert e2e_server.analysis(y) is None and e2e_server.node_count(y) == 0
    assert e2e_server.analysis(x) is not None and e2e_server.node_ids(x) == {x1}


@SINGLE
@pytest.mark.acceptance("S11-DELETE-REFUSED")
def test_S11_edit_delete_refused_after_the_page_was_shown_keeps_the_draft(page, page_watch, e2e_server):
    page_watch.allow_console_error(r"status of 409")
    other = e2e_server.create_analysis("別の分析", top_event="別")
    analysis_id = e2e_server.create_analysis("表示の後に変わった分析", top_event="頂上")
    p = e2e_server.add_level1(analysis_id, "一次要因P")
    q = e2e_server.add_child(p, "二次要因Q")
    r = e2e_server.add_level1(analysis_id, "一次要因R")
    r2 = e2e_server.add_child(r, "二次要因R2")
    open_edit(page, analysis_id, f"#sel={p}&step=2&view=work")
    expect_editor_ready(page, p)
    dialogs = record_dialogs(page)

    # After the page was shown: a factor of another analysis below Q, and R ⇄ R2.
    e2e_server.insert_node(other, 3, q, title="表示の後にQの下へ入った別分析の要因")
    e2e_server.set_parent(r, r2)
    before = dump(e2e_server)

    factor_field(page, "memo").fill("削除の前の下書き")
    delete = inspector(page).get_by_role("button", name="この要因を削除")
    expect(delete).to_be_enabled()  # the screen's check saw the data before the change
    delete.click()
    dialog = delete_dialog(page)
    dialog.get_by_role("button", name="削除する").click()
    expect(dialog.locator(".ui-dialog__error")).to_have_text(NODE_FOREIGN)
    dialog.get_by_role("button", name="キャンセル").click()
    expect(dialog).to_have_count(0)
    expect(factor_field(page, "memo")).to_have_value("削除の前の下書き")
    assert dump(e2e_server) == before

    factor_cancel(page).click()  # the draft of P is dropped by the user (取消)
    expect(factor_field(page, "memo")).to_have_value("")
    choose(page, r)
    inspector(page).get_by_role("button", name="この要因を削除").click()
    dialog = delete_dialog(page)
    dialog.get_by_role("button", name="削除する").click()
    expect(dialog.locator(".ui-dialog__error")).to_have_text(NODE_CYCLE)
    dialog.get_by_role("button", name="キャンセル").click()
    assert dump(e2e_server) == before
    assert dialogs == []
    assert {p, q, r, r2} <= e2e_server.node_ids(analysis_id)

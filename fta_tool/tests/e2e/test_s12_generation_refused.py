"""E2E: the server's S-12 refusal as the existing edit screen shows it
(docs/pr8-s11-s12-options.md section 6). S12-GEN-REFUSED.

The screen is unchanged and never asks for a parent it knows to be
inconsistent (判断3); a parent whose links loop after the page was shown is
the case it cannot see. Until S-12 such a request never ended (the stub
server would not answer); now it ends at once in the existing failure form.
The loop is written straight into the E2E server's temporary database; the
AI is the E2E stub (stub_calls.jsonl), the user's database is never used.

* S12-GEN-REFUSED  the log row of that parent is 「処理失敗」 with the
         server's message, the AI is not called for it, nothing is created
         below it, the normal parent is generated as before, and the
         screen's controls come back.
"""

from __future__ import annotations

import pytest

from tests.e2e.edit_helpers import (
    generate_button,
    log_row,
    open_edit,
    step_button,
    toast,
    wait_phase,
)
from tests.e2e.support import expect

pytestmark = pytest.mark.e2e

SINGLE = pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])


# ----- S12-GEN-REFUSED ----------------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("S12-GEN-REFUSED")
def test_S12_generation_for_a_parent_looping_after_the_page_was_shown_fails_at_once(page, e2e_server):
    analysis_id = e2e_server.create_analysis("生成の後に変わった分析", top_event="頂上")
    good = e2e_server.add_level1(analysis_id, "正常な一次要因")
    looping = e2e_server.add_level1(analysis_id, "表示の後に自己参照になる一次要因")
    for node_id in (good, looping):
        e2e_server.update_node(node_id, user_judgement="yes")
    open_edit(page, analysis_id)
    e2e_server.set_parent(looping, looping)  # after the page was shown
    before_ids = e2e_server.node_ids()

    step_button(page, 3).click()
    generate_button(page, 2).click()
    wait_phase(page, "idle", timeout=20)

    row = log_row(page, looping)
    expect(row).to_have_attribute("data-category", "failed")
    expect(row).to_contain_text("処理失敗")
    expect(row).to_contain_text(
        "指定された親要因「表示の後に自己参照になる一次要因」は親子関係に不整合があるため（自分自身を親にしている要因があります）、"
        "この親の下には要因を生成できません。AIは呼び出さず、要因は作成していません。")
    expect(log_row(page, good)).to_have_attribute("data-category", "created")
    expect(toast(page, "二次要因の通常生成：", "warning")).to_be_visible()
    # The AI was asked for the normal parent only; nothing below the looping one.
    calls = e2e_server.stub_calls()
    assert [c["parent_factor"] for c in calls] == ["正常な一次要因"]
    created = e2e_server.node_ids() - before_ids
    assert created and {row[0] for row in e2e_server.query(
        "SELECT parent_id FROM nodes WHERE id IN (%s)" % ",".join(map(str, created)))} == {good}
    # The controls are back after the generation.
    expect(generate_button(page, 2)).to_be_enabled()

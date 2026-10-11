"""E2E: the generation log kept for the tab (PR-6, E-G06; J-03, plan 5.9.2).

sessionStorage, key fta:genlog:v1:<analysis id>, the latest generation of
each analysis: ids, categories, counts, reasons and times only — never a
factor's text or a draft. Restored after a reload of the same tab with its
analysis and time and 「再読み込み前の結果」, a parent no longer there noted,
removed by 閉じる; nothing of the generation's restrictions comes back.
Other analyses never show it. Other tabs, by the way they are opened:
  * a new page without an opener (typing the address, a new window): its
    sessionStorage is empty — no log;
  * window.open with an opener: the browser copies the sessionStorage (it
    is inherited), but the log carries the mark of the tab that made it
    (window.name), so the copy is not shown (and is dropped there).
  Duplicating a tab in the browser's menu copies the storage and may copy
  window.name too: not covered here (manual check, manual-check-pr6.md).
Storage that throws, is full or holds broken data: the page and generation
go on; the log says when it cannot be kept.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.e2e.edit_helpers import (
    choose,
    factor_field,
    gen_badge,
    gen_log,
    gen_status,
    generate_button,
    hold,
    log_row,
    open_edit,
    phase,
    pump,
    step_button,
    wait_phase,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = [pytest.mark.e2e, pytest.mark.acceptance("E-G06")]

SINGLE = pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])
KEY = "fta:genlog:v1:{}"


def setup(e2e_server, title="生成ログの保持"):
    analysis_id = e2e_server.create_analysis(title, top_event="頂上事象の本文", system_context="参考情報の本文")
    a = e2e_server.add_level1(analysis_id, "親Aの本文タイトル")
    b = e2e_server.add_level1(analysis_id, "親Bの本文タイトル")
    e2e_server.update_node(a, user_judgement="yes", description="親Aの説明の本文")
    e2e_server.update_node(b, user_judgement="yes")
    return analysis_id, a, b


def generate(page, level=2):
    step_button(page, level + 1).click()
    generate_button(page, level).click()
    wait_phase(page, "idle", timeout=15)


def stored(page, analysis_id):
    return page.evaluate("(key) => sessionStorage.getItem(key)", KEY.format(analysis_id))


def test_E_G06_reload_restores_the_result_without_any_text_or_draft(page, e2e_server):
    analysis_id, a, b = setup(e2e_server)
    open_edit(page, analysis_id)
    choose(page, a)
    factor_field(page, "memo").fill("下書きの本文")
    generate(page)
    raw = stored(page, analysis_id)
    value = json.loads(raw)
    assert set(value) == {"v", "analysisId", "tab", "startedAt", "endedAt", "level", "kind", "status",
                          "excludedParents", "update", "jsError", "rows"}
    assert value["analysisId"] == analysis_id and value["level"] == 2 and value["kind"] == "normal"
    assert value["status"] == "done" and value["update"] == "applied"
    assert [(row["parentId"], row["state"], row["created"]) for row in value["rows"]] == [(a, "created", 3), (b, "created", 3)]
    titles = [row[0] for row in e2e_server.query("SELECT title FROM nodes WHERE analysis_id = ?", (analysis_id,))]
    for text in titles + ["下書きの本文", "頂上事象の本文", "参考情報の本文", "親Aの説明の本文", "生成ログの保持"]:
        assert text not in raw, text

    record_dialogs(page, action="accept")  # the draft asks before the reload
    page.reload()
    expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    log = gen_log(page)
    expect(log.locator("[data-gen-log-restored]")).to_have_text(
        "再読み込み前の結果です。件数は実行時点の値です（現在の要因の状態とは異なることがあります）。")
    expect(log.locator("[data-gen-log-when]")).to_have_text(
        re.compile(r"^この分析で \d{4}-\d\d-\d\d \d\d:\d\d に実行した生成の結果$"))
    expect(log).to_contain_text("生成ログ：二次要因の通常生成")
    expect(log_row(page, a)).to_contain_text("作成 3件")
    expect(log_row(page, a)).to_contain_text("親：「親Aの本文タイトル」")  # the name comes from the page's data
    step_button(page, 3).click()
    expect(gen_badge(page, a)).to_have_text("前回：作成 3件")
    # Nothing of a generation comes back.
    assert phase(page) == "idle"
    expect(gen_status(page)).to_be_hidden()
    expect(generate_button(page, 2)).to_be_enabled()
    expect(log.get_by_role("button", name="閉じる")).to_be_enabled()


@SINGLE
def test_E_G06_a_reload_during_a_generation_restores_no_running_state(page, e2e_server):
    analysis_id, a, b = setup(e2e_server, "実行中の再読み込み")
    open_edit(page, analysis_id)
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/2")
    step_button(page, 3).click()
    generate_button(page, 2).click()
    pump(page, lambda: len(held) == 1)
    dialogs = record_dialogs(page, action="accept")
    page.reload()
    assert dialogs == ["beforeunload"]
    expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    assert phase(page) == "idle"
    expect(gen_status(page)).to_be_hidden()
    expect(generate_button(page, 2)).to_be_enabled()
    log = gen_log(page)
    expect(log.locator("[data-gen-log-progress]")).to_have_text(
        "再読み込みの時点では完了していませんでした（その後の結果は確認できていません）。")
    expect(log_row(page, a)).to_have_attribute("data-category", "unknown")
    expect(log_row(page, a)).to_contain_text("結果不明")
    expect(log_row(page, b)).to_have_attribute("data-category", "unknown")
    expect(log).not_to_contain_text("生成中…")
    assert e2e_server.stub_calls() == []


def test_E_G06_other_analyses_and_other_tabs(page, e2e_server):
    analysis_id, a, b = setup(e2e_server, "分析1")
    other = e2e_server.create_analysis("分析2", top_event="頂上")
    open_edit(page, analysis_id)
    generate(page)
    expect(gen_log(page)).to_be_visible()
    # Another analysis in the same tab: not shown.
    open_edit(page, other)
    expect(gen_log(page)).to_have_count(0)
    # Back to the first one in the same tab: shown again (restored, in ③).
    open_edit(page, analysis_id)
    step_button(page, 3).click()
    expect(gen_log(page).locator("[data-gen-log-restored]")).to_be_visible()

    # A new page without an opener (as an address typed in a new tab): the
    # storage is not inherited.
    fresh = page.context.new_page()
    try:
        fresh.goto(f"{e2e_server.url}/analyses/{analysis_id}")
        expect(fresh.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
        assert stored(fresh, analysis_id) is None
        expect(fresh.locator("[data-gen-log]")).to_have_count(0)
    finally:
        fresh.close()

    # window.open with an opener: the storage IS copied, the log is not shown.
    with page.expect_popup() as popup_info:
        page.evaluate("(url) => { window.open(url); }", f"/analyses/{analysis_id}")
    popup = popup_info.value
    try:
        expect(popup.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
        copied = popup.evaluate("""(key) => {
          // The page has read it already; the copy the browser made is dropped there.
          return sessionStorage.getItem(key);
        }""", KEY.format(analysis_id))
        assert copied is None
        expect(popup.locator("[data-gen-log]")).to_have_count(0)
        inherited = popup.evaluate("() => sessionStorage.getItem('fta:edit:v1:' + location.pathname.split('/').pop()) !== null")
        assert inherited  # the screen state of the opener was copied: the storage was inherited
    finally:
        popup.close()
    # The opener still has its own log.
    page.reload()
    step_button(page, 3).click()
    expect(gen_log(page).locator("[data-gen-log-restored]")).to_be_visible()


@SINGLE
def test_E_G06_a_parent_no_longer_there_is_noted_and_close_removes_it(page, e2e_server):
    analysis_id, a, b = setup(e2e_server, "閉じる")
    open_edit(page, analysis_id)
    generate(page)
    e2e_server.delete_node(b)
    page.reload()
    row = log_row(page, b)
    expect(row).to_contain_text("現在はこの親が見つかりません")
    expect(row).to_contain_text(f"ID {b}")
    expect(row).to_contain_text("作成 3件")  # the count of that time
    expect(log_row(page, a)).not_to_contain_text("現在はこの親が見つかりません")
    gen_log(page).get_by_role("button", name="閉じる").click()
    expect(gen_log(page)).to_have_count(0)
    expect(page.locator("[data-gen-badge]")).to_have_count(0)
    assert stored(page, analysis_id) is None
    page.reload()
    expect(page.locator('.edit-steps [aria-current="step"]')).to_have_count(1)
    expect(gen_log(page)).to_have_count(0)


QUOTA = """() => {
  const set = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key, value) {
    if (String(key).startsWith('fta:genlog:')) throw new DOMException('full', 'QuotaExceededError');
    return set.call(this, key, value);
  };
}"""
BLOCKED = """() => {
  Object.defineProperty(window, 'sessionStorage', { get() { throw new DOMException('blocked', 'SecurityError'); } });
}"""


@SINGLE
@pytest.mark.parametrize("trouble", ["quota", "blocked", "broken"])
def test_E_G06_storage_that_cannot_be_used_keeps_the_page_working(page, e2e_server, trouble):
    analysis_id, a, b = setup(e2e_server, f"保存領域：{trouble}")
    if trouble == "quota":
        page.add_init_script(f"({QUOTA})()")
    elif trouble == "blocked":
        page.add_init_script(f"({BLOCKED})()")
    else:
        page.goto("/")
        page.evaluate("(key) => sessionStorage.setItem(key, '{\"v\": 1, \"rows\": [ broken')", KEY.format(analysis_id))
    open_edit(page, analysis_id)
    if trouble == "broken":
        expect(gen_log(page)).to_have_count(0)
        assert stored(page, analysis_id) is None  # dropped
    generate(page)
    expect(log_row(page, a)).to_contain_text("作成 3件")
    expect(log_row(page, b)).to_contain_text("作成 3件")
    note = gen_log(page).locator("[data-gen-log-storage]")
    if trouble == "broken":
        expect(note).to_have_count(0)
    else:
        expect(note).to_have_text("ブラウザの保存領域を使えないため、この画面を開き直すと結果は消えます。")
        # Saving and judging go on.
        step_button(page, 2).click()
        page.locator(f'[data-role="work-item"][data-node-id="{a}"] [data-value="no"]').click()
        expect(page.locator("#ui-toasts .ui-toast[data-toast-type='success']").filter(has_text="評価を更新しました")).to_be_visible()
    assert e2e_server.judgement(a) == ("no" if trouble != "broken" else "yes")

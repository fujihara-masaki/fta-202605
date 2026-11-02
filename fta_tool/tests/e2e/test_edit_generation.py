"""E2E: generation (PR-6; plan 5.3〜5.6, 8.6): what is generated and what came
of it.

E-G01  一次: an empty top event stops it; an unsaved top event and reference
       information are saved first.
E-G02  二次・三次: the targets (names and number, Yes parents hidden by the
       filter included, inconsistent ones excluded and counted apart), one
       request per parent with its parent_id, the top event's handling (J-09).
E-G03  The eight result categories in the log and on the parents' badges,
       a quality warning with the factors created, the reasons of an all
       excluded result, a partial failure, an HTTP error, an answer that is
       not JSON, a network failure; the summary notification (J-04).
E-G05  After the generation: the new factors under the right parent, the
       selection, the scroll position, the draft and the log kept.
E-G07  Additional generation: 一次, and below one parent whatever its
       judgement; the numbers of the operation bar are the settings.

The stub's settings (tests/e2e/stub_server.py PINNED_ENV): 一次 4, 二次 3,
三次 2, 追加 2. No real LLM is called.
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.edit_helpers import (
    additional_button,
    choose,
    factor_field,
    factor_status,
    gen_badge,
    gen_log,
    generate_button,
    generation_requests,
    hold,
    inspector,
    log_row,
    open_edit,
    phase,
    post_paths,
    pump,
    select_button,
    step_button,
    step_panel,
    toast,
    wait_phase,
)
from tests.e2e.support import expect

pytestmark = [pytest.mark.e2e]

SINGLE = pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])


def parents(e2e_server, analysis_id, specs):
    """一次要因 with their judgements: [(title, judgement)] -> ids."""
    ids = []
    for title, judgement in specs:
        node = e2e_server.add_level1(analysis_id, title)
        if judgement != "unknown":
            e2e_server.update_node(node, user_judgement=judgement)
        ids.append(node)
    return ids


def children_of(e2e_server, parent_id) -> list[tuple]:
    return e2e_server.query("SELECT id, title, ai_generated, warning_flags FROM nodes WHERE parent_id = ? ORDER BY id",
                            (parent_id,))


# ----- E-G01 --------------------------------------------------------------------

@pytest.mark.acceptance("E-G01")
def test_E_G01_an_empty_top_event_stops_the_primary_generation(page, e2e_server):
    analysis_id = e2e_server.create_analysis("頂上事象なし", system_context="構成")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    sent = post_paths(page)
    page.fill("#systemContextInput", "未保存の参考情報")
    step_button(page, 2).click()
    generate_button(page, 1).click()
    expect(toast(page, "頂上事象を入力してから生成してください", "error")).to_be_visible()
    expect(page.locator("#topEventInput")).to_be_focused()
    assert phase(page) == "idle"
    page.wait_for_timeout(300)
    assert requests == [] and sent == []  # nothing generated, nothing saved
    expect(page.locator("#systemContextInput")).to_have_value("未保存の参考情報")
    expect(generate_button(page, 1)).to_be_enabled()
    expect(gen_log(page)).to_have_count(0)


@pytest.mark.acceptance("E-G01")
def test_E_G01_unsaved_top_event_and_reference_information_are_saved_first(page, e2e_server):
    analysis_id = e2e_server.create_analysis("一次の通常生成", top_event="古い頂上事象")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    sent = post_paths(page)
    page.fill("#topEventInput", "決済処理が停止した")
    page.fill("#systemContextInput", "Web2台とDB1台")
    step_button(page, 2).click()
    expect(step_panel(page, 2).locator('[data-opbar-kinds="1"]')).to_contain_text("一次要因を4件生成します（設定値）")
    generate_button(page, 1).click()
    expect(log_row(page, "top")).to_have_attribute("data-category", "created")
    wait_phase(page, "idle")
    assert sent == [f"/analyses/{analysis_id}/top-event", f"/analyses/{analysis_id}/context",
                    f"/analyses/{analysis_id}/generate/level/1"]
    assert requests == [{"path": f"/analyses/{analysis_id}/generate/level/1", "body": {}}]
    stored = e2e_server.analysis(analysis_id)
    assert stored["top_event"] == "決済処理が停止した"
    assert json.loads(stored["analysis_context"])["system_context"] == "Web2台とDB1台"
    expect(toast(page, "編集中の頂上事象を保存してから生成します", "success")).to_have_count(1)
    expect(toast(page, "編集中の参考情報を保存してから生成します", "success")).to_have_count(1)
    expect(toast(page, "一次要因の通常生成：4件作成しました", "success")).to_be_visible()
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(4)
    expect(log_row(page, "top")).to_contain_text("作成 4件")
    expect(log_row(page, "top")).to_contain_text("頂上事象の下（一次要因）")
    expect(gen_log(page)).to_contain_text("生成ログ：一次要因の通常生成")
    calls = e2e_server.stub_calls()
    assert [(c["target_level"], c["parent_factor"], c["additional"]) for c in calls] == [(1, None, False)]


# ----- E-G02 --------------------------------------------------------------------

@pytest.mark.acceptance("E-G02")
def test_E_G02_every_eligible_yes_parent_hidden_or_not_one_request_each(page, e2e_server):
    analysis_id = e2e_server.create_analysis("二次の通常生成", top_event="頂上")
    a, b, c, d = parents(e2e_server, analysis_id,
                         [("認証の不具合", "yes"), ("設定の誤り", "yes"), ("運用の不備", "no"), ("監視の漏れ", "unknown")])
    # A Yes 一次要因 with an inconsistent link (a parent at level 1): excluded, counted apart.
    broken = e2e_server.insert_node(analysis_id, 1, a, title="不整合のYes", judgement="yes")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    sent = post_paths(page)
    step_button(page, 1).click()
    page.fill("#topEventInput", "保存していない頂上事象")
    page.fill("#incidentContextInput", "9時から停止")
    step_button(page, 3).click()
    page.fill("#edit-filter-text", "認証")  # 設定の誤り is hidden by the filter
    expect(step_panel(page, 3).locator(f'[data-group-parent="{b}"]')).to_be_visible()  # groups are not filtered
    bar = step_panel(page, 3).locator('[data-opbar-kinds="2"]')
    expect(bar.locator('[data-target-count="2"]')).to_have_text("2")
    expect(bar.locator('[data-target-names="2"]')).to_have_text("：「認証の不具合」「設定の誤り」")
    expect(bar).to_contain_text("絞り込みで表示していない要因も含みます")
    expect(bar.locator('[data-target-excluded="2"]')).to_be_visible()
    expect(bar.locator("[data-target-excluded-count]")).to_have_text("1")
    expect(bar).to_contain_text("親1件につき3件を生成します（設定値）")
    expect(bar).to_contain_text("通常生成")
    expect(bar).to_contain_text("追加生成")
    expect(bar).to_contain_text("手動追加")
    note = step_panel(page, 3).locator('[data-autosave-note="2"]')
    expect(note).to_contain_text("保存済みの頂上事象を使います")
    expect(note.locator("[data-top-event-unsaved-note]")).to_be_visible()

    generate_button(page, 2).click()
    expect(toast(page, "二次要因の通常生成を開始しました：対象の親 2件", "info")).to_be_visible()
    expect(toast(page, "親子関係に不整合があるため対象外：1件", "info")).to_be_visible()
    wait_phase(page, "idle")
    assert [r["body"] for r in requests] == [{"parent_id": a}, {"parent_id": b}]
    assert f"/analyses/{analysis_id}/top-event" not in sent  # J-09: the saved top event is used
    assert sent[0] == f"/analyses/{analysis_id}/context"
    assert e2e_server.analysis(analysis_id)["top_event"] == "頂上"
    expect(page.locator("#topEventInput")).to_have_value("保存していない頂上事象")
    calls = e2e_server.stub_calls()
    assert [c["parent_factor"] for c in calls] == ["認証の不具合", "設定の誤り"]
    assert len([n for n in children_of(e2e_server, a) if n[2]]) == 3  # AI children (the broken one is a manual row)
    assert len(children_of(e2e_server, b)) == 3
    assert children_of(e2e_server, c) == [] and children_of(e2e_server, d) == [] and children_of(e2e_server, broken) == []
    expect(gen_log(page)).to_contain_text("親子関係に不整合があるYes評価の要因 1件は対象外です")
    expect(log_row(page, a)).to_contain_text("親：「認証の不具合」")
    expect(log_row(page, b)).to_contain_text("作成 3件")
    expect(toast(page, "二次要因の通常生成：6件作成しました", "success")).to_be_visible()


@pytest.mark.acceptance("E-G02")
def test_E_G02_tertiary_generation_names_each_parent(page, e2e_server):
    analysis_id = e2e_server.create_analysis("三次の通常生成", top_event="頂上")
    a, = parents(e2e_server, analysis_id, [("一次A", "yes")])
    x = e2e_server.add_child(a, "二次X")
    y = e2e_server.add_child(a, "二次Y")
    e2e_server.update_node(x, user_judgement="yes")
    e2e_server.update_node(y, user_judgement="yes")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/3")
    step_button(page, 4).click()
    expect(step_panel(page, 4).locator('[data-target-names="3"]')).to_have_text("：「二次X」「二次Y」")
    generate_button(page, 3).click()
    pump(page, lambda: len(held) == 1)
    held[0].continue_()
    pump(page, lambda: len(held) == 2)
    held[1].continue_()
    wait_phase(page, "idle")
    assert [r["body"] for r in requests] == [{"parent_id": x}, {"parent_id": y}]
    assert all("parent_id" in r["body"] for r in requests)
    expect(log_row(page, x)).to_contain_text("作成 2件")
    expect(log_row(page, y)).to_contain_text("作成 2件")
    expect(gen_badge(page, x)).to_have_text("作成 2件")


# ----- E-G03 --------------------------------------------------------------------

CATEGORY_TITLES = {
    "created": "作成の親",
    "warning": "品質警告の親",
    "none": "候補0件の親",
    "excluded": "全候補除外の親",
    "error": "処理失敗の親",
    "network": "通信失敗の親",
    "http": "HTTPエラーの親",
    "parse": "JSONでない応答の親",
    "partial": "一部作成の親",
    "mismatch": "件数不一致の親",
}


@SINGLE
@pytest.mark.acceptance("E-G03")
def test_E_G03_every_category_in_the_log_and_on_the_badges(page, e2e_server, page_watch):
    page_watch.allow_console_error(r"status of 500")
    page_watch.allow_console_error(r"net::ERR_FAILED")
    analysis_id = e2e_server.create_analysis("結果区分", top_event="頂上")
    ids = dict(zip(CATEGORY_TITLES, parents(e2e_server, analysis_id,
                                            [(title, "yes") for title in CATEGORY_TITLES.values()])))
    e2e_server.set_control(mode="create", by_parent={
        CATEGORY_TITLES["warning"]: "warning",
        CATEGORY_TITLES["none"]: "no_candidates",
        CATEGORY_TITLES["excluded"]: "all_excluded",
        CATEGORY_TITLES["error"]: "error",
    })
    open_edit(page, analysis_id)
    requests = generation_requests(page)

    def answer(route):
        parent = (route.request.post_data_json or {}).get("parent_id")
        if parent == ids["network"]:
            route.abort()
        elif parent == ids["http"]:
            route.fulfill(status=500, content_type="application/json", body='{"detail": "内部エラー（検証用）"}')
        elif parent == ids["parse"]:
            route.fulfill(status=200, content_type="text/html", body="<html><body>JSONではない応答</body></html>")
        elif parent == ids["partial"]:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"success": False, "created": 2, "message": "一部でエラーが発生しました: 検証用", "parent_id": parent}))
        elif parent == ids["mismatch"]:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"success": True, "created": 3, "skipped": 0, "message": "3件の要因を生成しました",
                 "parent_id": parent, "quality_summary": {"all_candidates_excluded": False, "reason_summary": []}}))
        else:
            route.continue_()

    page.route(f"**/analyses/{analysis_id}/generate/level/2", answer)
    step_button(page, 3).click()
    generate_button(page, 2).click()
    wait_phase(page, "idle", timeout=20)
    assert [r["body"]["parent_id"] for r in requests] == list(ids.values())

    expected = {
        "created": ("created", ["作成 3件"]),
        "warning": ("created", ["作成 3件", "品質警告（要確認）付き：3件"]),
        "none": ("no-candidates", ["候補0件", "LLMが要因を返しませんでした"]),
        "excluded": ("all-excluded", ["全候補除外", "主な理由：親要因の言い換え"]),
        "error": ("failed", ["処理失敗", "E2Eスタブ：生成に失敗しました"]),
        "network": ("network", ["通信失敗", "生成されたかどうかは分かりません"]),
        "http": ("server-error", ["サーバーエラー", "HTTP 500", "内部エラー（検証用）"]),
        "parse": ("server-error", ["サーバーエラー", "応答を読み取れませんでした（HTTP 200）"]),
        "partial": ("failed", ["処理失敗", "一部作成：2件"]),
        "mismatch": ("created", ["作成 3件", "応答の作成件数（3件）と、更新後にこの親の下で確認できた新しい要因の数（0件）が一致しません"]),
    }
    labels = {"created": None, "no-candidates": "候補0件", "all-excluded": "全候補除外", "failed": "処理失敗",
              "network": "通信失敗", "server-error": "サーバーエラー"}
    for key, (category, texts) in expected.items():
        row = log_row(page, ids[key])
        expect(row).to_have_attribute("data-category", category)
        expect(row).to_contain_text(f"親：「{CATEGORY_TITLES[key]}」")
        for text in texts:
            expect(row).to_contain_text(text)
        badge = gen_badge(page, ids[key])
        expect(badge).to_have_attribute("data-category", category)
        expect(badge).to_have_text(labels[category] or "作成 3件")
    # 一部作成 is told with the failure, the created count is the answer's.
    expect(toast(page, "二次要因の通常生成：11件作成、5件の親で失敗しました（詳細は生成ログ）", "warning")).to_be_visible()
    expect(page.locator("[data-gen-log-summary]")).to_contain_text("作成 11件・失敗した親 5件・全候補除外の親 1件・候補0件の親 1件")
    # The factors really created are under their parents.
    assert len(children_of(e2e_server, ids["created"])) == 3
    warned = children_of(e2e_server, ids["warning"])
    assert len(warned) == 3 and all(row[3] for row in warned)
    assert children_of(e2e_server, ids["mismatch"]) == []
    expect(step_panel(page, 3).locator(f'[data-group-parent="{ids["warning"]}"] .ui-tag--warning')).to_have_count(3)


@SINGLE
@pytest.mark.acceptance("E-G03")
def test_E_G03_a_parent_deleted_meanwhile_is_told_after_the_update(page, e2e_server):
    analysis_id = e2e_server.create_analysis("親なし", top_event="頂上")
    a, b = parents(e2e_server, analysis_id, [("消える親", "yes"), ("残る親", "yes")])
    open_edit(page, analysis_id)
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/2")
    step_button(page, 3).click()
    generate_button(page, 2).click()
    pump(page, lambda: len(held) == 1)
    e2e_server.delete_node(a)  # e.g. from another tab, before the server ran this request
    held[0].continue_()
    pump(page, lambda: len(held) == 2)
    held[1].continue_()
    wait_phase(page, "idle")
    row = log_row(page, a)
    expect(row).to_have_attribute("data-category", "parent-gone")
    expect(row).to_contain_text("親なし")
    expect(row).to_contain_text("親要因が見つかりません（削除された可能性があります）")
    expect(row).to_contain_text(f"ID {a}")  # its name is not stored: the page has no data of it now
    expect(log_row(page, b)).to_have_attribute("data-category", "created")
    expect(toast(page, "二次要因の通常生成：3件作成、1件の親で失敗しました", "warning")).to_be_visible()


@SINGLE
@pytest.mark.acceptance("E-G03")
def test_E_G03_an_analysis_deleted_meanwhile_stops_the_rest(page, e2e_server, page_watch):
    page_watch.allow_console_error(r"status of 404")
    analysis_id = e2e_server.create_analysis("分析なし", top_event="頂上")
    a, b = parents(e2e_server, analysis_id, [("親A", "yes"), ("親B", "yes")])
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/2")
    step_button(page, 3).click()
    generate_button(page, 2).click()
    pump(page, lambda: len(held) == 1)
    e2e_server.delete_analysis(analysis_id)
    held[0].continue_()
    wait_phase(page, "idle")
    assert len(requests) == 1  # the second parent was not sent
    expect(log_row(page, a)).to_have_attribute("data-category", "analysis-gone")
    expect(log_row(page, a)).to_contain_text("分析が見つかりません")
    expect(log_row(page, b)).to_have_attribute("data-category", "skipped")
    expect(log_row(page, b)).to_contain_text("分析が見つからないため送信していません")
    expect(toast(page, "作成できませんでした", "error")).to_be_visible()
    # The analysis is gone: what that disabled stays disabled after the generation.
    expect(page.locator(".edit-gone")).to_be_visible()
    expect(generate_button(page, 2)).to_be_disabled()
    expect(step_panel(page, 3).locator('[data-action="add"]').first).to_be_disabled()


@SINGLE
@pytest.mark.acceptance("E-G03")
@pytest.mark.parametrize("mode, kind, message", [
    ("no_candidates", "warning", "二次要因の通常生成：生成候補がありませんでした（LLMが要因を返しませんでした）"),
    ("all_excluded", "warning", "二次要因の通常生成：生成候補はすべて品質チェックなどで除外されました（主な理由：親要因の言い換え）"),
    ("error", "error", "二次要因の通常生成：作成できませんでした（詳細は生成ログ）"),
])
def test_E_G03_the_summary_when_nothing_was_created(page, e2e_server, mode, kind, message):
    analysis_id = e2e_server.create_analysis("作成なし", top_event="頂上")
    a, = parents(e2e_server, analysis_id, [("親A", "yes")])
    e2e_server.set_control(mode=mode)
    open_edit(page, analysis_id)
    step_button(page, 3).click()
    generate_button(page, 2).click()
    wait_phase(page, "idle")
    expect(toast(page, message, kind, exact=True)).to_be_visible()
    assert children_of(e2e_server, a) == []


# ----- E-G05 --------------------------------------------------------------------

@pytest.mark.acceptance("E-G05")
def test_E_G05_new_factors_under_their_parents_and_the_page_state_kept(page, e2e_server):
    analysis_id = e2e_server.create_analysis("生成後の更新", top_event="頂上")
    ids = parents(e2e_server, analysis_id, [("親A", "yes"), ("親B", "yes")]
                  + [(f"一次要因{n}", "unknown") for n in range(1, 13)])
    a, b, x = ids[0], ids[1], ids[5]
    open_edit(page, analysis_id)
    choose(page, x)
    step_button(page, 3).click()
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/2")
    generate_button(page, 2).click()
    pump(page, lambda: len(held) == 1)
    # While it runs: a draft, the focus in it, a scroll position.
    factor_field(page, "memo").fill("生成中に書いた下書き")
    center = page.locator('[data-scroll="center"]')
    center.evaluate("(el) => { el.scrollTop = 240; }")
    factor_field(page, "memo").focus()
    held[0].continue_()
    pump(page, lambda: len(held) == 2)
    held[1].continue_()
    wait_phase(page, "idle")
    for parent in (a, b):
        group = step_panel(page, 3).locator(f'[data-group-parent="{parent}"]')
        expect(group.locator('[data-role="work-item"]')).to_have_count(3)
    for child in children_of(e2e_server, a):
        expect(page.locator(f'[data-group-parent="{a}"] [data-role="work-item"][data-node-id="{child[0]}"]')).to_have_count(1)
    expect(select_button(page, "nav", x)).to_have_attribute("aria-current", "true")
    expect(factor_field(page, "memo")).to_have_value("生成中に書いた下書き")
    expect(factor_field(page, "memo")).to_be_focused()
    expect(factor_status(page)).to_have_text("入力中（未保存）")
    assert center.evaluate("(el) => el.scrollTop") == 240
    expect(gen_log(page)).to_be_visible()
    expect(log_row(page, a)).to_contain_text("作成 3件")
    expect(log_row(page, b)).to_contain_text("作成 3件")


# ----- E-G07 --------------------------------------------------------------------

@pytest.mark.acceptance("E-G07")
def test_E_G07_additional_generation_of_primary_factors(page, e2e_server):
    analysis_id = e2e_server.create_analysis("一次の追加生成", top_event="頂上")
    parents(e2e_server, analysis_id, [("既存の一次要因", "unknown")])
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    bar = step_panel(page, 2).locator('[data-opbar-kinds="1"]')
    expect(bar).to_contain_text("一次要因を4件生成します（設定値）")
    expect(bar).to_contain_text("一次要因を2件追加します（設定値）")
    expect(bar).to_contain_text("AIを使わず、一次要因を1件追加します")
    additional_button(page).click()
    wait_phase(page, "idle")
    assert [r["body"] for r in requests] == [{"additional": True}]
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(3)
    expect(gen_log(page)).to_contain_text("生成ログ：一次要因の追加生成")
    expect(log_row(page, "top")).to_contain_text("作成 2件")
    calls = e2e_server.stub_calls()
    assert [(c["target_level"], c["additional"], c["factor_count"]) for c in calls] == [(1, True, 2)]


@pytest.mark.acceptance("E-G07")
def test_E_G07_additional_generation_below_a_no_an_unknown_and_a_secondary_parent(page, e2e_server):
    analysis_id = e2e_server.create_analysis("親への追加生成", top_event="頂上")
    yes, no, unknown = parents(e2e_server, analysis_id, [("Yesの親", "yes"), ("Noの親", "no"), ("未評価の親", "unknown")])
    secondary = e2e_server.add_child(yes, "二次の親")
    tertiary = e2e_server.add_child(secondary, "三次要因")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    step_button(page, 3).click()
    bar = step_panel(page, 3).locator('[data-opbar-kinds="2"]')
    expect(bar).to_contain_text("選んだ親1件の下に2件追加します（設定値）")
    expect(bar).to_contain_text("Yes・No・未評価のどれでも使えます")
    # The No parent, from its group heading.
    additional_button(page, no).click()
    wait_phase(page, "idle")
    expect(log_row(page, no)).to_contain_text("作成 2件")
    expect(gen_badge(page, no)).to_have_text("作成 2件")
    # The unknown parent, from the inspector.
    choose(page, unknown)
    additional_button(page, unknown, scope=inspector(page)).click()
    wait_phase(page, "idle")
    expect(gen_log(page)).to_contain_text("生成ログ：二次要因の追加生成")
    expect(log_row(page, unknown)).to_contain_text("作成 2件")
    # A 二次要因: its additional generation makes 三次要因.
    choose(page, secondary)
    expect(step_panel(page, 4).locator('[data-opbar-kinds="3"]')).to_contain_text("三次要因の下には追加しません")
    additional_button(page, secondary, scope=inspector(page)).click()
    wait_phase(page, "idle")
    expect(gen_log(page)).to_contain_text("生成ログ：三次要因の追加生成")
    assert [r["body"] for r in requests] == [
        {"additional": True, "parent_id": no},
        {"additional": True, "parent_id": unknown},
        {"additional": True, "parent_id": secondary},
    ]
    assert len(children_of(e2e_server, no)) == 2 and len(children_of(e2e_server, unknown)) == 2
    assert len([n for n in children_of(e2e_server, secondary) if n[2]]) == 2
    # Never below a 三次要因.
    choose(page, tertiary)
    expect(inspector(page).locator('[data-action="generate-additional"]')).to_have_count(0)
    calls = e2e_server.stub_calls()
    assert [(c["target_level"], c["additional"], c["factor_count"]) for c in calls] == [(2, True, 2), (2, True, 2), (3, True, 2)]

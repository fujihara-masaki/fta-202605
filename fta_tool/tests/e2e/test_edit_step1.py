"""E2E: ① 頂上事象・参考情報 (PR-4, E-E10; plan 5.1, 8.4-1・2, J-09, J-11).

- Save status 「入力中（未保存）／保存済み」 per input, compared after the
  normalisation used for saving: values written to the database with CRLF and
  surrounding spaces are 保存済み when the page opens, typing and restoring
  is 保存済み again, white space alone is not a change.
- The save buttons send one request (the two kinds of reference information
  together); demo_points and unknown keys survive and are never shown.
- A save's answer never marks what was typed after sending as saved; a
  failed save keeps the input and the reason.
- The automatic save before a generation is the same save: same requests,
  same saved value and status as the save button (一次: top event and
  reference information; 二次・三次: reference information only, the saved
  top event is used and the operation bar says so). A failed automatic save
  starts no generation; an empty top event stops 一次 only.
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.edit_helpers import (
    item,
    judgement_button,
    open_edit,
    post_paths,
    save_button,
    save_status,
    step_button,
    step_panel,
    toast,
    wait_until,
)
from tests.e2e.support import expect, record_dialogs

pytestmark = [pytest.mark.e2e, pytest.mark.acceptance("E-E10")]

STORED_TOP = "  頂上事象の1行目\r\n2行目  "
STORED_CONTEXT = {"system_context": "  構成の1行目\r\n構成の2行目 ", "incident_context": "状況\r\n",
                  "demo_points": "デモ観点（画面に出さない）", "extra_key": "未知のキー"}


def stored_analysis(e2e_server, title="①の保存"):
    analysis_id = e2e_server.create_analysis(title)
    e2e_server.set_analysis_fields(analysis_id, top_event=STORED_TOP,
                                   analysis_context=json.dumps(STORED_CONTEXT, ensure_ascii=False))
    return analysis_id


def expect_statuses(page, top: str, system: str, incident: str) -> None:
    for field, state in (("topEventInput", top), ("systemContextInput", system), ("incidentContextInput", incident)):
        expect(save_status(page, field)).to_have_attribute("data-state", state)
    texts = {"saved": "保存済み", "dirty": "入力中（未保存）", "saving": "保存中…"}
    expect(save_status(page, "topEventInput")).to_have_text(texts[top])


def test_E_E10_stored_crlf_and_spaces_are_saved_and_restoring_is_saved_again(page, e2e_server):
    analysis_id = stored_analysis(e2e_server)
    open_edit(page, analysis_id)
    dialogs = record_dialogs(page, action="accept")
    expect(step_panel(page, 1)).to_be_visible()
    expect_statuses(page, "saved", "saved", "saved")
    expect(step_button(page, 1)).to_contain_text("頂上事象：入力済み")
    expect(step_button(page, 1)).not_to_contain_text("未保存あり")
    expect(page.locator("body")).not_to_contain_text("デモ観点（画面に出さない）")
    expect(page.locator("body")).not_to_contain_text("未知のキー")
    page.reload()  # nothing unsaved: no leave confirmation
    assert dialogs == []

    top = page.locator("#topEventInput")
    top.fill("頂上事象の1行目\n2行目（変更）")
    expect_statuses(page, "dirty", "saved", "saved")
    expect(step_button(page, 1)).to_contain_text("未保存あり")
    top.fill("頂上事象の1行目\n2行目")  # typed back: saved again
    expect_statuses(page, "saved", "saved", "saved")
    top.fill("\n  頂上事象の1行目\r\n2行目   \n")  # white space and line endings only
    expect_statuses(page, "saved", "saved", "saved")
    page.fill("#incidentContextInput", "状況（変更）")
    expect_statuses(page, "saved", "saved", "dirty")
    page.fill("#incidentContextInput", " 状況 ")
    expect_statuses(page, "saved", "saved", "saved")
    expect(step_button(page, 1)).not_to_contain_text("未保存あり")
    page.reload()
    assert dialogs == []


def test_E_E10_save_buttons_send_one_request_and_keep_demo_points(page, e2e_server):
    analysis_id = stored_analysis(e2e_server)
    open_edit(page, analysis_id)
    sent = post_paths(page)

    page.fill("#topEventInput", "  保存する頂上事象\n2行目 ")
    save_button(page, "top-event").click()
    expect(toast(page, "頂上事象を保存しました", "success", exact=True)).to_have_count(1)
    expect_statuses(page, "saved", "saved", "saved")
    assert e2e_server.analysis(analysis_id)["top_event"] == "保存する頂上事象\n2行目"
    expect(page.locator('#edit-nav [data-select="top"]')).to_contain_text("保存する頂上事象")

    page.fill("#systemContextInput", "新しい構成")
    expect_statuses(page, "saved", "dirty", "saved")
    save_button(page, "context").click()
    expect(toast(page, "参考情報を保存しました", "success", exact=True)).to_have_count(1)
    expect_statuses(page, "saved", "saved", "saved")
    assert sent == [f"/analyses/{analysis_id}/top-event", f"/analyses/{analysis_id}/context"]
    stored = json.loads(e2e_server.analysis(analysis_id)["analysis_context"])
    assert stored == {"system_context": "新しい構成", "incident_context": "状況",
                      "demo_points": "デモ観点（画面に出さない）", "extra_key": "未知のキー"}

    # Nothing changed: nothing is sent.
    save_button(page, "context").click()
    expect(toast(page, "参考情報に保存していない変更はありません", "info", exact=True)).to_have_count(1)
    assert len(sent) == 2

    # The top event may be saved empty.
    page.fill("#topEventInput", "  ")
    save_button(page, "top-event").click()
    wait_until(lambda: e2e_server.analysis(analysis_id)["top_event"] == "")
    expect(step_button(page, 1)).to_contain_text("頂上事象：未入力")


def test_E_E10_input_typed_during_a_save_stays_unsaved(page, e2e_server):
    analysis_id = e2e_server.create_analysis("送信後の入力", top_event="元の頂上事象")
    open_edit(page, analysis_id)
    held = []
    page.route(f"**/analyses/{analysis_id}/top-event", lambda route: held.append(route))

    page.fill("#topEventInput", "送信した頂上事象")
    save_button(page, "top-event").click()
    expect(save_status(page, "topEventInput")).to_have_attribute("data-state", "saving")
    expect(save_button(page, "top-event")).to_be_disabled()
    wait_until(lambda: len(held) == 1)
    page.fill("#topEventInput", "送信後に入力した頂上事象")
    held[0].continue_()
    expect(page.locator("#topEventInput")).to_have_attribute("data-saved", "送信した頂上事象")
    expect(save_status(page, "topEventInput")).to_have_attribute("data-state", "dirty")
    expect(page.locator("#topEventInput")).to_have_value("送信後に入力した頂上事象")
    assert e2e_server.analysis(analysis_id)["top_event"] == "送信した頂上事象"


def test_E_E10_a_failed_save_keeps_the_input_and_the_reason(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("保存の失敗", top_event="元の頂上事象")
    open_edit(page, analysis_id)
    page_watch.allow_console_error(r"status of 500")
    page.route(f"**/analyses/{analysis_id}/context",
               lambda route: route.fulfill(status=500, json={"detail": "E2E: 参考情報の保存に失敗させました"}))

    page.fill("#systemContextInput", "失敗する構成")
    save_button(page, "context").click()
    expect(toast(page, "参考情報を保存できませんでした：E2E: 参考情報の保存に失敗させました", "error", exact=True)).to_be_visible()
    expect(page.locator('[data-save-message="context"]')).to_have_text("保存できませんでした：E2E: 参考情報の保存に失敗させました")
    expect(save_status(page, "systemContextInput")).to_have_attribute("data-state", "dirty")
    expect(page.locator("#systemContextInput")).to_have_value("失敗する構成")
    assert e2e_server.analysis(analysis_id)["analysis_context"] == ""

    page.unroute(f"**/analyses/{analysis_id}/context")
    save_button(page, "context").click()
    expect(save_status(page, "systemContextInput")).to_have_attribute("data-state", "saved")
    expect(page.locator('[data-save-message="context"]')).to_have_text("")


def test_E_E10_automatic_save_before_generation_is_the_same_save(page, e2e_server):
    analysis_id = stored_analysis(e2e_server, "生成前の自動保存")
    open_edit(page, analysis_id)
    sent = post_paths(page)
    expect(step_panel(page, 1).locator("[data-autosave-note]").first).to_contain_text(
        "二次・三次要因の生成の前には参考情報だけを保存し、頂上事象は保存済みの値を使います")

    # 一次: the stored CRLF top event is not changed, so it is not sent; the
    # changed reference information is saved first, as by its button.
    page.fill("#incidentContextInput", "生成前に保存する状況")
    step_button(page, 2).click()
    expect(step_panel(page, 2).locator('[data-autosave-note="1"]')).to_have_text(
        "生成の前に、入力中の頂上事象と参考情報を自動で保存します（頂上事象が空のときは生成しません）。")
    step_panel(page, 2).get_by_role("button", name="一次要因を生成").click()
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(4)
    assert sent[:2] == [f"/analyses/{analysis_id}/context", f"/analyses/{analysis_id}/generate/level/1"]
    expect(toast(page, "編集中の参考情報を保存してから生成します", "success", exact=True)).to_have_count(1)
    expect_statuses(page, "saved", "saved", "saved")
    assert json.loads(e2e_server.analysis(analysis_id)["analysis_context"])["incident_context"] == "生成前に保存する状況"
    assert e2e_server.analysis(analysis_id)["top_event"] == STORED_TOP  # untouched

    # 一次 (additional) with a changed top event: both are saved, top event first.
    step_button(page, 1).click()
    page.fill("#topEventInput", "生成前に保存する頂上事象")
    page.fill("#systemContextInput", "生成前に保存する構成")
    step_button(page, 2).click()
    del sent[:]
    step_panel(page, 2).get_by_role("button", name="一次要因を追加生成").click()
    expect(step_panel(page, 2).locator('[data-role="work-item"]')).to_have_count(6)
    assert sent[:3] == [f"/analyses/{analysis_id}/top-event", f"/analyses/{analysis_id}/context",
                        f"/analyses/{analysis_id}/generate/level/1"]
    expect_statuses(page, "saved", "saved", "saved")
    assert e2e_server.analysis(analysis_id)["top_event"] == "生成前に保存する頂上事象"

    # 二次: the reference information only; an unsaved top event is not used.
    first = int(step_panel(page, 2).locator('[data-role="work-item"]').first.get_attribute("data-node-id"))
    judgement_button(item(page, "work", first), first, "yes").click()
    expect(item(page, "work", first)).to_have_attribute("data-judgement", "yes")
    step_button(page, 1).click()
    page.fill("#topEventInput", "二次では使われない頂上事象")
    page.fill("#systemContextInput", "二次の前に保存する構成")
    step_button(page, 3).click()
    note = step_panel(page, 3).locator('[data-autosave-note="2"]')
    expect(note).to_contain_text("保存済みの頂上事象を使います。生成の前に自動で保存するのは参考情報だけです。")
    expect(note.locator("[data-top-event-unsaved-note]")).to_be_visible()
    del sent[:]
    step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成").click()
    expect(page.locator(f'[data-group-parent="{first}"] [data-role="work-item"]')).to_have_count(3)
    assert sent[0] == f"/analyses/{analysis_id}/context"
    assert f"/analyses/{analysis_id}/top-event" not in sent
    assert e2e_server.analysis(analysis_id)["top_event"] == "生成前に保存する頂上事象"
    expect(save_status(page, "topEventInput")).to_have_attribute("data-state", "dirty")
    expect(page.locator("#topEventInput")).to_have_value("二次では使われない頂上事象")
    # After the partial update the operation bar still says so.
    expect(step_panel(page, 3).locator("[data-top-event-unsaved-note]")).to_be_visible()


def test_E_E10_a_failed_automatic_save_or_an_empty_top_event_starts_nothing(page, e2e_server, page_watch):
    analysis_id = e2e_server.create_analysis("自動保存の失敗", top_event="頂上事象")
    open_edit(page, analysis_id)
    page_watch.allow_console_error(r"status of 500")
    page.route(f"**/analyses/{analysis_id}/context",
               lambda route: route.fulfill(status=500, json={"detail": "E2E: 自動保存に失敗させました"}))
    page.fill("#systemContextInput", "保存できない構成")
    step_button(page, 2).click()
    step_panel(page, 2).get_by_role("button", name="一次要因を生成").click()
    expect(toast(page, "参考情報の保存に失敗したため、生成を開始しませんでした：E2E: 自動保存に失敗させました",
                 "error", exact=True)).to_be_visible()
    expect(step_panel(page, 2).get_by_role("button", name="一次要因を生成")).to_be_enabled()
    assert e2e_server.stub_calls() == []
    step_button(page, 1).click()
    expect(page.locator("#systemContextInput")).to_have_value("保存できない構成")
    expect(save_status(page, "systemContextInput")).to_have_attribute("data-state", "dirty")

    # An empty top event: 一次 is not generated, nothing is saved.
    page.unroute(f"**/analyses/{analysis_id}/context")
    sent = post_paths(page)
    page.fill("#topEventInput", " ")
    step_button(page, 2).click()
    step_panel(page, 2).get_by_role("button", name="一次要因を生成").click()
    expect(toast(page, "頂上事象を入力してから生成してください", "error", exact=True)).to_be_visible()
    page.wait_for_timeout(300)
    assert sent == [] and e2e_server.stub_calls() == []
    assert e2e_server.analysis(analysis_id)["top_event"] == "頂上事象"

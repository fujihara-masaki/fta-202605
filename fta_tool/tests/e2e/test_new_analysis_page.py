"""E2E: new analysis (B) — plan 8.2, E-N01〜E-N06 and the PR-2 checks.

Runs against the real app (stub AI provider, temporary database) in
Chromium at 1280x800 and 1440x900.

* E-N01  two columns; create: the four fields are saved in the same shape as
         before (POST /analyses, 303) and the edit screen opens on
         「① 頂上事象・参考情報」 with the top event selected (added in PR-3).
* E-N02  title check: blank / 256 characters give an error in the page and
         the focus, and nothing is sent; code points, trimmed (J-22).
* E-N03  sample: preview, transfer, 「サンプルを転記済み・未保存」, demo_points
         saved, the title never transferred (J-21).
* E-N04  キャンセル / header links with and without input: 入力を続ける /
         破棄して移動 only (J-12).
* E-N05  repeated submits create one analysis; the submit itself gets no
         leave confirmation.
* E-N06  the browser's leave confirmation (reload, closing the tab) only while
         there is input.
* PR2-IME         Enter in the title: a normal Enter submits through the check,
                  the Enter that confirms an IME conversion does not (C-08).
                  Simulated with synthetic key events (isComposing / keyCode
                  229); the real Microsoft IME is a manual check.
* PR2-NO-SAMPLES  without a readable sample file the page has no sample panel
                  and creating still works (a second app instance started
                  with FTA_SAMPLE_SCENARIOS_FILE pointing to a missing file).
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

import pytest

from tests.e2e.support import PageWatcher, expect, free_port, record_dialogs, start_server

pytestmark = pytest.mark.e2e

NEW_URL = "/analyses/new"
LEAVE_DIALOG = "作成していない入力があります"
SAMPLE_STATUS = "サンプルを転記済み・未保存"
FIELD_SELECTORS = {
    "title": "#title",
    "top_event": "#top_event",
    "system_context": "#systemContextInput",
    "incident_context": "#incidentContextInput",
}
# How the leave dialog lists each field when it holds 「入力あり」.
FIELD_LABELS = {
    "title": "分析タイトル「入力あり」",
    "top_event": "頂上事象",
    "system_context": "AIへの参考情報：システム構成・対象範囲",
    "incident_context": "AIへの参考情報：障害発生時の状況・観測事実",
}


# ----- helpers --------------------------------------------------------------

def unify(text: str) -> str:
    # Form submission sends line breaks as CRLF and the server strips the
    # value (unchanged behaviour), so compare with line endings unified.
    return text.replace("\r\n", "\n").strip()


def open_new(page):
    page.goto(NEW_URL)
    expect(page.locator("h1")).to_have_text("新規FTA分析を作成")


def field(page, name):
    return page.locator(FIELD_SELECTORS[name])


def submit_button(page):
    return page.locator("[data-submit]")


def cancel_link(page):
    return page.locator("[data-cancel-link]")


def header_link(page, name):
    return page.get_by_role("navigation", name="メインメニュー").get_by_role("link", name=name)


def leave_dialog(page):
    return page.get_by_role("dialog", name=LEAVE_DIALOG)


def apply_button(page):
    return page.get_by_role("button", name="この内容を入力欄へ転記")


def create_requests(page):
    sent = []
    page.on("request", lambda r: sent.append(r) if r.method == "POST" and r.url.endswith("/analyses") else None)
    return sent


def analysis_count(server) -> int:
    return server.query("SELECT COUNT(*) FROM analyses")[0][0]


def embedded_samples(page) -> list[dict]:
    return json.loads(page.locator("#sample-scenarios-data").text_content())


def created_id(page) -> int:
    expect(page).to_have_url(re.compile(r"/analyses/\d+$"))
    return int(page.url.rsplit("/", 1)[1])


# ----- E-N01 ----------------------------------------------------------------

@pytest.mark.acceptance("E-N01")
def test_E_N01_two_columns_and_create(page, e2e_server):
    open_new(page)
    expect(page).to_have_title("新規FTA分析作成")
    expect(header_link(page, "新規作成")).to_have_attribute("aria-current", "page")

    # Two columns (plan 3.2): 1 and 2 on the left, how the input is used and
    # the sample on the right, キャンセル / 作成して編集へ below both.
    main = page.locator(".new-page__main")
    aside = page.locator(".new-page__aside")
    expect(main.get_by_role("heading", level=2)).to_have_text(["1 分析の名前と頂上事象", "2 AIへの参考情報 任意"])
    expect(aside.get_by_role("heading", level=2)).to_have_text(["入力の使われ方", "サンプルから入力 デモ用"])
    main_box, aside_box = main.bounding_box(), aside.bounding_box()
    assert aside_box["x"] >= main_box["x"] + main_box["width"]
    assert abs(aside_box["y"] - main_box["y"]) < 1
    actions = page.locator(".new-page__actions")
    assert actions.bounding_box()["y"] >= max(main_box["y"] + main_box["height"], aside_box["y"] + aside_box["height"])
    expect(actions.get_by_role("link")).to_have_text(["キャンセル"])
    expect(actions.get_by_role("button")).to_have_text(["作成して編集へ"])
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    # Migrated: no legacy script, stylesheet or toast on this screen.
    assert page.evaluate("typeof window.showToast") == "undefined"
    expect(page.locator("#toast")).to_have_count(0)
    expect(page.locator('link[href="/static/style.css"]')).to_have_count(0)

    sent = create_requests(page)
    dialogs = record_dialogs(page)
    field(page, "title").fill("  E-N01 の分析  ")
    field(page, "top_event").fill("E-N01 の頂上事象")
    field(page, "system_context").fill("Webサーバ2台\nDBサーバ1台")
    field(page, "incident_context").fill("9時から500エラー")
    submit_button(page).click()
    analysis_id = created_id(page)
    expect(page.locator("#analysisTitle")).to_have_text("E-N01 の分析")  # the edit screen
    # It opens on ① with the top event (plan 5.5; the redirect is unchanged).
    expect(page.locator('.edit-steps [data-step="1"]')).to_have_attribute("aria-current", "step")
    expect(page.locator('[data-step-panel="1"]')).to_be_visible()
    expect(page.locator("#topEventInput")).to_have_value("E-N01 の頂上事象")
    expect(page.locator('#edit-nav [data-select="top"]')).to_have_attribute("aria-current", "true")
    expect(page.locator("[data-inspector-title]")).to_have_text("頂上事象")
    assert dialogs == []

    # The same POST /analyses as before: field names, 303 to the edit screen.
    assert len(sent) == 1
    posted = parse_qs(sent[0].post_data, keep_blank_values=True)
    assert sorted(posted) == ["demo_points", "incident_context", "system_context", "title", "top_event"]
    assert posted["title"] == ["E-N01 の分析"]  # sent trimmed (J-22), like the rename
    assert posted["demo_points"] == [""]
    response = sent[0].response()
    assert response.status == 303
    assert response.headers["location"] == f"/analyses/{analysis_id}"

    stored = e2e_server.analysis(analysis_id)
    assert stored["title"] == "E-N01 の分析"
    assert stored["top_event"] == "E-N01 の頂上事象"
    context = json.loads(stored["analysis_context"])
    assert sorted(context) == ["demo_points", "incident_context", "system_context"]
    assert unify(context["system_context"]) == "Webサーバ2台\nDBサーバ1台"
    assert context["incident_context"] == "9時から500エラー"
    assert context["demo_points"] == ""

    # The title alone is enough; without context the stored shape is "".
    open_new(page)
    field(page, "title").fill("タイトルだけの分析")
    submit_button(page).click()
    only_title = created_id(page)
    stored = e2e_server.analysis(only_title)
    assert (stored["title"], stored["top_event"], stored["analysis_context"]) == ("タイトルだけの分析", "", "")
    assert analysis_count(e2e_server) == 2


# ----- E-N02 ----------------------------------------------------------------

@pytest.mark.acceptance("E-N02")
def test_E_N02_blank_and_too_long_titles_are_not_sent(page, e2e_server):
    open_new(page)
    sent = create_requests(page)
    title = field(page, "title")
    error = page.locator("#title-error")
    count = page.locator("[data-title-count]")
    help_line = page.locator("#title-help")
    field(page, "top_event").fill("頂上事象は入力済み")

    # Blank: spaces only (including the ideographic space), and empty; the
    # button and Enter both stop at the check.
    title.fill(" 　 ")
    submit_button(page).click()
    expect(error).to_have_text("タイトルは必須です")
    expect(error).to_be_visible()
    expect(title).to_be_focused()
    expect(title).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#ui-live-alert")).to_have_text("タイトルは必須です")
    expect(count).to_have_text("0")
    title.fill("")
    title.press("Enter")
    expect(error).to_have_text("タイトルは必須です")
    expect(title).to_be_focused()

    # 256 characters.
    title.fill("あ" * 256)
    expect(count).to_have_text("256")
    expect(help_line).to_have_attribute("data-over-limit", "true")
    submit_button(page).click()
    expect(error).to_have_text("タイトルは255文字以内で入力してください")
    expect(title).to_be_focused()
    title.press("Enter")
    expect(error).to_have_text("タイトルは255文字以内で入力してください")
    page.wait_for_timeout(300)
    assert sent == []
    assert analysis_count(e2e_server) == 0
    expect(page).to_have_url(f"{e2e_server.url}{NEW_URL}")
    expect(field(page, "top_event")).to_have_value("頂上事象は入力済み")  # nothing is lost

    # A valid title clears the error.
    title.fill("あ" * 255)
    expect(error).to_be_hidden()
    expect(title).not_to_have_attribute("aria-invalid", "true")
    expect(help_line).to_have_attribute("data-over-limit", "false")

    # Counted in code points like the server: 255 × 𠮷 (outside the BMP,
    # 510 UTF-16 units) with spaces around is valid and saved trimmed.
    long_title = "𠮷" * 255
    title.fill(f"  {long_title} ")
    expect(count).to_have_text("255")
    submit_button(page).click()
    analysis_id = created_id(page)
    assert len(sent) == 1
    assert e2e_server.analysis(analysis_id)["title"] == long_title


# ----- PR2-IME --------------------------------------------------------------

@pytest.mark.acceptance("PR2-IME")
def test_title_enter_submits_but_the_ime_confirmation_enter_does_not(page, e2e_server):
    open_new(page)
    sent = create_requests(page)
    title = field(page, "title")
    title.fill("へんかんちゅう")

    # The Enter that confirms an IME conversion (isComposing): left to the IME.
    composing = title.evaluate(
        """(input) => input.dispatchEvent(new KeyboardEvent('keydown', {
             key: 'Enter', code: 'Enter', isComposing: true, bubbles: true, cancelable: true }))"""
    )
    # Safari delivers the confirming Enter right after the conversion with
    # keyCode 229: cancelled, so the browser does not submit the form.
    after_conversion = title.evaluate(
        """(input) => {
             const event = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true });
             Object.defineProperty(event, 'keyCode', { get: () => 229 });
             return input.dispatchEvent(event);
           }"""
    )
    page.wait_for_timeout(300)
    assert composing is True
    assert after_conversion is False
    assert sent == []
    expect(page).to_have_url(f"{e2e_server.url}{NEW_URL}")
    expect(title).to_have_value("へんかんちゅう")
    expect(page.locator("#title-error")).to_be_hidden()

    # A normal Enter goes through the check and creates the analysis.
    title.fill("変換後のタイトル")
    title.press("Enter")
    analysis_id = created_id(page)
    assert len(sent) == 1
    assert e2e_server.analysis(analysis_id)["title"] == "変換後のタイトル"


# ----- E-N03 ----------------------------------------------------------------

@pytest.mark.acceptance("E-N03")
def test_E_N03_sample_preview_transfer_and_create(page, e2e_server):
    open_new(page)
    samples = embedded_samples(page)
    assert len(samples) >= 2
    first, second = samples[0], samples[1]
    writes = []
    page.on("request", lambda r: writes.append(r.url) if r.method != "GET" else None)
    select = page.locator("#sampleSelect")
    preview = page.locator("#samplePreview")
    status = page.locator("[data-sample-status]")
    expect(preview).to_be_hidden()
    expect(status).to_be_hidden()
    expect(select.locator("option")).to_have_count(len(samples) + 1)

    # Preview: the chosen sample, shown as text.
    select.select_option(first["id"])
    expect(preview).to_be_visible()
    assert page.locator("#samplePreviewTopEvent").text_content() == first["top_event"]
    assert page.locator("#samplePreviewSystem").text_content() == first["system_context"]
    assert page.locator("#samplePreviewIncident").text_content() == first["incident_context"]
    select.select_option(second["id"])
    assert page.locator("#samplePreviewTopEvent").text_content() == second["top_event"]
    select.select_option("")
    expect(preview).to_be_hidden()

    # Transfer: the top event and both contexts are replaced and demo_points
    # is set; the title is not touched (J-21); nothing is saved.
    field(page, "top_event").fill("上書きされる頂上事象")
    select.select_option(first["id"])
    apply_button(page).click()
    expect(field(page, "top_event")).to_have_value(first["top_event"])
    expect(field(page, "system_context")).to_have_value(first["system_context"])
    expect(field(page, "incident_context")).to_have_value(first["incident_context"])
    expect(page.locator("#demoPointsInput")).to_have_value(first["demo_points"])
    expect(field(page, "title")).to_have_value("")
    expect(field(page, "title")).to_be_focused()  # the title is what to enter next
    expect(status).to_be_visible()
    expect(status).to_have_text(f"{SAMPLE_STATUS}（[{first['category']}] {first['title']}）")
    expect(page.locator("#ui-live-status")).to_contain_text("まだ保存されていません")
    assert writes == []
    assert analysis_count(e2e_server) == 0
    shown = page.evaluate("document.body.innerText")  # demo points are never shown
    assert first["demo_points"].strip().splitlines()[0] not in shown

    # Another sample replaces the fields and the demo points; a title typed
    # by the user stays as it is.
    field(page, "title").fill("サンプルから作成")
    select.select_option(second["id"])
    apply_button(page).click()
    expect(field(page, "top_event")).to_have_value(second["top_event"])
    expect(field(page, "incident_context")).to_have_value(second["incident_context"])
    expect(page.locator("#demoPointsInput")).to_have_value(second["demo_points"])
    expect(field(page, "title")).to_have_value("サンプルから作成")
    expect(apply_button(page)).to_be_focused()  # the title is filled: focus stays
    expect(status).to_contain_text(second["title"])

    # Create: saved as before, with the demo points.
    submit_button(page).click()
    analysis_id = created_id(page)
    stored = e2e_server.analysis(analysis_id)
    assert stored["title"] == "サンプルから作成"
    assert stored["top_event"] == second["top_event"]
    context = json.loads(stored["analysis_context"])
    for key in ("system_context", "incident_context", "demo_points"):
        assert unify(context[key]) == unify(second[key]), key
    exported = json.loads(e2e_server.export(analysis_id, "json"))
    assert unify(exported["analysis_context"]["demo_points"]) == unify(second["demo_points"])


# ----- E-N04 ----------------------------------------------------------------

@pytest.mark.acceptance("E-N04")
def test_E_N04_without_input_there_is_no_confirmation(page, e2e_server):
    dialogs = record_dialogs(page)
    open_new(page)
    cancel_link(page).click()
    expect(page).to_have_url(f"{e2e_server.url}/")

    # Spaces / line breaks only are not input, nor is a sample only chosen.
    open_new(page)
    field(page, "title").fill("   ")
    field(page, "system_context").fill("\n\n")
    page.locator("#sampleSelect").select_option(index=1)
    header_link(page, "分析一覧").click()
    expect(page).to_have_url(f"{e2e_server.url}/")

    open_new(page)
    with page.expect_navigation():
        header_link(page, "新規作成").click()  # the same page again
    expect(page).to_have_url(f"{e2e_server.url}{NEW_URL}")
    page.get_by_role("link", name="FTA分析支援ツール").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    expect(page.get_by_role("dialog")).to_have_count(0)
    assert dialogs == []
    assert analysis_count(e2e_server) == 0


@pytest.mark.acceptance("E-N04")
def test_E_N04_input_asks_to_continue_or_discard(page, e2e_server):
    dialogs = record_dialogs(page)
    open_new(page)
    cancel = cancel_link(page)

    # Each of the four fields counts as input.
    for name, label in FIELD_LABELS.items():
        field(page, name).fill("入力あり")
        cancel.click()
        dialog = leave_dialog(page)
        expect(dialog).to_be_visible()
        # Two choices only: saving is done by 作成して編集へ (J-12).
        expect(dialog.get_by_role("button")).to_have_text(["入力を続ける", "破棄して移動"])
        expect(dialog.get_by_role("listitem")).to_have_text([label])
        expect(dialog).to_contain_text("保存するには「入力を続ける」を選び、「作成して編集へ」を押してください。")
        expect(dialog.get_by_role("button", name="入力を続ける")).to_be_focused()
        dialog.get_by_role("button", name="入力を続ける").click()
        expect(dialog).to_have_count(0)
        expect(cancel).to_be_focused()  # back to the element that was operated
        expect(page).to_have_url(f"{e2e_server.url}{NEW_URL}")
        expect(field(page, name)).to_have_value("入力あり")
        field(page, name).fill("")

    # Esc is 入力を続ける; the header link asks the same.
    field(page, "title").fill("見出しのリンクで移動")
    header_list = header_link(page, "分析一覧")
    header_list.click()
    expect(leave_dialog(page)).to_be_visible()
    page.keyboard.press("Escape")
    expect(leave_dialog(page)).to_have_count(0)
    expect(header_list).to_be_focused()
    expect(field(page, "title")).to_have_value("見出しのリンクで移動")
    expect(page).to_have_url(f"{e2e_server.url}{NEW_URL}")

    # 破棄して移動: nothing is created and the browser does not ask again.
    header_list.click()
    leave_dialog(page).get_by_role("button", name="破棄して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}/")
    assert dialogs == []
    assert analysis_count(e2e_server) == 0


@pytest.mark.acceptance("E-N04")
def test_E_N04_discard_after_a_sample_transfer(page, e2e_server):
    dialogs = record_dialogs(page)
    open_new(page)
    field(page, "title").fill("破棄する分析")
    page.locator("#sampleSelect").select_option(index=1)
    apply_button(page).click()

    header_link(page, "新規作成").click()
    dialog = leave_dialog(page)
    expect(dialog.get_by_role("listitem")).to_have_text([
        "分析タイトル「破棄する分析」",
        "頂上事象",
        "AIへの参考情報：システム構成・対象範囲",
        "AIへの参考情報：障害発生時の状況・観測事実",
    ])
    with page.expect_navigation():
        dialog.get_by_role("button", name="破棄して移動").click()
    expect(page).to_have_url(f"{e2e_server.url}{NEW_URL}")
    for name in FIELD_SELECTORS:
        expect(field(page, name)).to_have_value("")
    expect(page.locator("#demoPointsInput")).to_have_value("")
    expect(page.locator("[data-sample-status]")).to_be_hidden()
    assert dialogs == []
    assert analysis_count(e2e_server) == 0


# ----- E-N05 ----------------------------------------------------------------

@pytest.mark.acceptance("E-N05")
def test_E_N05_double_click_creates_one_analysis(page, e2e_server):
    open_new(page)
    sent = create_requests(page)
    dialogs = record_dialogs(page)
    field(page, "title").fill("二重送信の確認")
    field(page, "top_event").fill("連打しても1件")
    submit_button(page).dblclick()
    created_id(page)
    expect(page.locator("#analysisTitle")).to_have_text("二重送信の確認")
    page.wait_for_timeout(300)
    assert len(sent) == 1
    assert analysis_count(e2e_server) == 1
    assert dialogs == []  # no leave confirmation for the submit itself


def _create_and_stay(page) -> list:
    """POST /analyses reaches the server (the analysis is created) but the
    browser gets 204 No Content and stays, so the page can be inspected in
    its sending state. (While a navigation request is pending, Playwright
    waits for it before any query of the page.)"""
    posts = []

    def handle(route):
        if route.request.method != "POST":
            route.continue_()
            return
        posts.append(route.request)
        answer = route.fetch(max_redirects=0)
        assert answer.status == 303, answer.text()
        route.fulfill(status=204)

    page.route("**/analyses", handle)
    return posts


@pytest.mark.acceptance("E-N05")
def test_E_N05_further_submits_are_ignored_once_sent(page, e2e_server):
    page.clock.install()
    open_new(page)
    posts = _create_and_stay(page)
    dialogs = record_dialogs(page)
    title = field(page, "title")
    title.fill("送信後の確認")
    submit_button(page).click()

    button = submit_button(page)
    expect(button).to_be_disabled()
    expect(button).to_have_text("作成しています…")
    expect(page.locator("#new-analysis-form")).to_have_attribute("aria-busy", "true")
    expect(page.locator("[data-submit-status]")).to_have_text("分析を作成しています…")
    expect(title).to_have_attribute("readonly", "")
    assert len(posts) == 1
    assert analysis_count(e2e_server) == 1
    assert dialogs == []  # the guard was released before the POST

    # Clicking again, Enter in the title and a scripted submit send nothing.
    button.click(force=True)
    title.press("Enter")
    page.evaluate("document.getElementById('new-analysis-form').requestSubmit()")
    page.wait_for_timeout(300)
    assert len(posts) == 1
    assert analysis_count(e2e_server) == 1

    # In-page links wait as well: following one would cancel the pending
    # navigation after the server may already have created the analysis.
    cancel_link(page).click()
    header_link(page, "分析一覧").click()
    page.get_by_role("link", name="FTA分析支援ツール").click()
    expect(page.locator(".ui-toast--info")).to_contain_text("分析を作成しています。画面が切り替わるまでお待ちください。")
    expect(leave_dialog(page)).to_have_count(0)
    page.wait_for_timeout(300)
    expect(page).to_have_url(f"{e2e_server.url}{NEW_URL}")
    assert dialogs == []

    # A slow answer (e.g. the server busy generating elsewhere) is explained.
    page.clock.run_for(10500)
    expect(page.locator("[data-submit-status]")).to_contain_text("サーバーが別の処理（生成など）を実行中の可能性があります")
    expect(button).to_be_disabled()


@pytest.mark.acceptance("E-N05")
def test_E_N05_restored_from_the_back_forward_cache_the_form_is_usable(page, e2e_server):
    # Playwright's Chromium runs without the back/forward cache, so the
    # restore is simulated with a pageshow event (persisted); the real cache
    # is part of the manual check.
    open_new(page)
    posts = _create_and_stay(page)
    field(page, "title").fill("戻ったときの確認")
    submit_button(page).click()
    expect(submit_button(page)).to_be_disabled()

    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))")
    expect(submit_button(page)).to_be_enabled()
    expect(submit_button(page)).to_have_text("作成して編集へ")
    expect(field(page, "title")).not_to_have_attribute("readonly", "")
    expect(page.locator("#new-analysis-form")).not_to_have_attribute("aria-busy", "true")
    expect(page.locator("[data-submit-status]")).to_have_text("")
    cancel_link(page).click()  # links are no longer held; the input is protected again
    expect(leave_dialog(page)).to_be_visible()
    leave_dialog(page).get_by_role("button", name="入力を続ける").click()
    expect(field(page, "title")).to_have_value("戻ったときの確認")
    expect(page.locator(".ui-toast--info")).to_have_count(0)
    assert len(posts) == 1


# ----- E-N06 ----------------------------------------------------------------

@pytest.mark.acceptance("E-N06")
def test_E_N06_browser_leave_confirmation_only_with_input(page, e2e_server):
    open_new(page)
    dialogs = record_dialogs(page, action="accept")
    page.reload()
    field(page, "title").fill("   ")  # spaces only: not input
    field(page, "incident_context").fill("消す入力")
    field(page, "incident_context").fill("")  # typed and removed again
    page.reload()
    assert dialogs == []

    for count, name in enumerate(FIELD_SELECTORS, start=1):
        field(page, name).fill("未保存の入力")
        page.reload()
        assert dialogs == ["beforeunload"] * count, name
        field(page, name).fill("")

    # A transferred sample is input as well.
    page.locator("#sampleSelect").select_option(index=1)
    apply_button(page).click()
    page.reload()
    assert dialogs == ["beforeunload"] * 5

    # Closing the tab asks as well.
    open_new(page)
    field(page, "title").fill("閉じる前の入力")
    with page.expect_event("close"):
        page.close(run_before_unload=True)
    assert dialogs == ["beforeunload"] * 6


# ----- servers with other sample files -------------------------------------

def _server_with_sample_file(tmp_path_factory, name: str, content):
    """Another app instance whose FTA_SAMPLE_SCENARIOS_FILE is a file written
    here (content None: the file does not exist)."""
    workdir = tmp_path_factory.mktemp(name)
    sample_file = workdir / "sample_scenarios.yaml"
    if content is not None:
        sample_file.write_text(content, encoding="utf-8")
    return start_server(workdir, free_port(), extra_env={"FTA_SAMPLE_SCENARIOS_FILE": str(sample_file)})


def _page_on(browser, viewport, server):
    server.reset()
    context = browser.new_context(viewport=viewport, locale="ja-JP", timezone_id="Asia/Tokyo", base_url=server.url)
    page = context.new_page()
    page.set_default_timeout(10000)
    return context, page, PageWatcher(page, server.url)


def _close_page(context, watcher, server):
    problems = watcher.problems()
    context.close()
    assert not problems, " / ".join(problems)
    assert not server.violations()


@pytest.fixture(scope="module")
def server_without_samples(tmp_path_factory):
    server = _server_with_sample_file(tmp_path_factory, "e2e-server-no-samples", None)
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def page_without_samples(browser, viewport, server_without_samples):
    context, page, watcher = _page_on(browser, viewport, server_without_samples)
    yield page
    _close_page(context, watcher, server_without_samples)


# Sample text that would become markup if it were inserted as HTML.
MARKUP_SAMPLE = {
    "id": "markup",
    "category": "<b>分類</b>",
    "title": '<img src=x onerror="window.__e2eInjected=1">見出し',
    "top_event": "<script>window.__e2eInjected=2</script>頂上事象 & <b>太字</b>",
    "system_context": '<img src=x onerror="window.__e2eInjected=3">\n2行目',
    "incident_context": "</dd><dd>別の項目</dd>",
    "demo_points": "<i>デモ観点</i>",
}


@pytest.fixture(scope="module")
def server_with_markup_samples(tmp_path_factory):
    content = "scenarios:\n  - " + "\n    ".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in MARKUP_SAMPLE.items())
    server = _server_with_sample_file(tmp_path_factory, "e2e-server-markup-samples", content + "\n")
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def page_with_markup_samples(browser, viewport, server_with_markup_samples):
    context, page, watcher = _page_on(browser, viewport, server_with_markup_samples)
    yield page
    _close_page(context, watcher, server_with_markup_samples)


@pytest.mark.acceptance("E-N03")
def test_E_N03_sample_and_input_text_stay_text(page_with_markup_samples, server_with_markup_samples):
    page = page_with_markup_samples
    open_new(page)
    sample = embedded_samples(page)[0]
    assert sample == MARKUP_SAMPLE  # YAML -> template (tojson) -> page, unchanged
    expect(page.locator("#sampleSelect option").nth(1)).to_have_text(
        f"[{MARKUP_SAMPLE['category']}] {MARKUP_SAMPLE['title']}")

    page.locator("#sampleSelect").select_option("markup")
    assert page.locator("#samplePreviewTopEvent").text_content() == MARKUP_SAMPLE["top_event"]
    assert page.locator("#samplePreviewSystem").text_content() == MARKUP_SAMPLE["system_context"]
    assert page.locator("#samplePreviewIncident").text_content() == MARKUP_SAMPLE["incident_context"]
    apply_button(page).click()
    expect(field(page, "top_event")).to_have_value(MARKUP_SAMPLE["top_event"])
    expect(field(page, "system_context")).to_have_value(MARKUP_SAMPLE["system_context"])
    expect(page.locator("#demoPointsInput")).to_have_value(MARKUP_SAMPLE["demo_points"])
    expect(page.locator("[data-sample-status]")).to_have_text(
        f"{SAMPLE_STATUS}（[{MARKUP_SAMPLE['category']}] {MARKUP_SAMPLE['title']}）")

    # User input in the leave dialog is text as well.
    field(page, "title").fill("<b>入力</b>")
    cancel_link(page).click()
    dialog = leave_dialog(page)
    expect(dialog.get_by_role("listitem").first).to_have_text("分析タイトル「<b>入力</b>」")
    dialog.get_by_role("button", name="入力を続ける").click()

    injected = page.evaluate(
        """() => ({
             flag: window.__e2eInjected ?? null,
             elements: document.querySelectorAll('main img, main b, main i, main script:not([src]):not([type="application/json"])').length,
           })"""
    )
    assert injected == {"flag": None, "elements": 0}

    submit_button(page).click()
    analysis_id = created_id(page)
    stored = server_with_markup_samples.analysis(analysis_id)
    assert stored["title"] == "<b>入力</b>"
    assert stored["top_event"] == MARKUP_SAMPLE["top_event"]
    context = json.loads(stored["analysis_context"])
    for key in ("system_context", "incident_context", "demo_points"):
        assert unify(context[key]) == unify(MARKUP_SAMPLE[key]), key


# ----- PR2-NO-SAMPLES -------------------------------------------------------

@pytest.mark.acceptance("PR2-NO-SAMPLES")
def test_without_sample_scenarios_the_form_still_creates(page_without_samples, server_without_samples):
    page = page_without_samples
    open_new(page)
    expect(page.get_by_role("heading", name="入力の使われ方")).to_be_visible()
    expect(page.locator("[data-sample-panel]")).to_have_count(0)
    expect(page.locator("#sampleSelect")).to_have_count(0)
    expect(page.locator("#sample-scenarios-data")).to_have_count(0)

    # The check and the unsaved-input protection work without the panel.
    submit_button(page).click()
    expect(page.locator("#title-error")).to_have_text("タイトルは必須です")
    field(page, "title").fill("サンプルなしの分析")
    cancel_link(page).click()
    leave_dialog(page).get_by_role("button", name="入力を続ける").click()
    field(page, "system_context").fill("構成のみ")
    submit_button(page).click()
    analysis_id = created_id(page)
    stored = server_without_samples.analysis(analysis_id)
    assert stored["title"] == "サンプルなしの分析"
    assert json.loads(stored["analysis_context"]) == {
        "system_context": "構成のみ", "incident_context": "", "demo_points": "",
    }

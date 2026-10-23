"""E2E: leaving the page during a generation and coming back (PR-6 review R7;
J-01, plan 5.3, 5.9.1).

E-G08  The page was left (the browser's confirmation accepted) while a
       generation was under way and comes back from the back/forward cache:
       the generation is ended once and never resumed — no request is sent
       again or later, a result received before leaving stays, a request sent
       but not answered is 結果不明, a parent not sent is 送信していません
       (never 通信失敗, success or 候補0件), a preparation is dropped. An answer
       or a wait of the left generation that ends later changes nothing (not
       a later generation, not the selection). A page that was not generating
       is unchanged; a repeated pageshow does nothing more. The leaving of an
       in-page link does not outlive the return: the browser asks again.
E-G12  After the return nothing of the generation stays: the phase, the
       status line, the restrictions, 生成中・待機中 in the log.

Two kinds of test, told apart in their names:

* simulated (``_simulated``): pagehide and pageshow (persisted) are
  dispatched to the page, and the order of the events and of the answers is
  set with page.route. This covers every order but is no back/forward cache:
  the page is never actually left.
* real (``_real_bfcache``): the page is really left (another address, an
  in-page link) and the browser goes back; the test requires
  ``pageshow.persisted === true`` and the same document (a value set before
  leaving is still there), so a reload never counts. Playwright starts
  Chromium with ``--disable-back-forward-cache``; these tests start their own
  browser without it (with no --browser-channel and headless: Playwright's
  full Chromium, ``channel="chromium"``, since the headless shell restores
  nothing from the cache). The generation is kept running by the stub's
  server-side delay, not by page.route: a request held in the browser
  keeps the navigation from completing.
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.edit_helpers import (
    choose,
    expect_selected,
    gen_log,
    gen_status,
    generate_button,
    generation_requests,
    hold,
    item,
    judgement_button,
    leave_dialog,
    leave_link,
    log_row,
    open_edit,
    phase,
    pump,
    step_button,
    step_panel,
    toast,
    wait_phase,
)
from tests.e2e.support import PageWatcher, expect, record_dialogs

pytestmark = [pytest.mark.e2e]

SINGLE = pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])

LEFT_UNKNOWN = "ページを離れたため、この親の結果を確認できていません（要求は送信済みで、サーバーで作成された可能性があります。保存済みの内容を確かめてください）"
LEFT_SKIPPED = "ページを離れたため送信していません（戻った後も自動では送信しません）"
LEFT_ENDED = "ページを離れる前に実行中だった生成を終了しました。戻った後に生成の要求を送り直してはいません（サーバーでの処理は止めていません）。結果は生成ログで確かめてください。"
LEFT_PREPARING = "ページを離れたため、生成の準備を取りやめました。生成の要求は送っていません（送信済みの保存は取り消されません）。"
SUMMARY_UNKNOWN = "二次要因の通常生成：作成を確認できませんでした（1件の親は結果不明。詳細は生成ログ）"


def setup(e2e_server, title):
    """Two Yes parents of the 二次 generation: A and C (B is not a parent)."""
    analysis_id = e2e_server.create_analysis(title, top_event="頂上", system_context="構成")
    a = e2e_server.add_level1(analysis_id, "親A")
    b = e2e_server.add_level1(analysis_id, "要因B")
    c = e2e_server.add_level1(analysis_id, "親C")
    e2e_server.update_node(a, user_judgement="yes")
    e2e_server.update_node(c, user_judgement="yes")
    return analysis_id, a, b, c


def hide(page):
    """Simulated: the page is left into the back/forward cache."""
    page.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: true }))")


def show(page):
    """Simulated: the page comes back from the back/forward cache."""
    page.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))")


def start_held(page, analysis_id):
    held = hold(page, f"**/analyses/{analysis_id}/generate/level/2")
    step_button(page, 3).click()
    generate_button(page, 2).click()
    pump(page, lambda: len(held) == 1)
    assert phase(page) == "running"
    return held


def expect_nothing_under_way(page, b):
    """E-G12: nothing of the generation is left."""
    wait_phase(page, "idle", timeout=15)
    expect(gen_status(page)).to_be_hidden()
    expect(page.locator("[data-edit-page]")).to_have_attribute("data-generation-phase", "idle")
    expect(generate_button(page, 2)).to_be_enabled()
    expect(judgement_button(item(page, "work", b), b, "yes")).to_be_enabled()
    expect(step_panel(page, 3).locator('[data-action="add"]').first).to_be_enabled()
    expect(leave_link(page)).not_to_have_attribute("aria-disabled", "true")
    log = gen_log(page)
    if log.count():
        expect(log).not_to_contain_text("生成中…")
        expect(log).not_to_contain_text("待機中")
        expect(log).not_to_contain_text("進行中")
    expect(page.locator('[data-gen-badge][data-category="running"], [data-gen-badge][data-category="waiting"]')).to_have_count(0)


def expect_left_rows(page, a, c, *, observed):
    row_a, row_c = log_row(page, a), log_row(page, c)
    expect(row_a).to_have_attribute("data-category", "unknown")
    expect(row_a).to_contain_text("結果不明")
    expect(row_a).to_contain_text(LEFT_UNKNOWN)
    if observed:
        expect(row_a).to_contain_text(f"この親の下に新しいAIの要因が{observed}件あります")
    expect(row_c).to_have_attribute("data-category", "skipped")
    expect(row_c).to_contain_text(LEFT_SKIPPED)
    log = gen_log(page)
    expect(log).not_to_contain_text("通信失敗")
    expect(log.locator("[data-gen-log-summary]")).to_contain_text("結果不明の親 1件")
    for wrong in ("作成しました", "生成候補がありませんでした"):
        expect(page.locator("#ui-toasts .ui-toast").filter(has_text=wrong)).to_have_count(0)


# ----- simulated: running ---------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("E-G08", "E-G12")
@pytest.mark.parametrize("order", ["answer-while-hidden", "answer-after-return"])
def test_E_G08_left_while_running_and_back_simulated(page, e2e_server, order):
    analysis_id, a, b, c = setup(e2e_server, f"生成中に離れて戻る：{order}")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = start_held(page, analysis_id)
    hide(page)
    if order == "answer-while-hidden":
        # The path of the review: the answer ends the requests while the page
        # is hidden (before R7 nothing was settled and the phase stayed).
        held[0].continue_()
        pump(page, lambda: len(e2e_server.stub_calls()) == 1)
        page.wait_for_timeout(800)
        assert [r["body"] for r in requests] == [{"parent_id": a}]  # C is not sent while hidden
        show(page)
    else:
        show(page)  # the answer is still on its way
    expect_nothing_under_way(page, b)
    expect_left_rows(page, a, c, observed=3 if order == "answer-while-hidden" else 0)
    expect(toast(page, SUMMARY_UNKNOWN, "error", exact=True)).to_be_visible()
    expect(toast(page, LEFT_ENDED, "info", exact=True)).to_be_visible()
    show(page)  # a repeated pageshow does nothing more
    page.wait_for_timeout(300)
    expect(toast(page, LEFT_ENDED, "info", exact=True)).to_have_count(1)
    expect(toast(page, SUMMARY_UNKNOWN, "error", exact=True)).to_have_count(1)
    if order == "answer-after-return":
        # A later generation, then the left one's answer arrives: it changes
        # neither the later generation nor the selection.
        choose(page, b)
        step_button(page, 3).click()
        generate_button(page, 2).click()
        pump(page, lambda: len(held) == 2)
        assert phase(page) == "running"
        held[0].continue_()  # the left generation's answer
        pump(page, lambda: len(e2e_server.stub_calls()) == 1)
        page.wait_for_timeout(800)
        assert phase(page) == "running"
        expect(log_row(page, a)).to_have_attribute("data-category", "running")
        expect(log_row(page, c)).to_have_attribute("data-category", "waiting")
        expect_selected(page, b, "要因B")
        assert [r["body"] for r in requests] == [{"parent_id": a}, {"parent_id": a}]
        held[1].continue_()
        pump(page, lambda: len(held) == 3)
        held[2].continue_()
        expect_nothing_under_way(page, b)
        expect(log_row(page, a)).to_have_attribute("data-category", "created")
        expect(log_row(page, c)).to_have_attribute("data-category", "created")
        expect_selected(page, b, "要因B")
        assert [r["body"] for r in requests] == [{"parent_id": a}, {"parent_id": a}, {"parent_id": c}]
    else:
        page.wait_for_timeout(500)
        assert [r["body"] for r in requests] == [{"parent_id": a}]  # nothing sent again after the return
    # The stored log is the settled one (a reload shows no running state).
    page.reload()
    step_button(page, 3).click()
    expect(page.locator("[data-gen-log-restored]")).to_be_visible()
    expect(gen_log(page)).not_to_contain_text("生成中…")


# ----- simulated: preparing ---------------------------------------------------------

@SINGLE
@pytest.mark.acceptance("E-G08", "E-G12")
@pytest.mark.parametrize("order", ["save-ends-while-hidden", "save-ends-after-return"])
def test_E_G08_left_while_preparing_and_back_simulated(page, e2e_server, order):
    analysis_id, a, b, c = setup(e2e_server, f"準備中に離れて戻る：{order}")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    held = hold(page, f"**/analyses/{analysis_id}/top-event")
    step_button(page, 1).click()
    page.fill("#topEventInput", "保存中の頂上事象")
    step_panel(page, 1).locator('[data-save-button="top-event"]').click()
    pump(page, lambda: len(held) == 1)
    step_button(page, 3).click()
    generate_button(page, 2).click()
    pump(page, lambda: phase(page) == "preparing")
    hide(page)
    if order == "save-ends-while-hidden":
        held[0].continue_()  # the preparation goes on while hidden: it must request nothing
        page.wait_for_timeout(800)
        assert requests == []
        show(page)
    else:
        show(page)
        expect_nothing_under_way(page, b)
        held[0].continue_()  # the wait of the dropped preparation ends now
        page.wait_for_timeout(800)
    expect_nothing_under_way(page, b)
    expect(toast(page, LEFT_PREPARING, "info", exact=True)).to_be_visible()
    assert requests == []
    assert e2e_server.stub_calls() == []
    assert e2e_server.analysis(analysis_id)["top_event"] == "保存中の頂上事象"  # the save was not cancelled
    # A later generation runs normally.
    generate_button(page, 2).click()
    expect_nothing_under_way(page, b)
    assert [r["body"] for r in requests] == [{"parent_id": a}, {"parent_id": c}]
    expect(log_row(page, a)).to_have_attribute("data-category", "created")


# ----- simulated: finishing, idle -----------------------------------------------------

@SINGLE
@pytest.mark.acceptance("E-G08", "E-G12")
def test_E_G08_left_while_finishing_and_back_simulated(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "反映中に離れて戻る")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    step_button(page, 3).click()
    held = []

    def page_fetch(route):
        if route.request.resource_type == "fetch":
            held.append(route)
        else:
            route.continue_()

    page.route(re.compile(rf".*/analyses/{analysis_id}$"), page_fetch)
    generate_button(page, 2).click()
    pump(page, lambda: len(held) == 1)
    assert phase(page) == "finishing"
    hide(page)
    show(page)
    # Its own finishing goes on: the restrictions stay until the update ends.
    page.wait_for_timeout(500)
    assert phase(page) == "finishing"
    expect(generate_button(page, 2)).to_be_disabled()
    held[0].continue_()
    expect_nothing_under_way(page, b)
    expect(log_row(page, a)).to_contain_text("作成 3件")  # results received before leaving stay
    expect(log_row(page, c)).to_contain_text("作成 3件")
    expect(toast(page, LEFT_ENDED, "info")).to_have_count(0)
    assert [r["body"] for r in requests] == [{"parent_id": a}, {"parent_id": c}]


@SINGLE
@pytest.mark.acceptance("E-G08")
def test_E_G08_a_page_that_was_not_generating_comes_back_unchanged_simulated(page, e2e_server):
    analysis_id, a, b, c = setup(e2e_server, "生成していないページ")
    open_edit(page, analysis_id)
    requests = generation_requests(page)
    choose(page, b)
    hide(page)
    show(page)
    show(page)
    page.wait_for_timeout(500)
    assert phase(page) == "idle" and requests == []
    expect(page.locator("#ui-toasts .ui-toast")).to_have_count(0)
    expect_selected(page, b, "要因B")
    expect_nothing_under_way(page, b)


@SINGLE
@pytest.mark.acceptance("E-G08")
def test_E_G08_the_browser_asks_again_after_the_return_simulated(page, e2e_server):
    """The leaving of an in-page link (or of the reload after a failed update)
    does not outlive a return from the cache."""
    analysis_id, a, b, c = setup(e2e_server, "戻った後の離脱確認")
    open_edit(page, analysis_id)
    page.evaluate("async () => (await import('/static/js/common/unsaved.js')).markPageLeaving()")
    show(page)
    dialogs = record_dialogs(page, action="dismiss")
    held = start_held(page, analysis_id)
    page.evaluate("() => { window.__pr7Mark = 'kept'; window.location.reload(); }")
    pump(page, lambda: dialogs == ["beforeunload"])
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__pr7Mark") == "kept"
    assert phase(page) == "running"
    for route in held:
        route.continue_()
    pump(page, lambda: len(held) == 2)
    held[1].continue_()
    expect_nothing_under_way(page, b)


# ----- real back/forward cache ---------------------------------------------------------

# Recorded in the page from its first script on: each pageshow (persisted),
# the order of pagehide / pageshow and of every generation request sent, and
# the generation's phase when the page was hidden. (Playwright's request
# events miss requests of a page that is being left, so the page records
# them itself; the stub's records are the server's side.)
PAGE_RECORDER = """
window.__pr7Shows = [];
window.__pr7Events = [];
window.addEventListener('pageshow', (event) => {
  window.__pr7Shows.push(event.persisted);
  window.__pr7Events.push('pageshow:' + event.persisted);
});
window.addEventListener('pagehide', (event) => {
  const root = document.querySelector('[data-edit-page]');
  window.__pr7PhaseAtHide = root ? root.dataset.generationPhase : null;
  window.__pr7Events.push('pagehide:' + event.persisted);
});
const pageFetch = window.fetch;
window.fetch = function (url, init) {
  if (String(url).includes('/generate/level/')) window.__pr7Events.push('generate ' + (init && init.body));
  return pageFetch.apply(this, arguments);
};
"""


@pytest.fixture
def bfcache_page(launch_browser, browser_type_launch_args, browser_context_args, pytestconfig, e2e_server):
    """A page of a browser with the back/forward cache (see the module's
    docstring), watched like the `page` fixture's."""
    options = {"ignore_default_args": ["--disable-back-forward-cache"]}
    if not pytestconfig.getoption("--browser-channel") and browser_type_launch_args.get("headless", True):
        options["channel"] = "chromium"
    browser = launch_browser(**options)
    context = browser.new_context(**browser_context_args)
    page = context.new_page()
    page.set_default_timeout(10000)
    page.add_init_script(PAGE_RECORDER)
    watcher = PageWatcher(page, e2e_server.url)
    try:
        yield page, watcher
        problems = watcher.problems(PageWatcher.START, watcher.mark())
        assert not problems, " / ".join(problems)
    finally:
        context.close()
        browser.close()


def go_back_from_cache(page, url_part: str):
    """History back; the page must come from the cache (the same document)."""
    page.go_back(wait_until="commit")
    pump(page, lambda: url_part in page.url and page.evaluate(
        "() => Array.isArray(window.__pr7Shows) && window.__pr7Shows.length > 1"), timeout=15)
    shows = page.evaluate("() => window.__pr7Shows")
    same = page.evaluate("() => window.__pr7Same === 'before leaving'")
    assert shows[-1] is True and same, (
        f"戻った画面がバックフォワードキャッシュから復元されませんでした（pageshow.persisted の記録 {shows}、"
        f"同じ文書 {same}）。このブラウザでは実ブラウザの復元を確認できません（未検証）")
    return shows


@SINGLE
@pytest.mark.acceptance("E-G08", "E-G12")
def test_E_G08_left_while_running_and_back_real_bfcache(bfcache_page, e2e_server):
    page, _ = bfcache_page
    analysis_id, a, b, c = setup(e2e_server, "実ブラウザ：生成中に離れて戻る")
    d = e2e_server.add_level1(analysis_id, "親D")
    e2e_server.update_node(d, user_judgement="yes")  # three parents: A, C, D
    e2e_server.set_control(mode="delay", delay_seconds=3)  # each request takes 3 s on the server
    open_edit(page, analysis_id)
    dialogs = record_dialogs(page, action="accept")
    page.evaluate("() => { window.__pr7Same = 'before leaving'; }")
    step_button(page, 3).click()
    generate_button(page, 2).click()
    pump(page, lambda: len(e2e_server.stub_calls()) == 1)  # A's request is on the server
    page.evaluate("() => { window.location.href = '/'; }")  # another address of the app
    pump(page, lambda: page.url.rstrip("/") == e2e_server.url.rstrip("/"), timeout=15)
    page.wait_for_load_state()
    assert dialogs == ["beforeunload"]  # the browser asked; accepted
    page.wait_for_timeout(7000)  # every request sent before leaving has been answered by the server
    shows = go_back_from_cache(page, f"/analyses/{analysis_id}")
    assert page.evaluate("() => window.__pr7PhaseAtHide") == "running"  # left while it ran
    expect_nothing_under_way(page, b)
    page.wait_for_timeout(1500)  # late answers of the left generation have arrived
    expect_nothing_under_way(page, b)
    events = page.evaluate("() => window.__pr7Events")
    rows = {name: log_row(page, node) for name, node in (("A", a), ("C", c), ("D", d))}
    categories = {name: row.get_attribute("data-category") for name, row in rows.items()}
    print(f"pageshow.persisted: {shows}; events: {events}; rows after the return: {categories}")
    # Nothing is sent after the return (never resumed, never sent again).
    returned = events.index("pageshow:true")
    assert not [event for event in events[returned:] if event.startswith("generate")], events
    sent = [event for event in events if event.startswith("generate")]
    calls = [call["parent_factor"] for call in e2e_server.stub_calls()]
    assert len(calls) == len(set(calls)) == len(sent)  # no parent twice
    # Whatever the browser let run before it hid the page: a result received
    # stays, a request sent without a judged answer is 結果不明, a parent not
    # sent is 送信していません — the first not-done row is 結果不明 and the
    # rest are not sent; never 通信失敗 or anything under way.
    order = ["A", "C", "D"]
    done = [name for name in order if categories[name] == "created"]
    assert done == order[:len(done)] and len(done) < 3, categories
    assert categories[order[len(done)]] == "unknown", categories
    expect(rows[order[len(done)]]).to_contain_text(LEFT_UNKNOWN)
    for name in order[len(done) + 1:]:
        assert categories[name] == "skipped", categories
        expect(rows[name]).to_contain_text(LEFT_SKIPPED)
    assert len(sent) == len(done) + 1
    expect(gen_log(page)).not_to_contain_text("通信失敗")
    expect(toast(page, LEFT_ENDED, "info", exact=True)).to_be_visible()


@SINGLE
@pytest.mark.acceptance("E-G08")
def test_E_G08_the_browser_asks_again_after_the_return_real_bfcache(bfcache_page, e2e_server):
    page, _ = bfcache_page
    analysis_id, a, b, c = setup(e2e_server, "実ブラウザ：戻った後の離脱確認")
    open_edit(page, analysis_id)
    page.evaluate("() => { window.__pr7Same = 'before leaving'; }")
    # An in-page link with typed input: the page's own three choices, then the
    # page itself leaves (破棄して移動) — no browser question for that.
    step_button(page, 1).click()
    page.fill("#systemContextInput", "離れる前に入力した参考情報")
    leave_link(page).click()
    leave_dialog(page).get_by_role("button", name="破棄して移動").click()
    pump(page, lambda: f"/analyses/{analysis_id}" not in page.url, timeout=15)
    page.wait_for_load_state()
    go_back_from_cache(page, f"/analyses/{analysis_id}")
    dialogs = record_dialogs(page, action="dismiss")
    held = start_held(page, analysis_id)
    page.evaluate("() => { window.__pr7Mark = 'kept'; window.location.reload(); }")
    pump(page, lambda: dialogs == ["beforeunload"])
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__pr7Mark") == "kept"
    assert phase(page) == "running"
    held[0].continue_()
    pump(page, lambda: len(held) == 2)
    held[1].continue_()
    expect_nothing_under_way(page, b)

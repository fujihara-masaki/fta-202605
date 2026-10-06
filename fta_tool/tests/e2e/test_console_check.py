"""E2E: the page check lets through only the browser's own 404 for
/favicon.ico (the user's decision of 2026-10-03; tests/e2e/support.py), with
the browser's real events: every other 404 of the same server, even with the
same message and the path /favicon.ico (an img, a fetch, a query), stays a
console error that fails a test, and is not counted as the known exception.

No acceptance ID: it checks the check that every E2E test goes through.
"""

from __future__ import annotations

import pytest

from tests.e2e.support import FAVICON_404_TEXT, FAVICON_RESOURCE_TYPE, expect

pytestmark = pytest.mark.e2e

# Loads of the page that fail with 404 (none of them is the browser's own request).
PAGE_LOADS = """() => {
  const add = (tag, attributes, parent) => {
    const element = document.createElement(tag);
    Object.assign(element, attributes);
    (parent || document.body).append(element);
  };
  add('script', { src: '/e2e-missing.js' });
  add('link', { rel: 'stylesheet', href: '/e2e-missing.css' }, document.head);
  add('img', { src: '/e2e-missing.png' });
  add('img', { src: '/favicon.ico?v=1' });
  add('img', { src: '/favicon.ico' });
  fetch('/e2e-missing-api').catch(() => {});
  fetch('/favicon.ico').catch(() => {});
}"""
PATHS = ["/e2e-missing.js", "/e2e-missing.css", "/e2e-missing.png", "/favicon.ico?v=1", "/favicon.ico",
         "/e2e-missing-api", "/favicon.ico"]


def test_only_the_browsers_own_favicon_404_is_let_through(page, page_watch, e2e_server):
    assert page_watch.cdp_error == ""  # the browser's records can be read (else nothing is let through)
    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    before = page_watch.mark()
    page.evaluate(PAGE_LOADS)

    def failed_loads(end: int) -> list[str]:  # the console errors of the loads above
        pairs = zip(page_watch.console_errors[before[0]:end], page_watch.console_error_urls[before[0]:end])
        return sorted(url.removeprefix(e2e_server.url) for text, url in pairs
                      if text == FAVICON_404_TEXT and url.removeprefix(e2e_server.url) in PATHS)

    for _ in range(100):  # events come in while Playwright waits
        if len(failed_loads(len(page_watch.console_errors))) >= len(PATHS):
            break
        page.wait_for_timeout(100)
    page.wait_for_timeout(500)  # and what comes right after them
    checked = page_watch.mark()
    loads = failed_loads(checked[0])
    # Each load above once, and possibly the browser's own request for the icon.
    assert loads in (sorted(PATHS), sorted(PATHS + ["/favicon.ico"])), loads

    # Every load above is a console error that fails a test; only the
    # browser's own request (if it came now) is the known exception.
    problems = " ".join(page_watch.problems(before, checked))
    for path in set(PATHS):
        assert problems.count(f"（{e2e_server.url}{path}）") == PATHS.count(path), (path, problems)
    now = [event for index, event in page_watch.known.items() if before[0] <= index < checked[0]]
    assert len(now) == len(loads) - len(PATHS)
    for event in page_watch.known.values():
        assert event == {"url": e2e_server.url + "/favicon.ico", "text": FAVICON_404_TEXT, "status": 404,
                         "type": FAVICON_RESOURCE_TYPE, "request_id": event["request_id"]}

    # Judged once: checking again counts nothing twice.
    known = dict(page_watch.known)
    assert " ".join(page_watch.problems(before, checked)) == problems
    assert page_watch.known == known

    # The test forced these 404s: expected here (by their message only).
    page_watch.allow_console_error(r"^Failed to load resource: the server responded with a status of 404 \(Not Found\)$")

"""E2E: the page check lets no console error through, with the browser's
real events. Until PR-7 the browser's own 404 for /favicon.ico was let
through (the user's decision of 2026-10-03); PR-7 gave every screen its icon
and removed that exception (tests/e2e/support.py), so a 404 of
/favicon.ico — asked for by the page or by the browser — fails a test like a
404 of anything else, and the icon itself loads without an error.

No acceptance ID: it checks the check that every E2E test goes through.
"""

from __future__ import annotations

import pytest

from tests.e2e.support import FAVICON_URL, NOT_FOUND_TEXT, expect

pytestmark = pytest.mark.e2e

# Loads of the page that fail with 404, /favicon.ico among them.
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


def test_every_404_fails_the_favicon_ico_included(page, page_watch, e2e_server):
    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    before = page_watch.mark()
    page.evaluate(PAGE_LOADS)

    def failed_loads(end: int) -> list[str]:  # the console errors of the loads above
        pairs = zip(page_watch.console_errors[before[0]:end], page_watch.console_error_urls[before[0]:end])
        return sorted(url.removeprefix(e2e_server.url) for text, url in pairs
                      if text == NOT_FOUND_TEXT and url.removeprefix(e2e_server.url) in PATHS)

    for _ in range(100):  # events come in while Playwright waits
        if len(failed_loads(len(page_watch.console_errors))) >= len(PATHS):
            break
        page.wait_for_timeout(100)
    page.wait_for_timeout(500)  # and what comes right after them
    checked = page_watch.mark()
    assert failed_loads(checked[0]) == sorted(PATHS)

    # Every one of them is a console error that fails a test.
    problems = " ".join(page_watch.problems(before, checked))
    for path in set(PATHS):
        assert problems.count(f"（{e2e_server.url}{path}）") == PATHS.count(path), (path, problems)

    # The test forced these 404s: expected here (by their message only).
    page_watch.allow_console_error(r"^Failed to load resource: the server responded with a status of 404 \(Not Found\)$")


def test_the_apps_icon_loads_without_an_error(page, page_watch):
    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    before = page_watch.mark()
    loaded = page.evaluate("""(url) => new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve([img.naturalWidth, img.naturalHeight]);
      img.onerror = () => resolve(null);
      img.src = url;
    })""", FAVICON_URL)
    assert loaded and loaded[0] > 0 and loaded[1] > 0, loaded
    page.wait_for_timeout(300)
    assert page_watch.problems(before) == []

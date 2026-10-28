"""Checks of what is on the screen, from the page's real DOM (PR-7, E-V01〜
E-V03, E-F01; plan 5.9.4, 8.7): positions, sizes, visibility and the
element drawn on top. Screenshots only complement them (the visual review).

* reach(): the control is shown (visible), fully inside the display area
  after scrolling the pane it is in (never the page sideways), and on top
  at five points of it (its centre and four points near its corners), so
  nothing (a notification, the folded navigation, another pane) covers it.
  Only the notifications at the bottom may be over it at first: the panes
  keep room below their content (128px, PR-4) so that it can be scrolled
  above them, and reach() does that scroll as a user would (it fails if the
  pane cannot scroll that far);
* page_scroll(): the page's own scroll size against the display area;
* pane_scroll(): the panes' sideways scrolling;
* layout(): which layout the edit page has (three panes or the folded
  navigation) and where its panes are.
"""

from __future__ import annotations

from typing import Optional

from tests.e2e.support import expect

# Fully inside: up to half a CSS px out (fractional boxes at a DPR of 1.25).
EDGE = 0.5

HIT = """(el) => {
  const r = el.getBoundingClientRect();
  const w = document.documentElement.clientWidth, h = document.documentElement.clientHeight;
  const points = [[0.5, 0.5], [0.15, 0.2], [0.85, 0.2], [0.15, 0.8], [0.85, 0.8]];
  const misses = [];
  for (const [fx, fy] of points) {
    const x = r.x + r.width * fx, y = r.y + r.height * fy;
    const hit = document.elementFromPoint(x, y);
    if (!(hit && (hit === el || el.contains(hit)))) {
      misses.push({ x: Math.round(x), y: Math.round(y),
                    over: hit ? (hit.id ? '#' + hit.id : hit.tagName.toLowerCase() + (hit.className && typeof hit.className === 'string' ? '.' + hit.className.trim().split(/\\s+/).join('.') : '')) : null });
    }
  }
  return { box: [r.x, r.y, r.width, r.height], client: [w, h], misses,
           scrollX: window.scrollX, scrollY: window.scrollY };
}"""

# Scroll the nearest scrolling ancestor of the element so that its bottom is
# above the top of the notifications (plus a small gap); false if it cannot.
ABOVE_NOTIFICATIONS = """(el) => {
  const toasts = [...document.querySelectorAll('#ui-toasts .ui-toast')];
  if (!toasts.length) return false;
  const top = Math.min(...toasts.map((t) => t.getBoundingClientRect().top));
  let box = el.parentElement;
  while (box && !(box.scrollHeight > box.clientHeight && /(auto|scroll)/.test(getComputedStyle(box).overflowY))) {
    box = box.parentElement;
  }
  if (!box) return false;
  const need = el.getBoundingClientRect().bottom - top + 8;
  if (need <= 0) return true;
  const before = box.scrollTop;
  box.scrollTop = before + need;
  return box.scrollTop - before >= need - 1;
}"""

PAGE_SCROLL = """() => {
  const root = document.documentElement;
  return { scroll: [root.scrollWidth, root.scrollHeight], client: [root.clientWidth, root.clientHeight],
           at: [window.scrollX, window.scrollY] };
}"""

PANE_SCROLL = """() => {
  const out = {};
  for (const el of document.querySelectorAll('[data-scroll]')) {
    out[el.dataset.scroll] = { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
                               shown: el.offsetParent !== null };
  }
  return out;
}"""

LAYOUT = """() => {
  const box = (sel) => { const el = document.querySelector(sel); if (!el || el.offsetParent === null) return null;
    const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; };
  const toggle = document.querySelector('[data-nav-toggle]');
  return { nav: box('#edit-nav'), center: box('#edit-work-area'), inspector: box('#edit-inspector'),
           toggle: toggle && toggle.offsetParent !== null ? toggle.getAttribute('aria-expanded') : null,
           folded: window.matchMedia('(width < 1280px)').matches };
}"""


def describe(locator) -> str:
    return str(locator).replace("Locator@", "")


def reach(locator, *, timeout: Optional[float] = None, name: str = "", scroll: bool = True) -> dict:
    """The control can be reached and used as it is shown: see the module.
    Scrolls the pane it is in (Playwright scrolls the nearest scrolling
    ancestors), never asks for a sideways scroll of the page. scroll=False:
    it must be in view as it is (e.g. 保存・取消 while a field is in use)."""
    expect(locator).to_be_visible(timeout=timeout)
    if scroll:
        locator.scroll_into_view_if_needed(timeout=timeout)
    found = locator.evaluate(HIT)
    if scroll and found["misses"] and all(miss["over"] and "ui-toast" in miss["over"] for miss in found["misses"]):
        if locator.evaluate(ABOVE_NOTIFICATIONS):
            found = locator.evaluate(HIT)
    x, y, w, h = found["box"]
    width, height = found["client"]
    label = name or describe(locator)
    assert found["scrollX"] == 0, f"{label}：ページを横にスクロールしないと届かない（scrollX {found['scrollX']}）"
    assert x >= -EDGE and y >= -EDGE and x + w <= width + EDGE and y + h <= height + EDGE, (
        f"{label}：表示領域 {width}×{height} の外にはみ出す（{x:.1f}, {y:.1f}, {w:.1f}×{h:.1f}）")
    assert not found["misses"], f"{label}：ほかの要素に覆われている {found['misses']}"
    return found


def page_scroll(page) -> dict:
    return page.evaluate(PAGE_SCROLL)


def assert_no_page_hscroll(page, what: str = "") -> None:
    found = page_scroll(page)
    assert found["scroll"][0] <= found["client"][0], (
        f"ページ全体が横にスクロールする{('（' + what + '）') if what else ''}："
        f"scrollWidth {found['scroll'][0]} > clientWidth {found['client'][0]}")
    assert found["at"][0] == 0


def pane_scroll(page) -> dict:
    return page.evaluate(PANE_SCROLL)


def layout(page) -> dict:
    return page.evaluate(LAYOUT)


def no_overlap(page, selector: str, scope: str = "") -> None:
    """The visible elements of `selector` (inside each `scope`, or the whole
    page) do not overlap one another (E-F01)."""
    found = page.evaluate("""([selector, scope]) => {
      const scopes = scope ? [...document.querySelectorAll(scope)] : [document];
      const clash = [];
      for (const root of scopes) {
        const els = [...root.querySelectorAll(selector)].filter((el) => el.offsetParent !== null
          && getComputedStyle(el).visibility !== 'hidden');
        const boxes = els.map((el) => [el, el.getBoundingClientRect()]);
        for (let i = 0; i < boxes.length; i += 1) {
          for (let j = i + 1; j < boxes.length; j += 1) {
            const [a, ra] = boxes[i], [b, rb] = boxes[j];
            if (a.contains(b) || b.contains(a)) continue;
            const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
            const h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
            if (w > 0.5 && h > 0.5) clash.push([a.textContent.trim().slice(0, 30), b.textContent.trim().slice(0, 30)]);
          }
        }
      }
      return clash;
    }""", [selector, scope])
    assert not found, f"重なっている（{selector}）：{found}"


def not_clipped(page, selector: str, *, allow_ellipsis: str = "") -> list[str]:
    """Visible elements of `selector` whose text is cut off (their content
    is wider or taller than their box and the overflow is hidden), except
    those inside `allow_ellipsis` (cut on purpose with an ellipsis)."""
    return page.evaluate("""([selector, allowed]) => {
      const cut = [];
      for (const el of document.querySelectorAll(selector)) {
        if (el.offsetParent === null) continue;
        if (allowed && el.closest(allowed)) continue;
        const style = getComputedStyle(el);
        const hides = (v) => v !== 'visible';
        const wide = el.scrollWidth > el.clientWidth + 1 && hides(style.overflowX);
        const tall = el.scrollHeight > el.clientHeight + 1 && hides(style.overflowY);
        if (wide || tall) cut.push(`${el.tagName.toLowerCase()}「${el.textContent.trim().slice(0, 40)}」`
          + ` ${el.scrollWidth}×${el.scrollHeight} > ${el.clientWidth}×${el.clientHeight}`);
      }
      return cut;
    }""", [selector, allow_ellipsis])

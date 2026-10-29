"""Checks of what is on the screen, from the page's real DOM (PR-7, E-V01〜
E-V03, E-F01; plan 5.9.4, 8.7): positions, sizes, visibility and the
element drawn on top. Screenshots only complement them (the visual review).

* reach(): the control is shown (visible), fully inside the display area
  and on top at five points of it (its centre and four points near its
  corners), so nothing (a notification, the folded navigation, another
  pane) covers it; never by scrolling the page sideways. Two kinds of
  control (plan 8.7, conditions 2 and 4):
  - scroll=False, the main buttons (保存・取消 of the inspector, the
    buttons of a dialog): as shown, without any scrolling, and not covered
    (by a notification either);
  - scroll=True, a control in a pane that scrolls: reached by scrolling
    that pane as a user would. If then only the notifications at the
    bottom are over it, the pane is scrolled above them (the panes keep
    128px of room below their content, PR-4); it fails if the pane cannot
    scroll that far.
  Each call tells the observers (OBSERVERS) how the control was reached —
  REACHED_AS_SHOWN, REACHED_BY_PANE_SCROLL, REACHED_ABOVE_NOTIFICATIONS or
  NOT_REACHED (the check then fails), with what covered it at first — so that the record keeps "not covered
  from the start" apart from "reached after a scroll" (acceptance.py);
* page_scroll(): the page's own scroll size against the display area;
* pane_scroll(): the panes' sideways scrolling;
* layout(): which layout the edit page has (three panes or the folded
  navigation) and where its panes are.
"""

from __future__ import annotations

from typing import Callable, Optional

from tests.e2e.support import expect

# Fully inside: up to half a CSS px out (fractional boxes at a DPR of 1.25).
EDGE = 0.5

# How reach() got to a control (the record, plan 8.7 condition 4).
REACHED_AS_SHOWN = "表示のまま（スクロールなし・覆われない）"
REACHED_BY_PANE_SCROLL = "ペインのスクロールで到達"
REACHED_ABOVE_NOTIFICATIONS = "通知に覆われていたため、通知の上へスクロールして到達"
NOT_REACHED = "届かない（失敗）"

# Called with one dict per reach() (tests/e2e/conftest.py, display_check.py).
OBSERVERS: list[Callable[[dict], None]] = []

NOTIFICATIONS = """() => [...document.querySelectorAll('#ui-toasts .ui-toast')].map((toast) => {
  const r = toast.getBoundingClientRect();
  return { kind: toast.dataset.toastType, text: (toast.dataset.message || '').slice(0, 40),
           box: [r.x, r.y, r.width, r.height].map((v) => Math.round(v)) };
})"""

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
  const stack = document.getElementById('ui-toasts');
  if (!stack || !stack.querySelector('.ui-toast')) return false;
  const top = stack.getBoundingClientRect().top;  // the stack may scroll inside (low display areas)
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
    scroll=True: by scrolling the pane it is in (Playwright scrolls the
    nearest scrolling ancestors) and, if only the notifications cover it
    then, above them. scroll=False: as it is, with no scrolling at all (the
    main buttons). Never a sideways scroll of the page."""
    expect(locator).to_be_visible(timeout=timeout)
    label = name or describe(locator)
    first = locator.evaluate(HIT)  # as shown, before any scroll
    found, how, covered, notifications = first, REACHED_AS_SHOWN, [], []
    if not (_inside(first) and not first["misses"]):
        how = REACHED_BY_PANE_SCROLL
    if scroll and how != REACHED_AS_SHOWN:
        locator.scroll_into_view_if_needed(timeout=timeout)
        found = locator.evaluate(HIT)
        if found["misses"] and all(miss["over"] and "ui-toast" in miss["over"] for miss in found["misses"]):
            covered, notifications = found["misses"], locator.page.evaluate(NOTIFICATIONS)
            if locator.evaluate(ABOVE_NOTIFICATIONS):
                found = locator.evaluate(HIT)
                how = REACHED_ABOVE_NOTIFICATIONS
    if found["scrollX"] != 0 or not _inside(found) or found["misses"]:
        how = NOT_REACHED
    for observer in OBSERVERS:
        observer({"name": label, "how": how, "no_scroll_required": not scroll, "client": found["client"],
                  "box": [round(v, 1) for v in found["box"]], "first_misses": first["misses"],
                  "covered_by_notifications": covered, "notifications": notifications})
    x, y, w, h = found["box"]
    width, height = found["client"]
    rule = "（追加のスクロールなしで届く必要がある主要なボタン）" if not scroll else ""
    assert found["scrollX"] == 0, f"{label}：ページを横にスクロールしないと届かない（scrollX {found['scrollX']}）"
    assert _inside(found), (
        f"{label}：表示領域 {width}×{height} の外にはみ出す（{x:.1f}, {y:.1f}, {w:.1f}×{h:.1f}）{rule}")
    assert not found["misses"], f"{label}：ほかの要素に覆われている {found['misses']}{rule}"
    return found


def _inside(found: dict) -> bool:
    x, y, w, h = found["box"]
    width, height = found["client"]
    return x >= -EDGE and y >= -EDGE and x + w <= width + EDGE and y + h <= height + EDGE


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

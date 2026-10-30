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
  - scroll=True, a control in a pane that scrolls (a long list): reached
    by scrolling that pane as a user would. A notification over it is a
    failure here too: since PR-7 the notifications have a room of their
    own and never cover a control (plan 8.7 condition 4; until then this
    check scrolled the pane above them, which hid the fault).
  Each call tells the observers (OBSERVERS) how the control was reached —
  REACHED_AS_SHOWN, REACHED_BY_PANE_SCROLL or NOT_REACHED (the check then
  fails), with what covered it (a notification among them) — so that the
  record keeps "not covered from the start" apart from "reached after a
  scroll" (acceptance.py);
* focus_shown(): the control that has the focus, as it is after the key
  and the app's own handling (nothing is scrolled by the check): fully in
  the display area and in every area it scrolls in, its focus outline too,
  and on top (a notification or the 保存・取消 bar over it fails; plan 8.7
  conditions 3 and 4, PR-7's fix of 2026-10-29);
* tab_walk(): presses Tab (or Shift+Tab) and checks focus_shown() after
  each press, with the notifications that must still be shown; tab_until():
  the same until a condition holds, at most as many presses as the page has
  controls that Tab stops at (tabbable_count()), so a target that is in the
  Tab order is reached from wherever the walk starts;
* page_scroll(): the page's own scroll size against the display area;
* pane_scroll(): the panes' sideways scrolling;
* layout(): which layout the edit page has (three panes or the folded
  navigation) and where its panes are.

The display area of these checks is the one the page is laid out in
(AREA), in fractional CSS px, not the root's clientWidth x clientHeight:
those are whole numbers, rounded down or up (Edge on Windows' display scale
125 % with a zoom of 125 %: 1222.4x585.6 as 1222x585; Chromium at a display
scale of 1.25 on about:blank: 1905.6x945.6 as 1906x946). A pane that ends at
the edge of that display area (585.59) was taken for one 0.59px past 585,
more than the half px allowed (PR-7, the Windows check of b35504f). Both
are recorded.
"""

from __future__ import annotations

from typing import Callable, Optional

from tests.e2e.support import expect

# Fully inside: up to half a CSS px out (fractional boxes at a DPR of 1.25).
EDGE = 0.5
# Chromium places boxes in units of 1/64 CSS px (LayoutUnit): a pane that
# ends at the edge of the display area ends there to within one.
LAYOUT_UNIT = 1 / 64

# The display area the page is laid out in, [width, height] in CSS px: the
# visual viewport while it is not pinch-zoomed (the layout viewport less a
# scrollbar, as clientWidth x clientHeight, but not rounded); otherwise the
# root's client size. See the module.
AREA = """(() => { const vv = window.visualViewport, root = document.documentElement;
  return vv && vv.scale === 1 ? [vv.width, vv.height] : [root.clientWidth, root.clientHeight]; })()"""

# How reach() got to a control (the record, plan 8.7 condition 4).
REACHED_AS_SHOWN = "表示のまま（スクロールなし・覆われない）"
REACHED_BY_PANE_SCROLL = "ペインのスクロールで到達"
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
  const [w, h] = """ + AREA + """;
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
  return { box: [r.x, r.y, r.width, r.height], area: [w, h], misses,
           client: [document.documentElement.clientWidth, document.documentElement.clientHeight],
           scrollX: window.scrollX, scrollY: window.scrollY };
}"""

# The page's own scroll: the root's, and since PR-7's fix of 2026-10-29 the
# main area's (it scrolls, not the page; support.PAGE_WIDTH).
PAGE_SCROLL = """() => {
  const root = document.documentElement, main = document.getElementById('main');
  const inMain = main ? main.scrollWidth + (main.offsetWidth - main.clientWidth) : 0;
  return { scroll: [Math.max(root.scrollWidth, inMain), root.scrollHeight], client: [root.clientWidth, root.clientHeight],
           at: [Math.max(window.scrollX, main ? main.scrollLeft : 0), window.scrollY] };
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
           folded: window.matchMedia('(width < 1280px)').matches, area: """ + AREA + """,
           client: [document.documentElement.clientWidth, document.documentElement.clientHeight] };
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
    found, how = first, REACHED_AS_SHOWN
    if not (_inside(first) and not first["misses"]):
        how = REACHED_BY_PANE_SCROLL
    if scroll and how != REACHED_AS_SHOWN:
        locator.scroll_into_view_if_needed(timeout=timeout)
        found = locator.evaluate(HIT)
    covered = [miss for miss in found["misses"] if miss["over"] and "ui-toast" in miss["over"]]
    notifications = locator.page.evaluate(NOTIFICATIONS) if covered else []
    if found["scrollX"] != 0 or not _inside(found) or found["misses"]:
        how = NOT_REACHED
    for observer in OBSERVERS:
        observer({"name": label, "how": how, "no_scroll_required": not scroll, "client": found["client"],
                  "area": [round(v, 2) for v in found["area"]],
                  "box": [round(v, 1) for v in found["box"]], "first_misses": first["misses"],
                  "covered_by_notifications": covered, "notifications": notifications})
    x, y, w, h = found["box"]
    width, height = found["area"]
    rule = "（追加のスクロールなしで届く必要がある主要なボタン）" if not scroll else ""
    assert found["scrollX"] == 0, f"{label}：ページを横にスクロールしないと届かない（scrollX {found['scrollX']}）"
    assert _inside(found), (
        f"{label}：表示領域 {width:g}×{height:g} の外にはみ出す（{x:.1f}, {y:.1f}, {w:.1f}×{h:.1f}）{rule}")
    assert not covered, f"{label}：通知に覆われている {covered}{rule}"
    assert not found["misses"], f"{label}：ほかの要素に覆われている {found['misses']}{rule}"
    return found


def _inside(found: dict) -> bool:
    x, y, w, h = found["box"]
    width, height = found["area"]
    return x >= -EDGE and y >= -EDGE and x + w <= width + EDGE and y + h <= height + EDGE


# The focused element: its box, its focus outline (how far outline-width
# and -offset reach outside the box: what the user sees), the areas it scrolls in (and the display
# area), the part of it that is visible in all of them, and the elements
# drawn at five points of that part. Read only: nothing is scrolled.
FOCUS = """() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  const r = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  // How far the outline reaches outside the box (an inset one: 0).
  const ring = style.outlineStyle !== 'none' ? Math.max(0, (parseFloat(style.outlineWidth) || 0) + (parseFloat(style.outlineOffset) || 0)) : 0;
  const [w, h] = """ + AREA + """;
  const clips = [{ name: '表示領域', rect: [0, 0, w, h] }];
  // An element placed with position: absolute (fixed) is clipped only by the
  // areas from its containing block up (the 保存・取消 bar: by the
  // inspector pane, not by its scroll area).
  const containingBlock = (node) => {
    const position = getComputedStyle(node).position;
    if (position === 'fixed') return document.documentElement;
    if (position !== 'absolute') return null;
    for (let up = node.parentElement; up; up = up.parentElement) {
      if (getComputedStyle(up).position !== 'static') return up;
    }
    return document.documentElement;
  };
  let skipTo = containingBlock(el);
  for (let box = el.parentElement; box && box !== document.documentElement; box = box.parentElement) {
    const s = getComputedStyle(box);
    if (skipTo && box !== skipTo) continue;
    skipTo = null;
    const next = containingBlock(box);
    if (next) skipTo = next;
    if (/(auto|scroll|hidden|clip)/.test(s.overflowX + s.overflowY)) {
      const b = box.getBoundingClientRect();
      const left = b.left + box.clientLeft, top = b.top + box.clientTop;
      clips.push({ name: box.id || box.dataset.scroll || (typeof box.className === 'string' ? box.className : '') || box.tagName.toLowerCase(),
                   rect: [left, top, left + box.clientWidth, top + box.clientHeight] });
    }
  }
  const vis = [r.left, r.top, r.right, r.bottom];
  for (const c of clips) {
    vis[0] = Math.max(vis[0], c.rect[0]); vis[1] = Math.max(vis[1], c.rect[1]);
    vis[2] = Math.min(vis[2], c.rect[2]); vis[3] = Math.min(vis[3], c.rect[3]);
  }
  const misses = [];
  if (vis[2] > vis[0] && vis[3] > vis[1]) {
    const points = [[0.5, 0.5], [0.15, 0.2], [0.85, 0.2], [0.15, 0.8], [0.85, 0.8]];
    for (const [fx, fy] of points) {
      const x = vis[0] + (vis[2] - vis[0]) * fx, y = vis[1] + (vis[3] - vis[1]) * fy;
      const hit = document.elementFromPoint(x, y);
      if (!(hit && (hit === el || el.contains(hit)))) {
        misses.push({ x: Math.round(x), y: Math.round(y),
                      over: hit ? (hit.id ? '#' + hit.id : hit.tagName.toLowerCase() + (typeof hit.className === 'string' && hit.className.trim() ? '.' + hit.className.trim().split(/\\s+/).join('.') : '')) : null });
      }
    }
  }
  const label = el.id || el.getAttribute('data-action') || el.getAttribute('aria-label') || (el.textContent || el.value || '').trim().slice(0, 30) || el.tagName.toLowerCase();
  return { label, tag: el.tagName.toLowerCase(), box: [r.x, r.y, r.width, r.height], ring, area: [w, h], clips, visible: vis, misses,
           inToasts: Boolean(el.closest('#ui-toasts')), inDialog: Boolean(el.closest('dialog')),
           region: el.closest('#ui-toasts') ? 'toasts' : el.closest('#edit-inspector') ? 'inspector'
             : el.closest('#edit-work-area') ? 'work' : el.closest('#edit-nav') ? 'nav' : 'other',
           toasts: document.querySelectorAll('#ui-toasts .ui-toast').length };
}"""


def focus_shown(page, what: str = "") -> Optional[dict]:
    """The focused control is shown as it is (see the module); its record,
    or None when nothing has the focus. Never scrolls anything.

    A control that fits in the areas it scrolls in must be wholly visible
    with its focus outline. A larger one (a tab panel, a long text area)
    must show at least half of the area that is smaller than it. Either
    way the points of its visible part are on top (not under a
    notification or the 保存・取消 bar)."""
    found = page.evaluate(FOCUS)
    if found is None:
        return None
    x, y, w, h = found["box"]
    ring = found["ring"]
    label = f"{what}：{found['label']}" if what else found["label"]
    assert w > 0 and h > 0, f"{label}：フォーカスのある要素に大きさがない"
    outer = (x - ring, y - ring, x + w + ring, y + h + ring)
    vl, vt, vr, vb = found["visible"]
    for axis in (0, 1):
        start, end = (outer[0], outer[2]) if axis == 0 else (outer[1], outer[3])
        spans = [(clip["name"], *((clip["rect"][0], clip["rect"][2]) if axis == 0 else (clip["rect"][1], clip["rect"][3])))
                 for clip in found["clips"]]
        smallest = min(high - low for _, low, high in spans)
        if end - start <= smallest + EDGE:
            for name, low, high in spans:
                assert start >= low - EDGE and end <= high + EDGE, (
                    f"{label}：フォーカスの表示が {name} の見えている範囲の外"
                    f"（{'横' if axis == 0 else '縦'}：要素 {start:.1f}〜{end:.1f}、範囲 {low:.1f}〜{high:.1f}）")
        else:
            shown = (vr - vl) if axis == 0 else (vb - vt)
            assert shown >= smallest / 2, (
                f"{label}：見えている範囲より大きな要素の、見えている部分が半分未満"
                f"（{'横' if axis == 0 else '縦'} {shown:.1f}px、範囲 {smallest:.1f}px）")
    covered = [miss for miss in found["misses"] if miss["over"] and "ui-toast" in miss["over"]]
    assert not covered, f"{label}：フォーカスのある要素が通知に覆われている {covered}"
    assert not found["misses"], f"{label}：フォーカスのある要素がほかの要素に覆われている {found['misses']}"
    return found


def tab_walk(page, presses: int, *, key: str = "Tab", toasts: int = 0, what: str = "") -> list[dict]:
    """Press `key` `presses` times; after each press (the browser's and the
    app's handling done) the focused control is shown (focus_shown) and at
    least `toasts` notifications are still there, so the check never passes
    on a screen whose notifications have gone. The records of each press."""
    seen = []
    for press in range(1, presses + 1):
        page.keyboard.press(key)
        found = focus_shown(page, f"{what}{key} {press} 回目")
        if found is None:
            continue
        assert found["toasts"] >= toasts, (
            f"{what}{key} {press} 回目：通知が {found['toasts']} 件（{toasts} 件以上を表示したまま確かめる）")
        seen.append(found)
    return seen


# The controls Tab stops at (shown, enabled, tabindex >= 0): an upper bound
# of the presses that go once round the page.
TABBABLE = """() => [...document.querySelectorAll('a[href], button, input, select, textarea, [tabindex]')]
  .filter((el) => !el.disabled && el.tabIndex >= 0 && el.offsetParent !== null
    && getComputedStyle(el).visibility !== 'hidden').length"""


def tabbable_count(page) -> int:
    return page.evaluate(TABBABLE)


def tab_until(page, until, *, key: str = "Tab", toasts: int = 0, what: str = "", target: str = "") -> list[dict]:
    """Press `key` (focus_shown and the notifications checked after each
    press, as tab_walk()) until `until(record)` holds for the focused
    control; at most once round the page (tabbable_count() + 2 presses), so
    the walk does not depend on where the browser's sequential focus
    navigation starts. The records of each press."""
    limit = tabbable_count(page) + 2
    seen = []
    for press in range(1, limit + 1):
        seen += tab_walk(page, 1, key=key, toasts=toasts, what=f"{what}{press} 回目の")
        if seen and until(seen[-1]):
            return seen
    raise AssertionError(f"{what}{key} を {limit} 回（ページの Tab で止まる操作の数 + 2）押しても{target or '目的の操作'}に届かない："
                         f"最後のフォーカス {seen[-1]['label'] if seen else 'なし'}")


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

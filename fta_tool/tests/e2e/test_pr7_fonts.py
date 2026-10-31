"""E2E: PR-7 fonts — E-F01 (plan 5.8, 8.7, 8.9).

The screens name the device's own fonts only (tokens.css --font-sans:
"BIZ UDPGothic", "Yu Gothic UI", "Meiryo", "Hiragino Sans", …, sans-serif;
no web font, J-28). Whether BIZ UDPGothic is on the user's PCs is not known
(plan 12), so each screen is shown with --font-sans replaced by lists
without it, as a PC without it would show them:

* windows-fallback  "Yu Gothic UI", "Meiryo", sans-serif — on Windows the
                    fonts a PC without BIZ UDPGothic uses; elsewhere the
                    generic sans-serif;
* sans-serif        the browser's generic sans-serif;
* serif             the generic serif (other widths and heights).

At 1280x800 and 1093x500, for the list, the new-analysis form and the edit
screen (with the manual-add dialog): headings and buttons are not cut off
(their text fits their box; only the work steps' names and states are cut
with an ellipsis on purpose), the controls of each bar do not overlap, and
the main controls are reached (tests/e2e/layout_checks.py). The font the
browser actually drew with (CDP CSS.getPlatformFontsForNode) is recorded:
it tells which font the check ran with on that PC. How the fonts look on the
user's PCs (BIZ UDPGothic present or not) is checked by eye
(manual-check-pr7.md, from the screens this test keeps with --e2e-screens).
"""

from __future__ import annotations

import re

import pytest

from tests.e2e import acceptance
from tests.e2e.edit_helpers import expect_editor_ready, inspector, open_edit
from tests.e2e.layout_checks import no_overlap, reach
from tests.e2e.support import expect, measure_viewport, save_screenshot
from tests.e2e.test_pr7_viewports import build, main_controls

pytestmark = pytest.mark.e2e

SUBSTITUTES = {
    "windows-fallback": '"Yu Gothic UI", "Meiryo", sans-serif',
    "sans-serif": "sans-serif",
    "serif": "serif",
}
SIZES = [case for case in acceptance.BASE_CASES if case.label == "1280x800"] + [
    case for case in acceptance.PR7_CASES if case.label == "1093x500"]

# Text that must fit its box (whatever the overflow style), and what is cut
# with an ellipsis on purpose.
FIT = "h1, h2, h3, .ui-btn, .ui-tabs__tab, .edit-step__number, .ui-field__label, .ui-toast__close"
ELLIPSIS = ".edit-step__name, .edit-step__status"
BARS = {
    "ヘッダー": (".edit-header__title > *, .edit-header__actions > *", ""),
    "作業ステップ": (".edit-steps__list > li", ""),
    "表示タブと絞り込み": (".ui-tabs__tab, .edit-filter > :not(.visually-hidden)", ".edit-center__bar"),
    "インスペクタの保存・取消": (".edit-editor__buttons > *", ""),
    "ダイアログのボタン": (".ui-dialog__actions > *", "dialog[open]"),
    "一覧の見出し": (".list-page__header > *", ""),
    "一覧の操作": (".list-table__actions > *, .list-table__actions .ui-menu > *", "tr"),
    "新規作成のボタン": (".new-page__actions > *", ""),
}

CUT_OFF = """([fit, ellipsis]) => {
  const cut = [];
  for (const el of document.querySelectorAll(fit)) {
    if (el.offsetParent === null || el.closest(ellipsis) || el.closest('.visually-hidden')) continue;
    if (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) {
      cut.push(`${el.tagName.toLowerCase()}「${el.textContent.trim().slice(0, 30)}」 `
        + `${el.scrollWidth}×${el.scrollHeight} > ${el.clientWidth}×${el.clientHeight}`);
    }
  }
  for (const el of document.querySelectorAll(ellipsis)) {  // cut on purpose: never empty
    if (el.offsetParent !== null && el.getBoundingClientRect().width < 24) cut.push(`省略の幅が足りない「${el.textContent}」`);
  }
  return cut;
}"""


def rendered_fonts(page, selector: str) -> str:
    """The fonts the browser drew the element's text with (CDP), e.g.
    "Yu Gothic UI（12 字）"; '-' when they cannot be read."""
    try:
        session = page.context.new_cdp_session(page)
        session.send("DOM.enable")
        session.send("CSS.enable")
        root = session.send("DOM.getDocument")["root"]["nodeId"]
        node = session.send("DOM.querySelector", {"nodeId": root, "selector": selector})["nodeId"]
        fonts = session.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]
        session.detach()
    except Exception as error:  # noqa: BLE001 - only recorded
        return f"-（{type(error).__name__}）"
    return "、".join(f"{font['familyName']}（{font['glyphCount']} 字）" for font in fonts) or "-"


def check_screen(page, name: str) -> None:
    cut = page.evaluate(CUT_OFF, [FIT, ELLIPSIS])
    assert not cut, f"{name}：文字が欠ける {cut}"
    for bar, (selector, scope) in BARS.items():
        no_overlap(page, selector, scope)


@pytest.mark.acceptance("E-F01")
@pytest.mark.parametrize("viewport", [pytest.param(case, id=case.label) for case in SIZES], indirect=True)
@pytest.mark.parametrize("substitute", list(SUBSTITUTES))
def test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps(page, e2e_server, display_case, substitute,
                                                                    request):
    family = SUBSTITUTES[substitute]
    style = f":root {{ --font-sans: {family} !important; }}"
    page.add_init_script(f"""document.addEventListener('DOMContentLoaded', () => {{
      const s = document.createElement('style'); s.textContent = {style!r}; document.head.append(s); }});""")
    analysis_id, a, b, c, d = build(e2e_server, "代替フォントでの表示：見出しとボタンが欠けないこと")
    folder = acceptance.screens_dir(request.config)

    def keep(name):
        if folder is not None:
            slug = re.sub(r"[^\w.-]+", "-", request.node.name)[:90]
            acceptance.add_screenshot(request.node, name, save_screenshot(page, folder / f"{slug}--{name}.png"))

    page.goto("/")
    expect(page.locator("h1")).to_have_text("FTA分析一覧")
    unquoted = lambda text: text.replace('"', "").replace("'", "")  # noqa: E731 - the browser drops some quotes
    assert unquoted(page.evaluate("getComputedStyle(document.body).fontFamily")) == unquoted(family)
    used = {"一覧の見出し": rendered_fonts(page, "h1"), "ボタン": rendered_fonts(page, ".ui-btn")}
    check_screen(page, "一覧")
    keep("一覧")

    page.goto("/analyses/new")
    expect(page.locator("h1")).to_have_text("新規FTA分析を作成")
    check_screen(page, "新規作成")
    keep("新規作成")

    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    used["編集画面の要因名"] = rendered_fonts(page, "[data-inspector-title]")
    check_screen(page, "編集画面")
    for label, control in main_controls(page, b).items():
        reach(control, name=f"{label}（{substitute}）")
    keep("編集画面")
    inspector(page).get_by_role("button", name="手動追加").click()
    dialog = page.get_by_role("dialog", name="要因を手動追加")
    expect(dialog).to_be_visible()
    check_screen(page, "手動追加のダイアログ")
    for label in ("追加する", "キャンセル"):
        reach(dialog.get_by_role("button", name=label), name=f"手動追加：{label}（{substitute}）", scroll=False)
    keep("手動追加のダイアログ")
    page.keyboard.press("Escape")

    acceptance.record_display(request.node, requested=display_case.size, dpr=display_case.dpr,
                              origin=display_case.origin, measured=measure_viewport(page),
                              layout="構造ナビの折りたたみ" if display_case.width < 1280 else "3ペイン",
                              note=f"--font-sans: {family}。描画に使われたフォント：" + "／".join(
                                  f"{where} {fonts}" for where, fonts in used.items()))


@pytest.mark.acceptance("E-F01")
@pytest.mark.parametrize("viewport", [pytest.param(SIZES[0], id=SIZES[0].label)], indirect=True)
@pytest.mark.parametrize("fault, css", [
    ("button-cut-off", ".edit-header__actions .ui-btn { width: 24px; overflow: hidden; white-space: nowrap; }"),
    ("buttons-overlap", ".edit-header__actions > * + * { margin-left: -40px; }"),
])
def test_the_font_checks_catch_cut_off_and_overlapping_text(page, e2e_server, display_case, fault, css):
    analysis_id, a, b, c, d = build(e2e_server, "検出力")
    open_edit(page, analysis_id, f"#sel={b}&step=3&view=work")
    expect_editor_ready(page, b)
    check_screen(page, "そのまま")
    page.add_style_tag(content=css)
    with pytest.raises(AssertionError):
        check_screen(page, "不具合")

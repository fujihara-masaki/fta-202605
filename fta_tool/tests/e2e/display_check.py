"""PR-7: the real browser zoom and Windows display scale, and Microsoft IME
(plan 5.7, 5.9.4, 8.7; the steps for the user are in
docs/manual-check-pr7.md).

    python -m tests.e2e.display_check --out <new folder> --channel chrome|msedge
        [--zooms 100,125,150] [--ime] [--os-scale 125]

What the E2E tests cannot do is the browser's own zoom and the Windows
display scale (the tests give the browser a size and a devicePixelRatio,
never a zoom level) and a real IME. This tool lets the user do only that
and does the rest:

* starts the app as the E2E tests do (the stub AI provider, a test database
  in <out>/work, never the user's database, a free port; no real LLM) with
  test data;
* opens the installed Chrome or Edge (--channel) in a window of its own,
  maximized, with a temporary profile (never the user's profile, its zoom
  levels or its cache) and **without** a viewport given by Playwright, so
  the window, the display scale and the zoom are the real ones;
* records the OS, the browser and its version, the screen, and what the
  page measures (document.documentElement.clientWidth × clientHeight,
  innerWidth × innerHeight, devicePixelRatio), and the fonts the browser
  drew with (CDP: whether BIZ UDPGothic is on this PC);
* for each zoom level (--zooms): asks the user to set it with Ctrl and +
  (or Ctrl and -) in that window, sees it arrive in devicePixelRatio
  (display scale × zoom), then runs on the live page the checks of E-V01〜
  E-V03 (tests/e2e/test_pr7_viewports.py: the layout of the width, every
  main control visible and not covered, 保存・取消 while a field is in use,
  the folded navigation, the status line and log of a generation, a failed
  save, the dialogs, the list and the new-analysis form) and keeps the
  screens in <out>/screens for the visual review;
* --ime: the user types Japanese with the IME in five fields (the list's
  rename, the new-analysis title, the edit screen's title, the manual add,
  the filter) and confirms the conversion with Enter; the tool sees the
  composition in the page and judges that the Enter that confirmed it sent
  nothing, and that the Enter after it saved (the filter: nothing is sent);
* writes result.md and result.json (and display-output.log) and removes
  the test database (<out>/work; if it cannot, the run is 未完了 and the
  reason is in result.md).

The Windows display scale is never changed here (nor any setting, policy or
profile of the user): it is the one of the PC when the tool runs; its value
in Windows' settings can be given with --os-scale for the record, and it is
estimated from devicePixelRatio at zoom 100 %. Run the tool again after
changing it in Windows' settings to check another one.

--simulate-zoom (development only): instead of waiting for the user, the
page is shown again with the size and devicePixelRatio of the zoom level.
The record says so; it is never a check of a real zoom.

Exit code: 0 every check OK at every zoom level checked (and the IME
checks, with --ime); 1 a check NG; 2 not completed (a zoom level was not
set in time, the browser did not start, interrupted, the test database's
folder could not be removed: the reason is in result.md).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import platform
import subprocess
import sys
import time
import traceback
from typing import Callable, Optional

from tests.e2e.acceptance import DisplayCase
from tests.e2e.layout_checks import NOT_REACHED, OBSERVERS, REACHED_AS_SHOWN, REACHED_BY_PANE_SCROLL, reach
from tests.e2e.support import FTA_TOOL_DIR, free_port, remove_folder, save_screenshot, start_server

# Below these the plan has no assumed size (plan 5.9.4: 1024px wide and
# 500px high are its assumption; the tests go down to 900x600): a zoom level
# whose display area is smaller is checked, but only for reference, and is
# shown to the user for a decision (影響と対応方法を示して判断を受ける).
PLAN_WIDTH, PLAN_HEIGHT = 1024, 500
TESTED_WIDTH = 900
# Chrome's and Edge's zoom levels from 100 %: one press of Ctrl and + each.
ZOOM_STEPS = (100, 110, 125, 150, 175, 200)
DPR_TOLERANCE = 0.02

MEASURE = """() => {
  const root = document.documentElement;
  return { client: [root.clientWidth, root.clientHeight], inner: [window.innerWidth, window.innerHeight],
           outer: [window.outerWidth, window.outerHeight], devicePixelRatio: window.devicePixelRatio,
           screen: [screen.width, screen.height, screen.availWidth, screen.availHeight] };
}"""

COMPOSITION = """
window.__ftaComposition = [];
for (const type of ['compositionstart', 'compositionend']) {
  document.addEventListener(type, (event) => {
    const el = event.target;
    window.__ftaComposition.push({ type, data: event.data || '', at: Date.now(),
      field: el && (el.id || el.getAttribute('name') || el.className || el.tagName) });
  }, true);
}
"""


class Incomplete(Exception):
    """The run cannot go on; the reason goes to result.md."""


def git_head() -> tuple[str, bool]:
    def run(*args):
        try:
            done = subprocess.run(["git", *args], cwd=FTA_TOOL_DIR, capture_output=True, text=True, timeout=10)
            return done.stdout.strip() if done.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    return run("rev-parse", "HEAD") or "取得できませんでした", bool(run("status", "--porcelain", "--untracked-files=no"))


def make_data(server) -> dict:
    """The tool's test data (the E2E server's API): an analysis with four
    factors and a second analysis for the list."""
    analysis_id = server.create_analysis("表示倍率の確認", top_event="ログインできない",
                                         system_context="Web 2台・DB 1台")
    a = server.add_level1(analysis_id, "一次要因A：ネットワーク機器の設定変更が反映されていない可能性がある", "説明A")
    b = server.add_child(a, "二次要因B", "説明B")
    # 「障害」 is in two of the four factors (D's title, C's description):
    # the word the IME check of the filter asks for.
    c = server.add_child(b, "三次要因C", "障害の記録が残っていない")
    d = server.add_level1(analysis_id, "一次要因D：認証サーバーの障害")
    server.update_node(a, user_judgement="yes")
    list_id = server.create_analysis("一覧の確認：長いタイトルが折り返されても操作が見えること", top_event="頂上事象")
    return {"analysis": analysis_id, "a": a, "b": b, "c": c, "d": d, "list": list_id}


class DisplayCheck:
    def __init__(self, args):
        self.args = args
        self.out: pathlib.Path = args.out
        self.work = self.out / "work"
        self.screens = self.out / "screens"
        self.output = self.out / "display-output.log"
        self.results: list[dict] = []
        self.levels: list[dict] = []
        self.environment: dict = {}
        self.reason = ""
        self.server = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.base_dpr: Optional[float] = None
        self.data: dict = {}
        self.cleanup_error = ""  # why the server could not be stopped or <out>/work removed (close)
        self.cleanup = ""  # how the server stopped and the work folder was removed (result.md)
        self.console_errors: list[str] = []
        # Every request of the page (method, path and the Playwright request,
        # for its response), in order. Playwright's sync API runs the
        # callback only while one of its calls runs: every wait here goes
        # through pump() (page.wait_for_timeout), never time.sleep().
        self.requests: list[dict] = []
        # How each control was reached (layout_checks.reach(): as shown, by
        # scrolling its pane, or above the notifications), per zoom level.
        self.reaches: list[dict] = []
        self.level_name = ""

    # ----- output ---------------------------------------------------------------
    def say(self, text: str = "") -> None:
        print(text, flush=True)
        try:
            with self.output.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError:
            pass

    def ask(self, text: str) -> str:
        """A question for the user (Enter to go on)."""
        self.say(text)
        if self.args.simulate_zoom or self.args.no_input:
            return ""
        try:
            return input("  > ").strip()
        except EOFError:
            return ""

    def record(self, level: str, item: str, ok: bool, detail: str = "", operated_by: str = "自動") -> None:
        self.results.append({"level": level, "item": item, "ok": bool(ok), "detail": detail,
                             "operated_by": operated_by})
        self.say(f"  [{'OK' if ok else 'NG'}] {level}：{item}{('：' + detail) if detail else ''}")

    # ----- the app and the browser --------------------------------------------------
    def start(self) -> None:
        self.work.mkdir(parents=True)
        self.server = start_server(self.work, free_port())
        self.data = make_data(self.server)
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        options = {"headless": False, "args": ["--start-maximized"]}
        if self.args.executable:
            options["executable_path"] = self.args.executable
        elif not self.args.bundled:
            options["channel"] = self.args.channel
        if self.args.simulate_zoom:
            options["headless"] = True
            options["args"] = []
        try:
            self.browser = self.playwright.chromium.launch(**options)
        except Exception as error:  # noqa: BLE001 - the reason goes to the record
            raise Incomplete(f"ブラウザを起動できませんでした（{self.args.channel}）：{str(error).splitlines()[0]}")
        self.new_context(None)

    def new_context(self, simulated: Optional[DisplayCase]) -> None:
        if self.context is not None:
            self.context.close()
        options = {"locale": "ja-JP", "timezone_id": "Asia/Tokyo", "base_url": self.server.url}
        if simulated is None:
            options["no_viewport"] = True  # the window's real size, display scale and zoom
        else:
            options["viewport"] = {"width": simulated.width, "height": simulated.height}
            options["device_scale_factor"] = simulated.dpr
        self.context = self.browser.new_context(**options)
        self.context.add_init_script(COMPOSITION)
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.page.on("console", lambda m: self.console_errors.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.console_errors.append(f"例外：{e}"))
        self.page.on("request", lambda r: self.requests.append(
            {"method": r.method, "path": "/" + r.url.split("/", 3)[3], "request": r}))

    def measure(self) -> dict:
        return self.page.evaluate(MEASURE)

    def describe_environment(self) -> None:
        from tests.e2e.conftest import DESCRIBE_BROWSER

        head, dirty = git_head()
        info = {"対象 SHA": f"{head}（{'追跡中のファイルに未コミットの変更あり' if dirty else '未コミットの変更なし'}）",
                "OS": platform.platform(), "Python": platform.python_version(),
                "ブラウザ（channel）": self.args.executable or ("Playwright 同梱の Chromium" if self.args.bundled else self.args.channel),
                "ブラウザの版（Playwright）": self.browser.version,
                "テスト用サーバー": f"{self.server.url}（一時 DB：{self.work}。AI: e2e-stub、実LLMなし）",
                "プロフィール": "一時プロフィール（Playwright が作る。普段のプロフィール・拡大の設定・キャッシュは使わない）"}
        page = self.context.new_page()
        try:
            page.goto("chrome://version", timeout=10000)
            version = page.evaluate(DESCRIBE_BROWSER)
            info["ブラウザ（chrome://version）"] = f"{version['company']} {' '.join(version['version'].split())}"
            info["ブラウザの実行ファイル"] = version["executable"]
        except Exception as error:  # noqa: BLE001 - informational only
            info["ブラウザ（chrome://version）"] = f"読めませんでした：{str(error).splitlines()[0]}"
        finally:
            page.close()
        if self.args.os_scale:
            info["Windows の表示倍率（利用者の入力）"] = f"{self.args.os_scale}%"
        if self.args.simulate_zoom:
            info["注意"] = "--simulate-zoom：拡大を寸法と devicePixelRatio で模したもの。実際の拡大の確認ではない（開発用）"
        self.environment = info

    def fonts(self) -> str:
        try:
            session = self.context.new_cdp_session(self.page)
            session.send("DOM.enable")
            session.send("CSS.enable")
            root = session.send("DOM.getDocument")["root"]["nodeId"]
            found = []
            for selector in ("h1", "[data-factor-save]"):
                node = session.send("DOM.querySelector", {"nodeId": root, "selector": selector})["nodeId"]
                for font in session.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]:
                    found.append(f"{selector}：{font['familyName']}（{font['glyphCount']} 字）")
            session.detach()
            return "、".join(found) or "-"
        except Exception as error:  # noqa: BLE001 - informational only
            return f"読めませんでした（{type(error).__name__}）"

    # ----- zoom levels ------------------------------------------------------------
    def set_zoom(self, zoom: int, current: int) -> Optional[dict]:
        """Wait until the window shows `zoom` (its devicePixelRatio); the
        measurement, or None when it was not set in time."""
        if self.args.simulate_zoom:
            base = self.args.simulate_base
            case = DisplayCase(f"simulated-{zoom}", round(base[0] * 100 / zoom), round(base[1] * 100 / zoom),
                               round(self.base_dpr * zoom / 100, 4))
            self.new_context(case)
            self.page.goto("/")
            return self.measure()
        if zoom != current:
            steps = ZOOM_STEPS.index(zoom) - ZOOM_STEPS.index(current) if zoom in ZOOM_STEPS and current in ZOOM_STEPS else None
            how = (f"Ctrl と + を {steps} 回" if steps and steps > 0 else f"Ctrl と - を {-steps} 回" if steps
                   else "Ctrl と + / - で")
            self.say("")
            self.say(f"■ ブラウザの拡大を {zoom}% にしてください：テスト用のウィンドウをクリックしてから、{how}押します"
                     f"（アドレスバーの虫眼鏡で {zoom}% を確認。100% に戻すのは Ctrl と 0）。")
            self.say("  ツールが拡大の変化を検出すると、自動で確認を始めます。確認中はウィンドウを操作しないでください。")
        target = round(self.base_dpr * zoom / 100, 4)
        deadline = time.monotonic() + self.args.zoom_timeout
        while time.monotonic() < deadline:
            measured = self.measure()
            if abs(measured["devicePixelRatio"] - target) <= DPR_TOLERANCE:
                self.pump(1.0)  # the layout settles
                return self.measure()
            self.pump(0.5)
        return None

    def run_level(self, zoom: int, measured: dict) -> None:
        level = f"拡大 {zoom}%"
        width, height = measured["client"]
        case = DisplayCase(f"zoom{zoom}", width, height, measured["devicePixelRatio"])
        below = width < PLAN_WIDTH or height < PLAN_HEIGHT
        reference = width < TESTED_WIDTH or height < PLAN_HEIGHT
        entry = {"zoom": zoom, "measured": measured, "layout": "3ペイン" if width >= 1280 else "構造ナビの折りたたみ",
                 "simulated": bool(self.args.simulate_zoom), "screens": [],
                 "below_plan": below, "reference": reference}
        self.levels.append(entry)
        self.say(f"  実測：{width}×{height}、devicePixelRatio {measured['devicePixelRatio']}（{entry['layout']}）")
        if below:
            self.say(f"  注意：計画の想定（幅 {PLAN_WIDTH}px・高さ {PLAN_HEIGHT}px）を下回ります。"
                     + ("結果は参考で、判定に含めません。" if reference else "") + "影響を利用者に示して判断を受けます（第5.9.4節）。")
        if reference:
            level += "（想定を下回る・参考）"
        self.level_name = level
        for name, check in self.checks():
            errors_before = len(self.console_errors)
            try:
                detail = check(case, level, entry) or ""
                new_errors = self.console_errors[errors_before:]
                if new_errors:
                    raise AssertionError(f"コンソールのエラー：{new_errors[:3]}")
                self.record(level, name, True, detail)
            except Exception as error:  # noqa: BLE001 - recorded as NG, the next check goes on
                text = str(error).strip().splitlines()
                self.record(level, name, False, (text[0] if text else type(error).__name__)[:300])
                self.keep(entry, f"{name}-NG")

    def keep(self, entry: dict, name: str) -> None:
        file = self.screens / f"zoom{entry['zoom']}--{name}.png"
        result = save_screenshot(self.page, file)
        entry["screens"].append({"name": name, **result})

    # ----- the checks on the live page (E-V01〜E-V03) ---------------------------------
    def checks(self) -> list[tuple[str, Callable]]:
        return [("一覧：主要な操作と削除のダイアログ", self.check_list),
                ("新規作成：主要な操作と確認のダイアログ", self.check_new),
                ("編集画面：レイアウト・主要な操作・入力の前と入力中の保存・取消", self.check_edit),
                ("編集画面：通知の表示中のキーボード操作とフォーカスの後の通知", self.check_focus),
                ("編集画面：構造ナビの開閉（1280px 未満）", self.check_drawer),
                ("編集画面：未保存確認・削除・手動追加のダイアログ", self.check_dialogs),
                ("編集画面：生成中の状態表示・生成ログ・通知・保存失敗", self.check_generation)]

    def open_edit(self) -> None:
        from tests.e2e.edit_helpers import expect_editor_ready, open_edit

        open_edit(self.page, self.data["analysis"], f"#sel={self.data['b']}&step=3&view=work")
        expect_editor_ready(self.page, self.data["b"])

    def check_list(self, case, level, entry):
        from tests.e2e.layout_checks import assert_no_page_hscroll

        page = self.page
        page.goto("/")
        if case.width >= 1024:
            assert_no_page_hscroll(page, "一覧")
        row = page.locator(f'tr[data-analysis-id="{self.data["list"]}"]')
        for control in (page.locator("main").get_by_role("link", name="＋ 新規分析を作成"), row.locator("[data-title-link]"),
                        row.locator('[data-action="rename"]'), row.locator("[data-ui-menu-button]"),
                        row.locator('[data-action="delete"]')):
            reach(control)
        self.keep(entry, "一覧")
        row.locator('[data-action="delete"]').click()
        dialog = page.get_by_role("dialog", name="分析を削除しますか？")
        for button in dialog.get_by_role("button").all():
            reach(button, name="一覧の削除ダイアログ", scroll=False)
        self.keep(entry, "一覧の削除ダイアログ")
        page.keyboard.press("Escape")

    def check_new(self, case, level, entry):
        from tests.e2e.layout_checks import assert_no_page_hscroll

        page = self.page
        page.goto("/analyses/new")
        if case.width >= 1024:
            assert_no_page_hscroll(page, "新規作成")
        for control in (page.locator("#title"), page.locator("#top_event"), page.locator("[data-submit]"),
                        page.locator("[data-cancel-link]")):
            reach(control)
        self.keep(entry, "新規作成")
        page.fill("#title", "入力あり")
        page.locator("[data-cancel-link]").click()
        dialog = page.get_by_role("dialog", name="作成していない入力があります")
        for label in ("入力を続ける", "破棄して移動"):
            reach(dialog.get_by_role("button", name=label), name=f"新規作成の確認：{label}", scroll=False)
        page.keyboard.press("Escape")
        page.fill("#title", "")

    def check_edit(self, case, level, entry):
        from tests.e2e.test_pr7_viewports import (editor_bar, editor_bar_as_shown, expect_layout, expect_scrolling,
                                                  main_controls)

        self.open_edit()
        expect_layout(self.page, case)
        expect_scrolling(self.page, case, level)
        editor_bar_as_shown(self.page, f"{level}・入力の前")
        for name, control in main_controls(self.page, self.data["b"]).items():
            reach(control, name=name)
        editor_bar(self.page, level)
        entry.setdefault("fonts", self.fonts())
        self.keep(entry, "編集画面")
        return f"描画に使われたフォント：{entry['fonts']}"

    def check_focus(self, case, level, entry):
        """The same as tests/e2e/test_pr7_focus.py (E-K01): Tab and Shift+Tab
        with notifications shown, the focus in view and on top after each
        key (nothing scrolled by the tool); a notification shown while
        typing in the inspector leaves the focus, the text and its
        selection; the notifications closed with the keys."""
        from tests.e2e.edit_helpers import factor_cancel, factor_field
        from tests.e2e.layout_checks import focus_shown
        from tests.e2e.test_pr7_focus import close_notifications_by_keyboard, notify, walk_with_notifications

        self.open_edit()
        page = self.page
        seen = walk_with_notifications(page, what=f"{level}・")
        field = factor_field(page, "prevention_idea")
        field.click()
        page.keyboard.type("通知の確認の入力")
        before = field.evaluate("(el) => [el.value, el.selectionStart, el.selectionEnd]")
        notify(page, "入力中に出た注意（確認）", "warning")
        focus_shown(page, f"{level}・入力中に通知が出た後")
        assert field.evaluate("(el) => document.activeElement === el"), "入力中に通知が出た後、フォーカスが入力欄にない"
        assert field.evaluate("(el) => [el.value, el.selectionStart, el.selectionEnd]") == before, "入力・選択が変わった"
        self.keep(entry, "通知の表示中のフォーカス")
        close_notifications_by_keyboard(page, f"{level}・")
        factor_cancel(page).click()
        return f"Tab・Shift+Tab {len(seen)} 回：フォーカスの表示は通知・保存・取消の帯に覆われず、見えている範囲の中"

    def check_drawer(self, case, level, entry):
        from tests.e2e.edit_helpers import select_button
        from tests.e2e.layout_checks import layout
        from tests.e2e.support import expect

        if case.width >= 1280:
            return "1280px 以上のため3ペイン（構造ナビは常に表示）"
        self.open_edit()
        page = self.page
        toggle = page.locator("[data-nav-toggle]")
        reach(toggle, name="構造を表示")
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        found = layout(page)
        assert found["nav"] and found["nav"][0] + found["nav"][2] <= found["inspector"][0] + 0.5, found
        for key in ("a", "b", "c", "d"):
            reach(select_button(page, "nav", self.data[key]))
        self.keep(entry, "構造ナビを開いた状態")
        page.keyboard.press("Escape")
        expect(toggle).to_be_focused()
        return ""

    def check_dialogs(self, case, level, entry):
        from tests.e2e.edit_helpers import factor_cancel, factor_field, inspector, leave_link, select_button
        from tests.e2e.support import expect

        self.open_edit()
        page = self.page

        def fits(dialog, buttons, name):
            expect(dialog).to_be_visible()
            box = dialog.bounding_box()
            assert box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= case.width + 0.5 \
                and box["y"] + box["height"] <= case.height + 0.5, (name, box)
            for label in buttons:
                reach(dialog.get_by_role("button", name=label, exact=True), name=f"{name}：{label}", scroll=False)
            self.keep(entry, name)

        factor_field(page, "memo").fill("切り替える前の下書き")
        select_button(page, "group", self.data["a"]).click()
        fits(page.get_by_role("dialog", name="保存していない変更があります"),
             ["保存して移動", "破棄して移動", "編集を続ける"], "未保存確認（要因の切替）")
        page.keyboard.press("Escape")
        leave_link(page).click()
        fits(page.get_by_role("dialog", name="保存していない変更があります"),
             ["保存して移動", "破棄して移動", "編集を続ける"], "未保存確認（画面の移動）")
        page.keyboard.press("Escape")
        factor_cancel(page).click()
        inspector(page).get_by_role("button", name="この要因を削除").click()
        fits(page.get_by_role("dialog", name="要因を削除しますか？"), ["削除する", "キャンセル"], "削除確認")
        page.keyboard.press("Escape")
        inspector(page).get_by_role("button", name="手動追加").click()
        fits(page.get_by_role("dialog", name="要因を手動追加"), ["追加する", "キャンセル"], "手動追加")
        page.keyboard.press("Escape")

    def check_generation(self, case, level, entry):
        from tests.e2e.edit_helpers import (factor_field, factor_message, factor_save, gen_log, gen_status,
                                            step_panel, toast, wait_phase)
        from tests.e2e.support import expect
        from tests.e2e.test_pr7_viewports import editor_bar

        self.open_edit()
        page = self.page
        self.server.set_stub_mode("delay", delay_seconds=2)
        generate = step_panel(page, 3).get_by_role("button", name="Yesの一次要因から二次要因を生成")
        generate.click()
        wait_phase(page, "running")
        reach(gen_status(page).locator("[data-gen-status-text]").first, name="生成中の状態表示")
        self.keep(entry, "生成中")
        wait_phase(page, "idle", timeout=30)
        reach(gen_log(page).locator("[data-gen-log-close]"), name="生成ログを閉じる")
        editor_bar(page, f"{level}・生成の結果の通知")
        self.keep(entry, "生成ログ")
        page.route(f"**/nodes/{self.data['b']}/update", lambda route: route.fulfill(status=500, body="error"))
        before = len(self.console_errors)
        factor_field(page, "memo").fill("保存に失敗するメモ")
        factor_save(page).click()
        error = toast(page, "要因を保存できませんでした", "error")
        expect(error).to_be_visible()
        reach(factor_message(page), name="保存失敗の表示")
        reach(error.locator(".ui-toast__close"), name="エラーの通知を閉じる")
        editor_bar(page, f"{level}・エラーの通知")
        self.keep(entry, "保存失敗の表示と通知")
        del self.console_errors[before:]  # the 500 forced here
        page.unroute(f"**/nodes/{self.data['b']}/update")
        self.server.set_stub_mode("create")

    # ----- Microsoft IME (C-08) ---------------------------------------------------
    # Five fields, each judged by judge_ime() from what the page reports (the
    # composition events) and what it sends (the requests), watched from the
    # moment the field is ready, before the user types:
    #   phase 1  from the field ready until the conversion was confirmed and
    #            the page had IME_SETTLE seconds more: no request of the save
    #            (whether it came before, with or after the compositionend the
    #            tool saw) — else NG "確定の Enter で送信";
    #   phase 2  after the tool asks for the next Enter: exactly one request
    #            of the save, its response a success (2xx, or 303 for the new
    #            analysis) and the saved value (read from the test database)
    #            the text the user confirmed — "送信" and "保存" are told apart
    #            in the record;
    #   the filter: no request at all while the user types and confirms, and
    #            the count and the work list's rows match the factors whose
    #            name or description contains the confirmed text
    #            (js/pages/edit/filter.js).
    # The tool's judgement is tested with composed events
    # (tests/e2e/test_display_check.py); that is not a check of the
    # Microsoft IME, which only the user's run on Windows is.
    IME_SETTLE = 3.0
    FILTER_WORD = "障害"

    def pump(self, seconds: float) -> None:
        """Let the page and Playwright's events run (never time.sleep)."""
        self.page.wait_for_timeout(int(seconds * 1000))

    def wait_for(self, check, timeout: float, step: float = 0.2):
        deadline = time.monotonic() + timeout
        while True:
            found = check()
            if found or time.monotonic() >= deadline:
                return found
            self.pump(step)

    def ime(self) -> None:
        level = "日本語入力"
        self.say("")
        self.say("■ 日本語入力の確認（5 か所）：ツールが入力欄を開いてフォーカスを置きます。")
        self.say("  IME をオンにして日本語を入力し、変換して Enter で**確定だけ**してください。そのまま手を止めると、")
        self.say("  ツールが「確定の Enter で保存・送信されていないこと」を確かめ、次の操作を案内します。")
        self.ask("  準備ができたら、このウィンドウで Enter を押してください。")
        for name, open_field, target in self.ime_steps():
            try:
                field = open_field()
                self.judge_ime(level, name, field, target)
            except Exception as error:  # noqa: BLE001 - recorded as NG
                text = str(error).strip().splitlines()
                self.record(level, name, False, (text[0] if text else type(error).__name__)[:300], "利用者（IME）＋自動")

    def ime_steps(self) -> list:
        data, server = self.data, self.server

        def title_of(analysis_id):
            return lambda: (server.analysis(analysis_id) or {}).get("title")

        def new_analysis_titles():
            return [row[0] for row in server.query("SELECT title FROM analyses ORDER BY id")]

        def children_of(parent):
            return lambda: [row[0] for row in server.query("SELECT title FROM nodes WHERE parent_id = ? ORDER BY id",
                                                           (parent,))]
        return [
            ("一覧の改名", self.ime_rename, {"method": "POST", "path": f"/analyses/{data['list']}/title",
                                          "ok": (200,), "saved": title_of(data["list"]), "kind": "value"}),
            ("新規作成のタイトル", self.ime_new, {"method": "POST", "path": "/analyses", "ok": (303,),
                                             "saved": new_analysis_titles, "kind": "one-of"}),
            ("編集画面の分析タイトル", self.ime_title, {"method": "POST", "path": f"/analyses/{data['analysis']}/title",
                                                "ok": (200,), "saved": title_of(data["analysis"]), "kind": "value"}),
            ("手動追加のタイトル", self.ime_add, {"method": "POST", "path": f"/nodes/{data['b']}/children",
                                             "ok": (200,), "saved": children_of(data["b"]), "kind": "one-of"}),
            ("絞り込み", self.ime_filter, {"kind": "filter"}),
        ]

    def ime_rename(self):
        self.page.goto("/")
        row = self.page.locator(f'tr[data-analysis-id="{self.data["list"]}"]')
        row.locator('[data-action="rename"]').click()
        field = row.locator("[data-rename-editor] input")
        field.fill("")
        return field

    def ime_new(self):
        self.page.goto("/analyses/new")
        field = self.page.locator("#title")
        field.focus()
        return field

    def ime_title(self):
        self.open_edit()
        self.page.locator("[data-title-edit]").click()
        field = self.page.locator("#analysisTitleInput")
        field.fill("")
        return field

    def ime_add(self):
        from tests.e2e.edit_helpers import inspector

        self.open_edit()
        inspector(self.page).get_by_role("button", name="手動追加").click()
        field = self.page.locator("#add-factor-title")
        field.focus()
        return field

    def ime_filter(self):
        self.open_edit()
        field = self.page.locator("#edit-filter-text")
        field.fill("")
        field.focus()
        return field

    def judge_ime(self, level, name, field, target) -> dict:
        """Judge one field (see above). Returns what was found (also in the record)."""
        page = self.page
        who = "利用者（IME）＋自動"
        found = {"field": name, "composition": None, "sent_on_confirm": [], "sent_after": [], "status": None,
                 "saved": None, "value": "", "filter": None}
        page.evaluate("() => { window.__ftaComposition = []; }")
        watch_from = len(self.requests)  # before the user types: nothing sent from here is missed
        page.bring_to_front()
        word = f"（例：「しょうがい」と入力して「{self.FILTER_WORD}」に変換）" if target["kind"] == "filter" else ""
        self.say(f"  【{name}】入力欄にフォーカスがあります。日本語を入力・変換し{word}、Enter で確定してから手を止めてください。")

        def ended():
            ends = [e for e in page.evaluate("() => window.__ftaComposition") if e["type"] == "compositionend" and e["data"]]
            return ends[-1] if ends else None

        end = self.wait_for(ended, self.args.ime_timeout)
        if end is None:
            self.record(level, name, False, "時間内に IME の変換（compositionend）を検出できませんでした", who)
            return found
        found["composition"] = end
        self.pump(self.IME_SETTLE)  # the Enter that confirmed it, and what it may have sent
        value = field.input_value() if field.count() else ""
        found["value"] = value
        phase1 = self.requests[watch_from:]

        if target["kind"] == "filter":
            return self.judge_filter(level, name, value, phase1, found, who)

        def is_target(entry):
            return entry["method"] == target["method"] and entry["path"] == target["path"]

        found["sent_on_confirm"] = [e["path"] for e in phase1 if is_target(e)]
        if found["sent_on_confirm"]:
            self.record(level, name, False, f"変換を確定した Enter で送信された（{target['method']} {target['path']}。"
                        "確定の前後を問わず、入力欄の準備の後から次の Enter の案内までに送られた要求）", who)
            return found
        self.say(f"    確定の Enter では送信されていません（入力欄の値「{value}」）。もう一度 Enter を押して保存してください。")
        after_from = len(self.requests)
        sent = self.wait_for(lambda: [e for e in self.requests[after_from:] if is_target(e)], self.args.ime_timeout)
        if not sent:
            self.record(level, name, False, f"確定の Enter では送信なし。次の Enter で送信なし（{self.args.ime_timeout:.0f} 秒で時間切れ）"
                        f"（値「{value}」）", who)
            return found
        self.pump(1.0)  # a second request of the same save, if any
        sent = [e for e in self.requests[after_from:] if is_target(e)]
        found["sent_after"] = [e["path"] for e in sent]
        response = sent[0]["request"].response()
        found["status"] = response.status if response else None
        expected = value.replace("\r\n", "\n").strip()  # stored as the server does (str.strip())
        saved = self.wait_for(lambda: self.saved_text(target, expected), 5.0)
        found["saved"] = saved
        problems = []
        if len(sent) != 1:
            problems.append(f"次の Enter で {len(sent)} 回送信")
        if found["status"] not in target["ok"]:
            problems.append(f"応答が {found['status']}（成功ではない）")
        if not saved:
            problems.append("保存された値が確定した文字と一致しない（テスト用 DB）")
        if not any(ord(ch) > 0x2fff for ch in value):
            problems.append("確定した文字に日本語がない（IME で入力していない可能性）")
        detail = (f"確定の Enter：送信なし／次の Enter：送信 {len(sent)} 回・応答 {found['status']}"
                  f"／保存：{'確定した文字「' + value + '」と一致' if saved else '一致しない'}")
        self.record(level, name, not problems, detail + ("。NG：" + "、".join(problems) if problems else ""), who)
        self.pump(1.5)
        return found

    def saved_text(self, target, expected: str) -> bool:
        current = target["saved"]()
        if target["kind"] == "value":
            return bool(expected) and current == expected
        return bool(expected) and expected in (current or [])

    def judge_filter(self, level, name, value, phase1, found, who) -> dict:
        """The filter sends nothing; its count and rows follow the text."""
        page = self.page
        sent = [f"{e['method']} {e['path']}" for e in phase1]
        text = value.strip().lower()
        nodes = self.server.query("SELECT id, title, description FROM nodes WHERE analysis_id = ?",
                                  (self.data["analysis"],))
        hits = {row[0] for row in nodes if text and text in f"{row[1] or ''} {row[2] or ''}".lower()}
        expected_count = f"一致 {len(hits)}件（全{len(nodes)}件）"
        count = page.locator("#edit-filter-count").inner_text()
        rows = page.evaluate("""() => [...document.querySelectorAll('[data-role="work-item"][data-node-id]')]
          .map((el) => [Number(el.dataset.nodeId), !el.hidden])""")
        wrong_rows = [node_id for node_id, shown in rows if shown != (node_id in hits)]
        found["filter"] = {"text": value, "hits": sorted(hits), "count": count, "expected": expected_count,
                           "requests": sent, "wrong_rows": wrong_rows}
        problems = []
        if sent:
            problems.append(f"入力・確定の間に要求が送られた：{sent}")
        if not hits:
            problems.append(f"確定した文字「{value}」に一致する要因がなく、絞り込みの反映を確かめられない"
                            f"（「{self.FILTER_WORD}」で確かめる）")
        if count != expected_count:
            problems.append(f"件数の表示「{count}」が期待「{expected_count}」と違う")
        if wrong_rows:
            problems.append(f"作業リストの表示が一致しない行：{wrong_rows}")
        detail = f"確定した文字「{value}」で{count}（期待 {expected_count}）。要求の送信：{len(sent)} 件"
        self.record(level, name, not problems, detail + ("。NG：" + "、".join(problems) if problems else ""), who)
        return found

    # ----- the whole run ----------------------------------------------------------
    def reached(self, entry: dict) -> None:
        self.reaches.append({"level": self.level_name, **entry})

    def run(self) -> None:
        OBSERVERS.append(self.reached)
        self.start()
        self.describe_environment()
        page = self.page
        page.goto("/")
        first = self.measure()
        self.environment["画面（screen）"] = f"{first['screen'][0]}×{first['screen'][1]}（作業領域 {first['screen'][2]}×{first['screen'][3]}）"
        self.environment["ウィンドウ（outer）"] = f"{first['outer'][0]}×{first['outer'][1]}"
        if not self.args.simulate_zoom:
            self.ask("■ テスト用のブラウザが開きました（最大化）。拡大が 100% であること（アドレスバーに虫眼鏡がないこと）を"
                     "確かめて、このウィンドウで Enter を押してください。")
            first = self.measure()
        self.base_dpr = first["devicePixelRatio"]
        self.environment["Windows の表示倍率（拡大100%の devicePixelRatio からの推定）"] = f"{round(self.base_dpr * 100)}%"
        if self.args.simulate_zoom:
            width, height = (int(v) for v in self.args.simulate_base.split("x"))
            self.args.simulate_base = (width, height)
        current = 100
        for zoom in self.args.zooms:
            measured = self.set_zoom(zoom, current)
            if measured is None:
                self.record(f"拡大 {zoom}%", "拡大の設定", False,
                            f"{self.args.zoom_timeout:.0f} 秒以内に拡大 {zoom}%（devicePixelRatio "
                            f"{round(self.base_dpr * zoom / 100, 3)}）を検出できませんでした", "利用者")
                self.reason = f"拡大 {zoom}% を確認できませんでした（未実施）"
                continue
            current = zoom
            self.say(f"■ 拡大 {zoom}% を確認しています（操作しないでください）…")
            self.run_level(zoom, measured)
        if self.args.ime:
            self.ime()

    def close(self) -> None:
        if self.reached in OBSERVERS:
            OBSERVERS.remove(self.reached)
        for thing in (self.context, self.browser):
            try:
                if thing is not None:
                    thing.close()
            except Exception:  # noqa: BLE001
                pass
        if self.playwright is not None:
            self.playwright.stop()
        if self.server is not None:
            try:  # the app's own process gone, the log's handle closed (tests/e2e/support.py)
                self.server.close()
            except Exception as error:  # noqa: BLE001 - the run is then not OK, with the reason
                self.cleanup_error = f"テスト用サーバーを止められませんでした：{error}"
                self.say(f"未完了：{self.cleanup_error}")
            self.cleanup = f"テスト用サーバー：{self.server.stopped or '不明'}"
        if not self.cleanup_error:
            self.remove_work()

    # The test database's folder is removed after the server stopped; on
    # Windows a file is released a moment after the process that held it
    # ended (and an indexer or antivirus may hold it briefly): a few tries.
    REMOVE_TRIES = 10
    REMOVE_WAIT = 0.5

    def remove_work(self) -> bool:
        """Remove <out>/work (the test database and the server's files;
        nothing else). A failure is never let through: its reason goes to
        the record and the run is not OK (未完了)."""
        work = self.work
        if not work.exists():
            return True
        if work.resolve().parent != self.out.resolve() or work.name != "work":
            self.cleanup_error = f"削除の対象が記録フォルダの work ではないため削除していません：{work}"
            return False
        # Playwright is stopped here: nothing to pump while waiting.
        removed, errors = remove_folder(work, self.REMOVE_TRIES, self.REMOVE_WAIT)
        if removed:
            self.cleanup = "；".join(filter(None, [
                self.cleanup, f"一時フォルダの削除：{len(errors) + 1} 回目で削除"
                + (f"（それまでの失敗：{errors[-1]}）" if errors else "")]))
            return True
        left = sorted(str(path.relative_to(work)) for path in work.rglob("*"))[:10] if work.exists() else []
        self.cleanup_error = (f"一時フォルダ {work} を削除できませんでした（{self.REMOVE_TRIES} 回試行）："
                              f"{errors[-1]}。残ったもの：{left or 'なし'}")
        self.say(f"未完了：{self.cleanup_error}")
        return False

    def write_result(self) -> int:
        # NG: a check failed; 未完了: nothing failed but a zoom level (or the
        # whole run) was not done; OK: every zoom level done and every check OK.
        # The test database not removed is not OK either (remove_work).
        failed = [r for r in self.results if not r["ok"] and r["item"] != "拡大の設定" and "参考" not in r["level"]]
        incomplete = bool(self.reason) or bool(self.cleanup_error) or len(self.levels) != len(self.args.zooms)
        code = 1 if failed else (2 if incomplete else 0)
        verdict = {0: "OK", 1: "NG", 2: "未完了"}[code]
        self.reason = "；".join(filter(None, [self.reason, self.cleanup_error]))
        payload = {"verdict": verdict, "exit_code": code, "reason": self.reason, "cleanup_error": self.cleanup_error,
                   "cleanup": self.cleanup,
                   "environment": self.environment,
                   "levels": self.levels, "results": self.results, "reaches": self.reaches,
                   "written": _dt.datetime.now().astimezone().isoformat(timespec="seconds")}
        (self.out / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# PR-7 表示倍率・ブラウザの拡大・日本語入力の確認（display_check）", "",
                 f"- 判定：**{verdict}**（終了コード {code}）" + (f"。理由：{self.reason}" if self.reason else ""),
                 f"- 記録した日時：{payload['written']}",
                 f"- 後片付け：{self.cleanup or 'なし'}",
                 "- 自動で判定した項目は、実際のブラウザのウィンドウ（Playwright は表示領域を指定しない）での DOM の位置・寸法・"
                 "最前面の要素によるものです。画面の読みやすさは screens の画像で目視してください（判定に含めません）。",
                 "", "## 実行環境", "", "| 項目 | 値 |", "|---|---|"]
        lines += [f"| {key} | {value} |" for key, value in self.environment.items()]
        lines += ["", "## 拡大ごとの実測", "", "| ブラウザの拡大 | clientWidth×clientHeight | innerWidth×innerHeight | devicePixelRatio | レイアウト | 計画の想定との関係 | 模擬 |",
                  "|---|---|---|---|---|---|---|"]
        for entry in self.levels:
            m = entry["measured"]
            relation = ("想定を下回る：参考（判定に含めない）。利用者の判断が必要" if entry["reference"]
                        else "想定を下回る：判定に含める。利用者の判断が必要" if entry["below_plan"] else "想定の範囲")
            lines.append(f"| {entry['zoom']}% | {m['client'][0]}×{m['client'][1]} | {m['inner'][0]}×{m['inner'][1]} "
                         f"| {m['devicePixelRatio']} | {entry['layout']} | {relation} "
                         f"| {'はい（実際の拡大ではない）' if entry['simulated'] else 'いいえ'} |")
        lines += ["", "## 確認の結果", "", "| 条件 | 項目 | 結果 | 操作 | 詳細 |", "|---|---|---|---|---|"]
        for r in self.results:
            detail = str(r["detail"]).replace("|", "／").replace("\n", " ")
            lines.append(f"| {r['level']} | {r['item']} | {'OK' if r['ok'] else 'NG'} | {r['operated_by']} | {detail} |")
        lines += self.reach_lines()
        lines += ["", "## 目視のレビュー用の画面（screens）", ""]
        for entry in self.levels:
            for shot in entry["screens"]:
                lines.append(f"- 拡大 {entry['zoom']}%：{shot['name']} → "
                             + (f"screens/{shot['file']}" if shot.get("file") else f"保存できなかった（{shot.get('reason')}）"))
        lines += ["", "## このツールが確認しないこと", "",
                  "- Windows の表示倍率の変更（このツールは変えない。設定を変えてから、もう一度実行する）",
                  "- スクリーンリーダー（NVDA など）の実際の読み上げ（manual-check-pr7.md の手動確認）",
                  "- 画面の読みやすさ・見た目（screens の画像の目視）",
                  "- 普段のプロフィール（拡張機能・既定の文字サイズ・保存された拡大）での表示", ""]
        (self.out / "result.md").write_text("\n".join(lines), encoding="utf-8")
        self.say(f"判定：{verdict}（{self.out / 'result.md'}）")
        return code


    def reach_lines(self) -> list[str]:
        """Not covered from the start, or reached only after a scroll (plan 8.7 condition 4)."""
        lines = ["", "## 主要な操作への到達", "",
                 "保存・取消（入力の前・入力中）とダイアログのボタンは、スクロールなしで表示領域の中にあり、通知にも覆われないことを"
                 "確かめます（そうでなければ NG）。ほかの操作は、ペイン（長い一覧など）をスクロールして届けば OK です。"
                 "**通知に覆われていた操作は、スクロールの有無にかかわらず NG です。**", "",
                 "| 条件 | 確かめた数 | 表示のまま（うちスクロールなしが要件） | ペインのスクロールで到達 | 届かない（NG） |",
                 "|---|---|---|---|---|"]
        levels = list(dict.fromkeys(e["level"] for e in self.reaches))
        for level in levels:
            entries = [e for e in self.reaches if e["level"] == level]
            shown = [e for e in entries if e["how"] == REACHED_AS_SHOWN]
            lines.append(f"| {level} | {len(entries)} | {len(shown)}（{sum(e['no_scroll_required'] for e in shown)}） "
                         f"| {sum(e['how'] == REACHED_BY_PANE_SCROLL for e in entries)} "
                         f"| {sum(e['how'] == NOT_REACHED for e in entries)} |")
        other = [e for e in self.reaches if e["how"] != REACHED_AS_SHOWN]
        if other:
            lines += ["", "| 条件 | 操作 | 届き方 | 表示領域 | 重なった通知 |", "|---|---|---|---|---|"]
            for e in other:
                toasts = "、".join(f"{t['kind']}「{t['text']}」" for t in e["notifications"]) or "-"
                lines.append(f"| {e['level']} | {e['name']} | {e['how']} | {e['client'][0]}×{e['client'][1]} | {toasts} |")
        return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=pathlib.Path, help="new record folder (outside the code)")
    parser.add_argument("--channel", default="chrome", choices=("chrome", "msedge"))
    parser.add_argument("--executable", default="", help="a Chromium executable instead of --channel (development)")
    parser.add_argument("--bundled", action="store_true", help="Playwright's own Chromium (development)")
    parser.add_argument("--zooms", default="100,125,150", help="browser zoom levels to check, in %%")
    parser.add_argument("--os-scale", default="", help="the Windows display scale in %% as Windows' settings show it")
    parser.add_argument("--ime", action="store_true", help="also the Microsoft IME checks")
    parser.add_argument("--zoom-timeout", type=float, default=180, help="seconds to wait for each zoom level")
    parser.add_argument("--ime-timeout", type=float, default=180, help="seconds to wait for each IME input")
    parser.add_argument("--simulate-zoom", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--simulate-base", default="1920x945", help=argparse.SUPPRESS)
    parser.add_argument("--no-input", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.out = args.out.resolve()
    try:
        args.zooms = [int(z) for z in args.zooms.split(",") if z.strip()]
    except ValueError:
        print(f"未完了：--zooms は 100,125,150 のように指定してください（{args.zooms}）")
        return 2
    if args.out == FTA_TOOL_DIR or FTA_TOOL_DIR in args.out.parents:
        print(f"未完了：記録フォルダはコードの外に指定してください：{args.out}")
        return 2
    if args.out.exists() and any(args.out.iterdir()):
        print(f"未完了：記録フォルダには新しい（空の）フォルダを指定してください：{args.out}")
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    check = DisplayCheck(args)
    try:
        check.run()
    except Incomplete as error:
        check.reason = str(error)
        check.say(f"未完了：{error}")
    except KeyboardInterrupt:
        check.reason = "中断されました（Ctrl+C）"
        check.say(check.reason)
    except Exception as error:  # noqa: BLE001 - recorded as the reason, with the traceback
        check.reason = f"{type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}"
        check.say(f"未完了：{check.reason}")
        (args.out / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        check.close()
    return check.write_result()


if __name__ == "__main__":
    sys.exit(main())

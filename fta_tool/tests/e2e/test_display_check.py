"""E2E: the tool of the Windows zoom and display-scale check (PR-7,
tests/e2e/display_check.py, manual-check-pr7.md) runs through, here with
its development mode (--simulate-zoom: the zoom levels are shown as their
size and devicePixelRatio, which the record says), so that the user's run on
Windows meets a tool that works. The real zoom, the display scale and the
IME are only checked on Windows by the user.

No acceptance ID: it checks the tool, not the screens.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import types
from typing import Optional

import pytest

from tests.e2e import acceptance, display_check, layout_checks
from tests.e2e.support import (FTA_TOOL_DIR, free_port, process_gone, python_env, read_server_pid, remove_folder,
                              start_server)

pytestmark = pytest.mark.e2e


def run_tool(tmp_path, pytestconfig, *args) -> tuple[int, dict, str]:
    out = tmp_path / "display-check"
    executable = acceptance.browser_executable(pytestconfig) or ""
    channel = pytestconfig.getoption("--browser-channel") or ""
    browser = ["--executable", executable] if executable else (["--channel", channel] if channel else ["--bundled"])
    # In a process of its own: this one may run pytest-playwright's Playwright.
    # Its output in UTF-8, as read here (python_env; the Windows run of 2026-10-30).
    env = python_env()
    done = subprocess.run([sys.executable, "-m", "tests.e2e.display_check", "--out", str(out), *browser,
                           "--simulate-zoom", "--no-input", *args], cwd=FTA_TOOL_DIR, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    code = done.returncode
    assert (out / "result.json").exists(), done.stdout[-2000:] + done.stderr[-2000:]
    return code, json.loads((out / "result.json").read_text(encoding="utf-8")), (out / "result.md").read_text(encoding="utf-8")


def test_the_display_check_tool_runs_its_checks_and_records_them(tmp_path, pytestconfig):
    code, result, text = run_tool(tmp_path, pytestconfig, "--zooms", "100,150", "--simulate-base", "1920x945")
    assert code == 0 and result["verdict"] == "OK", [r for r in result["results"] if not r["ok"]]
    assert [(lvl["zoom"], tuple(lvl["measured"]["client"]), lvl["measured"]["devicePixelRatio"]) for lvl in result["levels"]] \
        == [(100, (1920, 945), 1), (150, (1280, 630), 1.5)]
    assert len(result["results"]) == 14 and all(r["operated_by"] == "自動" for r in result["results"])
    # The same checks as the E2E tests of PR-7's fix: 保存・取消 before any
    # input, the focus with notifications shown (tests/e2e/test_pr7_focus.py).
    focus = [r for r in result["results"] if r["item"].startswith("編集画面：通知の表示中のキーボード操作")]
    assert len(focus) == 2 and all(r["ok"] for r in focus), focus
    assert "模した" in result["environment"]["注意"]  # never recorded as a real zoom
    assert "はい（実際の拡大ではない）" in text
    screens = [shot for lvl in result["levels"] for shot in lvl["screens"]]
    assert screens and all(shot.get("file") for shot in screens)
    assert not (tmp_path / "display-check" / "work").exists()  # the test database is removed
    # How each control was reached is recorded, the main buttons as shown.
    assert result["reaches"] and "## 主要な操作への到達" in text
    required = [e for e in result["reaches"] if e["no_scroll_required"]]
    assert required and all(e["how"] == layout_checks.REACHED_AS_SHOWN for e in required)


def test_a_display_area_below_the_plan_is_flagged_for_the_users_decision(tmp_path, pytestconfig):
    # 1366x650 at 150 % is 911x433: lower than the plan's 500px, shown for reference only.
    code, result, text = run_tool(tmp_path, pytestconfig, "--zooms", "150", "--simulate-base", "1366x650")
    level = result["levels"][0]
    assert tuple(level["measured"]["client"]) == (911, 433)
    assert level["below_plan"] and level["reference"]
    assert all("参考" in r["level"] for r in result["results"])
    assert code in (0, 2) and "想定を下回る：参考（判定に含めない）。利用者の判断が必要" in text


# ----- the test database's folder is removed (the Windows runs of 2026-10-30) --------
# On Windows the run above left display-check/work: this process kept its
# handle of server.log open (tests/e2e/support.py start_server), a file open
# without FILE_SHARE_DELETE cannot be removed there, and the removal ignored
# its error. The server now releases its folder when closed, and a folder
# that cannot be removed makes the run 未完了 with the reason.
# In the individual run on Edge (795cf36) work/fta_tool.db was still in use
# right after close(): a venv's python.exe on Windows is a launcher, and
# close() waited for the launcher, not for the app it runs (support.py
# E2EServer). close() now asks the app to end and waits for its own process.

def open_handles_in(folder) -> Optional[list[str]]:
    """The files under `folder` this process has open (Linux: /proc/self/fd).
    None where they cannot be listed (Windows): no proof either way."""
    fds = pathlib.Path("/proc/self/fd")
    if not fds.exists():
        return None
    found = []
    for fd in fds.iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if target.startswith(str(folder)):
            found.append(target)
    return found


def test_the_test_server_releases_its_folder_when_closed(tmp_path, record_property):
    work = tmp_path / "work"
    work.mkdir()
    server = start_server(work, free_port())
    try:
        assert server.http.get("/").status_code == 200
        assert server.query("SELECT COUNT(*) FROM analyses") == [(0,)]
    finally:
        server.close()
    # The app ended by itself (not stopped), and its own process is gone.
    assert server.stopped.startswith("自分で終了（終了コード 0）"), server.stopped
    assert process_gone(server.server_pid, 0), server.stopped
    handles = open_handles_in(work)
    if handles is not None:
        assert handles == [], handles
    # No ignore_errors; a file still in use after the tries fails the test.
    removed, errors = remove_folder(work, REMOVE_TRIES, REMOVE_WAIT)
    record_property(acceptance.NOTE_PROPERTY, f"停止：{server.stopped}／一時フォルダの削除：{len(errors) + 1} 回目"
                    + (f"（それまでの失敗：{errors[-1]}）" if removed and errors else ""))
    assert removed and not work.exists(), errors


# The same tries as the tool (display_check.py REMOVE_TRIES, REMOVE_WAIT).
REMOVE_TRIES = display_check.DisplayCheck.REMOVE_TRIES
REMOVE_WAIT = display_check.DisplayCheck.REMOVE_WAIT

# A stand-in for a venv's launcher on Windows (CPython PC/launcher.c,
# run_child): it runs the app as its child with its own standard handles,
# passed explicitly as launcher.c does (DuplicateHandle, STARTF_USESTDHANDLES):
# on Windows a child of subprocess.Popen inherits no handle unless passed
# (close_fds). Unlike launcher.c it ends first, as soon as its stdin is
# closed, while the app is still ending. "no-std-handles" starts the child
# as this stand-in did until 32730b8 (Popen without them): on Windows the
# app then had no stdout, uvicorn's logging failed, nothing could be written
# and the start waited 60 s for nothing (the Windows run of 2026-10-30).
LAUNCHER = """import os, pathlib, subprocess, sys
pathlib.Path("launcher.pid").write_text(str(os.getpid()))
mode, command = sys.argv[1], sys.argv[2:]
if mode == "no-std-handles" and os.name == "nt":
    subprocess.Popen(command)
elif mode == "no-std-handles":
    subprocess.Popen(command, preexec_fn=lambda: [os.close(fd) for fd in (0, 1, 2)])
else:
    subprocess.Popen(command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
sys.stdin.buffer.read()
"""


def launcher_command(tmp_path, mode: str) -> list[str]:
    launcher = tmp_path / "launcher.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    return [sys.executable, str(launcher), mode, sys.executable]


def launcher_pid(work) -> int:
    return int((work / "launcher.pid").read_text(encoding="utf-8"))


def test_close_waits_for_the_apps_own_process(tmp_path, record_property):
    work = tmp_path / "work"
    work.mkdir()
    server = start_server(work, free_port(), {"FTA_E2E_EXIT_DELAY": "2"}, python=launcher_command(tmp_path, "pass"))
    assert server.server_pid != server.process.pid
    try:
        assert server.query("SELECT COUNT(*) FROM analyses") == [(0,)]
    finally:
        server.close()
    record_property(acceptance.NOTE_PROPERTY, f"停止：{server.stopped}")
    # The stand-in ended about 2 s before the app (checked when it ended),
    # and close() waited for the app's own process.
    assert server.app_outlived_process is True, server.stopped
    assert process_gone(server.server_pid, 0) and process_gone(launcher_pid(work), 0), server.stopped
    assert "の終了を確認" in server.stopped, server.stopped
    removed, errors = remove_folder(work, REMOVE_TRIES, REMOVE_WAIT)
    assert removed, errors


def test_the_server_starts_again_in_the_same_folder(tmp_path):
    # As the W-02 tool does (cache_manual_check.py): what the first server
    # left (server.pid of a process now gone) is not taken for the second's.
    work = tmp_path / "work"
    work.mkdir()
    port = free_port()
    first = start_server(work, port)
    first.close()
    second = start_server(work, port)
    try:
        assert second.server_pid not in (None, first.server_pid)
        assert second.query("SELECT COUNT(*) FROM analyses") == [(0,)]
    finally:
        second.close()
    assert second.stopped.startswith("自分で終了（終了コード 0）"), second.stopped


def test_an_app_started_without_standard_handles_is_reported_at_once(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    started = time.monotonic()
    with pytest.raises(RuntimeError) as failure:
        start_server(work, free_port(), python=launcher_command(tmp_path, "no-std-handles"))
    message = str(failure.value)
    # Said at once (the app's process ended), with the app's own reason.
    assert time.monotonic() - started < 30, message
    assert "起動の途中で終了" in message and "標準の入出力がない" in message, message
    assert '"stage": "python"' in message and '"stage": "listening"' not in message, message
    assert "起動したプロセスとアプリのプロセスは終了した" in message, message
    assert process_gone(read_server_pid(work), 0) and process_gone(launcher_pid(work), 0), message


def test_a_server_that_does_not_answer_is_reported_then_stopped(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(RuntimeError) as failure:
        start_server(work, free_port(), {"FTA_E2E_START_DELAY": "60"}, python=launcher_command(tmp_path, "pass"),
                     start_seconds=5)
    message = str(failure.value)
    # What is known is gathered first (both processes still running, the
    # app imported but not listening, its port closed), then they are stopped.
    assert "5 秒たっても HTTP の応答がない" in message, message
    assert f"アプリのプロセス（PID {read_server_pid(work)}）：動作中" in message, message
    assert '"stage": "app imported"' in message and '"stage": "listening"' not in message, message
    assert "：開いていない" in message, message
    assert "起動したプロセスとアプリのプロセスは終了した" in message, message
    assert process_gone(read_server_pid(work), 0) and process_gone(launcher_pid(work), 0), message


# What a test reads of a Python process's output is its Japanese text, also
# on Windows (where a pipe is written in the locale's encoding unless
# PYTHONIOENCODING says otherwise: cp932 here stands for it). An undecodable
# output is an error of this test, not a warning (subprocess's reader thread).
@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_python_process_s_output_is_read_in_utf8(tmp_path):
    script = "import sys; print('未完了：表示倍率 150%'); print('エラー：削除できません', file=sys.stderr)"
    done = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=python_env({**os.environ, "PYTHONIOENCODING": "cp932"}),
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert (done.returncode, done.stdout, done.stderr) == (0, "未完了：表示倍率 150%\n", "エラー：削除できません\n")


def tool(tmp_path) -> "display_check.DisplayCheck":
    out = tmp_path / "display-check"
    out.mkdir()
    args = types.SimpleNamespace(out=out, zooms=[], simulate_zoom=True, no_input=True)
    check = display_check.DisplayCheck(args)
    check.work.mkdir()
    (check.work / "server.log").write_text("log", encoding="utf-8")
    check.REMOVE_WAIT = 0
    return check


def test_the_tool_removes_its_work_folder(tmp_path):
    check = tool(tmp_path)
    assert check.remove_work() and not check.work.exists()
    assert check.write_result() == 0


def test_a_work_folder_that_cannot_be_removed_is_not_ok(tmp_path, monkeypatch):
    check = tool(tmp_path)
    calls = []

    def held(path, *a, **kw):
        calls.append((path, a, kw))
        raise PermissionError(32, "The process cannot access the file because it is being used by another process",
                              str(path / "server.log"))

    monkeypatch.setattr(shutil, "rmtree", held)
    assert check.remove_work() is False
    assert len(calls) == check.REMOVE_TRIES and all(not kw.get("ignore_errors") for _, _, kw in calls)
    code = check.write_result()
    result = json.loads((check.out / "result.json").read_text(encoding="utf-8"))
    text = (check.out / "result.md").read_text(encoding="utf-8")
    assert code == 2 and result["verdict"] == "未完了"
    assert "削除できませんでした" in result["cleanup_error"] and "being used by another process" in result["cleanup_error"]
    assert "server.log" in result["cleanup_error"] and result["cleanup_error"] in text


def test_only_the_record_folders_work_is_removed(tmp_path, monkeypatch):
    check = tool(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    check.work = elsewhere
    monkeypatch.setattr(shutil, "rmtree", lambda *a, **kw: pytest.fail("removed a folder outside the record"))
    assert check.remove_work() is False and elsewhere.exists()
    assert "削除していません" in check.cleanup_error


# ----- the IME judgement (judge_ime), with composed events ------------------------
# What the user does on Windows (type with the IME, confirm with Enter, then
# the next Enter) is played here by a script in the page: composed
# compositionstart / input / compositionend events and keydown Enter
# (isComposing for the Enter that confirms). It tests how the tool judges
# what it sees; it is not a check of the Microsoft IME (manual-check-pr7.md 5.3).

TEXT = "障害の確認"

# When: 300 ms after judge_ime() starts, the "user" types and confirms; the
# next Enter comes NEXT_ENTER ms after the confirmation (after the tool asks).
USER = """({ text, misfire, second, nextEnter }) => {
  const el = document.activeElement;
  const key = (init) => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...init }));
  setTimeout(() => {
    el.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true, data: '' }));
    el.value = text;
    el.dispatchEvent(new InputEvent('input', { bubbles: true, isComposing: true, data: text, inputType: 'insertCompositionText' }));
    if (misfire === 'before') key({});               // a plain Enter before the composition ends
    el.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true, data: text }));
    key({ isComposing: misfire !== 'with' });        // 'with': the confirming Enter reaches the page as a plain one
    if (misfire === 'after') setTimeout(() => key({}), 600);  // after the tool has seen the compositionend
    if (second) setTimeout(() => key({}), nextEnter);
  }, 300);
}"""


# The judgement is the same at every size: one is enough.
ONE_SIZE = pytest.mark.parametrize("viewport", [(1280, 800)], indirect=True, ids=["1280x800"])


@pytest.fixture
def check(page, e2e_server, tmp_path):
    """A DisplayCheck on the test's page and server (no window of its own)."""
    page.add_init_script(display_check.COMPOSITION)
    args = types.SimpleNamespace(out=tmp_path, ime_timeout=4.0, simulate_zoom=False, no_input=True)
    tool = display_check.DisplayCheck(args)
    tool.output = tmp_path / "display-output.log"
    tool.IME_SETTLE = 1.0
    tool.server, tool.page = e2e_server, page
    tool.data = display_check.make_data(e2e_server)
    page.on("request", lambda r: tool.requests.append(
        {"method": r.method, "path": "/" + r.url.split("/", 3)[3], "request": r}))
    return tool


def play(check, field_name: str, *, text=TEXT, misfire=None, second=True, fault: str = ""):
    """Open the field as the tool does, add `fault` (a script on the opened
    page), play the user and judge."""
    steps = {name: (open_field, target) for name, open_field, target in check.ime_steps()}
    open_field, target = steps[field_name]
    field = open_field()
    if fault:
        check.page.evaluate(fault)
    check.page.evaluate(USER, {"text": text, "misfire": misfire, "second": second,
                               "nextEnter": int(check.IME_SETTLE * 1000) + 1200})
    found = check.judge_ime("日本語入力", field_name, field, target)
    return check.results[-1], found


@ONE_SIZE
@pytest.mark.parametrize("field_name", ["一覧の改名", "新規作成のタイトル", "編集画面の分析タイトル", "手動追加のタイトル"])
def test_judge_ime_confirm_sends_nothing_and_the_next_enter_saves(check, field_name):
    result, found = play(check, field_name)
    assert result["ok"], result
    assert found["sent_on_confirm"] == [] and len(found["sent_after"]) == 1
    assert found["status"] in (200, 303) and found["saved"] is True
    assert "確定の Enter：送信なし" in result["detail"] and "保存：確定した文字「障害の確認」と一致" in result["detail"]


@ONE_SIZE
@pytest.mark.parametrize("misfire", ["before", "with", "after"])
def test_judge_ime_a_save_on_the_confirming_enter_is_ng_whenever_it_comes(check, misfire):
    """Before the compositionend, with it, or after the tool saw it: every
    request of the save from the field ready to the tool's question counts."""
    result, found = play(check, "一覧の改名", misfire=misfire, second=False)
    assert not result["ok"] and "変換を確定した Enter で送信された" in result["detail"], result
    assert found["sent_on_confirm"]


@ONE_SIZE
def test_judge_ime_no_save_on_the_next_enter_is_ng(check):
    result, found = play(check, "編集画面の分析タイトル", second=False)
    assert not result["ok"] and "次の Enter で送信なし" in result["detail"], result
    assert found["sent_after"] == []


@ONE_SIZE
def test_judge_ime_sent_but_not_saved_is_ng(check, page_watch):
    page_watch.allow_console_error(r"status of 500")
    check.page.route(f"**/analyses/{check.data['list']}/title",
                     lambda route: route.fulfill(status=500, json={"detail": "E2E: 保存できない"}))
    result, found = play(check, "一覧の改名")
    assert not result["ok"], result
    assert len(found["sent_after"]) == 1 and found["status"] == 500 and found["saved"] is False
    assert "応答が 500" in result["detail"] and "保存された値が確定した文字と一致しない" in result["detail"]


@ONE_SIZE
def test_judge_ime_the_filter_follows_the_confirmed_text(check):
    result, found = play(check, "絞り込み", text="障害", second=False)
    assert result["ok"], result
    assert found["filter"]["count"] == "一致 2件（全4件）" == found["filter"]["expected"]
    assert sorted(found["filter"]["hits"]) == sorted([check.data["c"], check.data["d"]])
    assert found["filter"]["requests"] == []


@ONE_SIZE
def test_judge_ime_a_filter_that_does_not_follow_is_ng(check):
    # The page's own compositionend listener is kept from running (the tool's
    # listener on the document, in the capture phase, still sees it).
    fault = """() => document.getElementById('edit-filter-text')
      .addEventListener('compositionend', (e) => e.stopImmediatePropagation(), true)"""
    result, found = play(check, "絞り込み", text="障害", second=False, fault=fault)
    assert not result["ok"] and "件数の表示" in result["detail"], result


@ONE_SIZE
def test_judge_ime_a_request_while_filtering_is_ng(check, page_watch):
    page_watch.allow_console_error(r"status of (404|405|500)")
    fault = """() => document.getElementById('edit-filter-text')
      .addEventListener('compositionend', () => { fetch('/analyses/0/title', { method: 'POST' }).catch(() => {}); })"""
    result, found = play(check, "絞り込み", text="障害", second=False, fault=fault)
    assert not result["ok"] and "要求が送られた" in result["detail"], result

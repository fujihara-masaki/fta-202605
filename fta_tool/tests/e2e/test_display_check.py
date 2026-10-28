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
import subprocess
import sys

import pytest

from tests.e2e import acceptance
from tests.e2e.support import FTA_TOOL_DIR

pytestmark = pytest.mark.e2e


def run_tool(tmp_path, pytestconfig, *args) -> tuple[int, dict, str]:
    out = tmp_path / "display-check"
    executable = acceptance.browser_executable(pytestconfig) or ""
    channel = pytestconfig.getoption("--browser-channel") or ""
    browser = ["--executable", executable] if executable else (["--channel", channel] if channel else ["--bundled"])
    # In a process of its own: this one may run pytest-playwright's Playwright.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(FTA_TOOL_DIR), os.environ.get("PYTHONPATH")]))}
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
    assert len(result["results"]) == 12 and all(r["operated_by"] == "自動" for r in result["results"])
    assert "模した" in result["environment"]["注意"]  # never recorded as a real zoom
    assert "はい（実際の拡大ではない）" in text
    screens = [shot for lvl in result["levels"] for shot in lvl["screens"]]
    assert screens and all(shot.get("file") for shot in screens)
    assert not (tmp_path / "display-check" / "work").exists()  # the test database is removed


def test_a_display_area_below_the_plan_is_flagged_for_the_users_decision(tmp_path, pytestconfig):
    # 1366x650 at 150 % is 911x433: lower than the plan's 500px, shown for reference only.
    code, result, text = run_tool(tmp_path, pytestconfig, "--zooms", "150", "--simulate-base", "1366x650")
    level = result["levels"][0]
    assert tuple(level["measured"]["client"]) == (911, 433)
    assert level["below_plan"] and level["reference"]
    assert all("参考" in r["level"] for r in result["results"])
    assert code in (0, 2) and "想定を下回る：参考（判定に含めない）。利用者の判断が必要" in text

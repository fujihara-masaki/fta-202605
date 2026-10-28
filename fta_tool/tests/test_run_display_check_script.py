"""scripts/run_display_check.ps1 (PR-7, the real zoom and display scale):
Windows PowerShell 5.1 compatibility, as tests/test_run_cache_check_script.py
checks run_cache_check.ps1 (the UTF-8 BOM, CRLF, no operator Windows
PowerShell 5.1 does not have, no ParserError when pwsh / powershell is
available), what it runs, and that it changes no setting of the PC."""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

from tests.test_run_browser_e2e_script import UTF8_BOM, code_lines, find_powershell

PS1 = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "run_display_check.ps1"


def test_ps1_starts_with_utf8_bom_and_uses_crlf():
    data = PS1.read_bytes()
    assert data.startswith(UTF8_BOM)
    text = data[len(UTF8_BOM):].decode("utf-8")
    assert "param(" in text
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")


def test_ps1_avoids_powershell7_only_operators():
    code = code_lines(PS1.read_bytes().decode("utf-8-sig"))
    for pattern, label in ((r"\?\?", "??"), (r"\?\.", "?."), (r"&&", "&&"), (r"\|\|", "||"),
                           (r"\$IsWindows", "$IsWindows"), (r"\s\?\s[^:]*\s:\s", "三項演算子")):
        assert not re.search(pattern, code), f"Windows PowerShell 5.1 に無い {label} が使われています"


def test_ps1_runs_the_display_tool_with_the_checked_sha_and_changes_no_setting():
    code = code_lines(PS1.read_bytes().decode("utf-8-sig"))
    assert '$toolArgs = @("-m", "tests.e2e.display_check", "--out", $runDir, "--channel", $Browser, "--zooms", $Zooms)' in code
    assert "& $python @toolArgs" in code
    assert "rev-parse" in code and "--porcelain" in code and "ExpectedSha" in code and ".env" in code
    # Never the display scale, a policy or the registry of the PC.
    for forbidden in ("Set-ItemProperty", "New-ItemProperty", "HKCU:", "HKLM:", "reg add", "LogPixels", "Win8DpiScaling",
                      "Set-ExecutionPolicy"):
        assert forbidden not in code, forbidden


def test_ps1_parses_without_errors():
    exe = find_powershell()
    if not exe:
        pytest.skip("pwsh / powershell が見つからないため構文解析チェックをスキップ")
    script = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{PS1}', [ref]$tokens, [ref]$errors) | Out-Null; "
        "$errors | ForEach-Object { Write-Output $_.Message }; exit $errors.Count"
    )
    result = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"ParserError:\n{result.stdout}\n{result.stderr}"

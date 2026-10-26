"""scripts/run_cache_check.ps1 (PR-C, W-02): Windows PowerShell 5.1
compatibility, as tests/test_run_browser_e2e_script.py checks
run_browser_e2e.ps1: the UTF-8 BOM, CRLF, no operator Windows PowerShell 5.1
does not have, and no ParserError when pwsh / powershell is available."""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from tests.test_run_browser_e2e_script import UTF8_BOM, code_lines, find_powershell

PS1 = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "run_cache_check.ps1"


def test_ps1_starts_with_utf8_bom_and_uses_crlf():
    data = PS1.read_bytes()
    assert data.startswith(UTF8_BOM)
    text = data[len(UTF8_BOM):].decode("utf-8")
    assert "param(" in text
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")


def test_ps1_avoids_powershell7_only_operators():
    import re

    code = code_lines(PS1.read_bytes().decode("utf-8-sig"))
    for pattern, label in ((r"\?\?", "??"), (r"\?\.", "?."), (r"&&", "&&"), (r"\|\|", "||"),
                           (r"\$IsWindows", "$IsWindows"), (r"\s\?\s[^:]*\s:\s", "三項演算子")):
        assert not re.search(pattern, code), f"Windows PowerShell 5.1 に無い {label} が使われています"


def test_ps1_runs_the_w02_tool_with_the_checked_sha():
    code = code_lines(PS1.read_bytes().decode("utf-8-sig"))
    assert "-m tests.e2e.cache_manual_check --out $runDir --port $Port" in code
    assert "rev-parse" in code and "--porcelain" in code and "ExpectedSha" in code


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

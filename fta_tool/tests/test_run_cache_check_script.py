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


# ----- running the wrapper (pwsh with a stand-in python; POSIX only) ---------------
# The stand-in writes result.md (unless told not to) and exits with the code in
# the file "exit-code" next to it. On Windows, tests/e2e/test_windows_tools.py
# runs the wrapper with the real python in Windows PowerShell 5.1.

FAKE_TOOL = """#!/bin/sh
here="$(dirname "$0")"
printf '%s\\n' "$@" > "$here/args.txt"
out=""; previous=""
for argument in "$@"; do
  if [ "$previous" = "--out" ]; then out="$argument"; fi
  previous="$argument"
done
if [ ! -f "$here/no-result" ]; then
  mkdir -p "$out"
  printf '%s\\n' '# W-02' '- 判定：**NG**（終了コード 1）' > "$out/result.md"
fi
exit "$(cat "$here/exit-code")"
"""


@pytest.fixture
def run_wrapper():
    import shutil as _shutil

    exe = _shutil.which("pwsh")
    if not exe:
        pytest.skip("pwsh（PowerShell 7）が見つからないため、ラッパーの実行の確認はスキップ（Windows では tests/e2e/test_windows_tools.py）")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([exe, "-NoProfile", "-NonInteractive", "-File", str(PS1), *args],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    return run


@pytest.fixture
def fake_code(tmp_path):
    import shutil as _shutil
    import sys as _sys

    if _sys.platform == "win32" or not _shutil.which("git"):
        pytest.skip("the stand-in python is a POSIX shell script and needs git")
    repo = tmp_path / "コード"
    source = repo / "fta_tool"
    (source / "tests" / "e2e").mkdir(parents=True)
    (source / "tests" / "e2e" / "cache_manual_check.py").write_text("", encoding="utf-8")
    git = ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "code"], check=True)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.strip()
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(FAKE_TOOL, encoding="utf-8")
    python.chmod(0o755)
    return source, tmp_path / "venv", sha


def test_the_wrapper_stops_before_running_for_a_wrong_sha_or_no_venv(run_wrapper, fake_code, tmp_path):
    source, venv, sha = fake_code
    out = tmp_path / "records"
    (venv / "bin" / "exit-code").write_text("0")
    wrong = run_wrapper("-Venv", str(venv), "-OutRoot", str(out), "-ExpectedSha", "0000000", "-Source", str(source))
    assert wrong.returncode == 9 and "一致しません" in wrong.stdout
    missing = run_wrapper("-Venv", str(tmp_path / "none"), "-OutRoot", str(out), "-ExpectedSha", sha, "-Source", str(source))
    assert missing.returncode == 9 and "venv がありません" in missing.stdout
    inside = run_wrapper("-Venv", str(venv), "-OutRoot", str(source / "rec"), "-ExpectedSha", sha, "-Source", str(source))
    assert inside.returncode == 9 and "コードのフォルダの外" in inside.stdout
    assert not (venv / "bin" / "args.txt").exists()  # the tool never ran


@pytest.mark.parametrize("code", [0, 1, 2, 3])
def test_the_wrapper_passes_the_tools_exit_code_on(run_wrapper, fake_code, tmp_path, code):
    source, venv, sha = fake_code
    out = tmp_path / "records"
    (venv / "bin" / "exit-code").write_text(str(code))
    result = run_wrapper("-Venv", str(venv), "-OutRoot", str(out), "-ExpectedSha", sha[:7], "-Source", str(source),
                         "-Port", "8011", "-Browser", "msedge")
    assert result.returncode == code, result.stdout + result.stderr
    args = (venv / "bin" / "args.txt").read_text(encoding="utf-8").splitlines()
    assert args[:2] == ["-m", "tests.e2e.cache_manual_check"]
    assert args[args.index("--port") + 1] == "8011" and args[args.index("--browser") + 1] == "Microsoft Edge"
    runs = list(out.iterdir())
    assert len(runs) == 1 and runs[0].name.endswith("-msedge-w02")


def test_the_wrapper_records_an_incomplete_run_when_the_tool_wrote_nothing(run_wrapper, fake_code, tmp_path):
    source, venv, sha = fake_code
    out = tmp_path / "records"
    (venv / "bin" / "exit-code").write_text("0")
    (venv / "bin" / "no-result").write_text("")
    result = run_wrapper("-Venv", str(venv), "-OutRoot", str(out), "-ExpectedSha", sha, "-Source", str(source))
    assert result.returncode == 2
    text = (next(out.iterdir()) / "result.md").read_text(encoding="utf-8")
    assert "判定：**未完了**" in text and "結果を書きませんでした" in text and sha in text

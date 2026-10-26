"""scripts/run_cache_check.ps1 (W-02's wrapper) run by the PowerShell of the
machine: on Windows, Windows PowerShell 5.1 (powershell.exe) always, and
PowerShell 7 (pwsh) when it is installed; elsewhere pwsh when it is there.
Each host is a test of its own, so 5.1 and 7 are told apart in the record.

Part of the preflight on Windows (tests/e2e/acceptance.py PREFLIGHT_TESTS),
so the user runs nothing more for it. Where no PowerShell exists, no test is
defined (nothing is skipped and counted as checked).

Per host, with the real venv's python and nothing for the user to do:
* the file parses without errors;
* a wrong -ExpectedSha stops the wrapper before anything runs (exit 9, no
  record folder);
* with the tool's port taken, the wrapper starts the tool, which ends as
  "未完了" with the reason in result.md, and the wrapper passes its exit
  code 2 on.
The execution policy is the user's: it is not changed. If it refuses
scripts, the test fails and says so.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import socket
import subprocess
import sys

import pytest

from tests.e2e.support import FTA_TOOL_DIR

pytestmark = [pytest.mark.e2e]

PS1 = FTA_TOOL_DIR / "scripts" / "run_cache_check.ps1"


def powershell_hosts() -> list[tuple[str, str]]:
    hosts = []
    if sys.platform == "win32" and shutil.which("powershell"):
        hosts.append(("windows-powershell", shutil.which("powershell")))
    if shutil.which("pwsh"):
        hosts.append(("pwsh", shutil.which("pwsh")))
    return hosts


HOSTS = powershell_hosts()


def run_host(exe: str, *args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([exe, "-NoProfile", "-NonInteractive", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(FTA_TOOL_DIR.parent), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


if HOSTS:
    @pytest.mark.parametrize("host, exe", HOSTS, ids=[name for name, _ in HOSTS])
    def test_run_cache_check_ps1_with_the_installed_powershell(host, exe, tmp_path):
        info = run_host(exe, "-Command", "$PSVersionTable.PSVersion.ToString() + ' ' + $PSVersionTable.PSEdition")
        version = info.stdout.strip()
        (tmp_path / "powershell-check.json").write_text(json.dumps({"host": host, "exe": exe, "version": version},
                                                                   ensure_ascii=False), encoding="utf-8")
        print(f"PowerShell: {host} {version} ({exe})")
        if host == "windows-powershell":
            assert version.startswith("5.1") and version.endswith("Desktop"), version
        else:
            assert version.split(".")[0].isdigit() and int(version.split(".")[0]) >= 7, version

        parse = run_host(exe, "-Command",
                         "$tokens = $null; $errors = $null; "
                         f"[System.Management.Automation.Language.Parser]::ParseFile('{PS1}', [ref]$tokens, [ref]$errors) | Out-Null; "
                         "$errors | ForEach-Object { Write-Output $_.Message }; exit $errors.Count")
        assert parse.returncode == 0, f"{host} ParserError:\n{parse.stdout}\n{parse.stderr}"

        venv = pathlib.Path(sys.prefix)  # the venv the tests run in (its python, not resolved)
        out = tmp_path / "records"
        wrong = run_host(exe, "-File", str(PS1), "-Venv", str(venv), "-OutRoot", str(out), "-ExpectedSha", "0000000")
        assert wrong.returncode == 9, f"{host}: {wrong.stdout}\n{wrong.stderr}"
        assert "一致しません" in wrong.stdout or "未コミット" in wrong.stdout, wrong.stdout
        assert not out.exists() or not any(out.iterdir())

        head = git("rev-parse", "HEAD")
        clean = git("status", "--porcelain", "--untracked-files=no") == ""
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen(1)
            port = busy.getsockname()[1]
            started = run_host(exe, "-File", str(PS1), "-Venv", str(venv), "-OutRoot", str(out),
                               "-ExpectedSha", head, "-Port", str(port))
        if not clean:  # a developer's working tree: the wrapper refuses it before running
            assert started.returncode == 9 and "未コミット" in started.stdout, started.stdout
            return
        assert started.returncode == 2, f"{host}: {started.stdout}\n{started.stderr}"
        runs = list(out.iterdir())
        assert len(runs) == 1 and runs[0].name.startswith(head[:7]) and runs[0].name.endswith("-w02"), runs
        result = (runs[0] / "result.md").read_text(encoding="utf-8")
        assert "判定：**未完了**" in result and f"ポート {port} が使用中" in result, result
        assert (runs[0] / "w02-output.log").exists()

"""scripts/run_browser_e2e.ps1: Windows PowerShell 5.1 compatibility and the
checks it makes before anything is run (the check in Google Chrome of
2026-10-03; tests/e2e/README.md).

Like tests/test_run_langgraph_comparison_script.py:
  1. the file starts with the UTF-8 BOM (Windows PowerShell 5.1 reads a file
     without it as ANSI and fails on the Japanese text) and is UTF-8;
  2. no operator Windows PowerShell 5.1 does not have;
  3. no ParserError (when pwsh / powershell is available, otherwise skipped).
And, with pwsh (PowerShell 7) only, never with Windows PowerShell (whose
execution policy is the user's to decide), the script stops before running
anything with exit code 9 and a reason: no -BasePython for the setup, no
venv yet, no -OutRoot, no code at -Source, a venv inside the code's folder
or in a folder it did not make, changed code, another SHA, a code-side .env.
With a stand-in for the venv's python (a POSIX shell script) a run writes a
new record folder (run-info.md, the logs) and passes on pytest's exit code;
the record names the environment (development / the user's, -Environment)
with the actual OS, never "the user's Windows PC" for a run elsewhere, and
says that leftover processes were not checked outside Windows (never "none").
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

FTA_TOOL_DIR = pathlib.Path(__file__).resolve().parents[1]
PS1 = FTA_TOOL_DIR / "scripts" / "run_browser_e2e.ps1"
UTF8_BOM = b"\xef\xbb\xbf"
ABORT = 9


def code_lines(text: str) -> str:
    lines, in_comment = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("<#"):
            in_comment = True
        if not in_comment and not stripped.startswith("#"):
            lines.append(line)
        if stripped.endswith("#>"):
            in_comment = False
    return "\n".join(lines)


def test_ps1_starts_with_utf8_bom_and_is_utf8():
    data = PS1.read_bytes()
    assert data.startswith(UTF8_BOM), "run_browser_e2e.ps1 は UTF-8 BOM 付きで保存してください（Windows PowerShell 5.1）"
    assert "param(" in data[len(UTF8_BOM):].decode("utf-8")


def test_ps1_avoids_powershell7_only_operators():
    code = code_lines(PS1.read_bytes().decode("utf-8-sig"))
    for pattern, label in ((r"\?\?", "??"), (r"\?\.", "?."), (r"&&", "&&"), (r"\|\|", "||"),
                           (r"\$IsWindows", "$IsWindows"), (r"\s\?\s[^:]*\s:\s", "三項演算子")):
        assert not re.search(pattern, code), f"Windows PowerShell 5.1 に無い {label} が使われています"


def find_powershell(names=("pwsh", "powershell")):
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


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


@pytest.fixture
def run_script():
    exe = find_powershell(("pwsh",))
    if not exe:
        pytest.skip("pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([exe, "-NoProfile", "-NonInteractive", "-File", str(PS1), *args],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    return run


def fake_venv(folder: pathlib.Path) -> pathlib.Path:
    python = folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("")
    return folder


def test_setup_needs_the_base_python(run_script, tmp_path):
    result = run_script("-Mode", "Setup", "-Venv", str(tmp_path / "venv"))
    assert result.returncode == ABORT, result.stdout + result.stderr
    assert "-BasePython" in result.stdout
    assert not (tmp_path / "venv").exists()


def test_setup_refuses_a_venv_in_the_code_or_a_folder_it_did_not_make(run_script, tmp_path):
    inside = FTA_TOOL_DIR / "e2e-venv-should-not-exist"
    result = run_script("-Mode", "Setup", "-Venv", str(inside), "-BasePython", sys.executable, "-DryRun")
    assert result.returncode == ABORT and "コードのフォルダ" in result.stdout, result.stdout + result.stderr
    assert not inside.exists()
    existing = tmp_path / "something"
    existing.mkdir()
    (existing / "keep.txt").write_text("前からあるファイル", encoding="utf-8")
    result = run_script("-Mode", "Setup", "-Venv", str(existing), "-BasePython", sys.executable, "-DryRun")
    assert result.returncode == ABORT and "既にあるフォルダ" in result.stdout, result.stdout + result.stderr
    assert [p.name for p in existing.iterdir()] == ["keep.txt"]


def test_a_run_needs_the_venv_and_the_record_folder(run_script, tmp_path):
    result = run_script("-Mode", "Preflight", "-Venv", str(tmp_path / "missing"), "-OutRoot", str(tmp_path / "out"))
    assert result.returncode == ABORT and "-Mode Setup" in result.stdout, result.stdout + result.stderr
    venv = fake_venv(tmp_path / "venv")
    result = run_script("-Mode", "Full", "-Venv", str(venv))
    assert result.returncode == ABORT and "-OutRoot" in result.stdout, result.stdout + result.stderr
    result = run_script("-Mode", "Full", "-Venv", str(venv), "-OutRoot", str(FTA_TOOL_DIR / "runs"))
    assert result.returncode == ABORT and "コードのフォルダの外" in result.stdout, result.stdout + result.stderr
    assert not (tmp_path / "out").exists() and not (FTA_TOOL_DIR / "runs").exists()


def test_a_run_needs_the_code(run_script, tmp_path):
    result = run_script("-Mode", "Preflight", "-Venv", str(fake_venv(tmp_path / "venv")),
                        "-OutRoot", str(tmp_path / "out"), "-Source", str(tmp_path / "nowhere"))
    assert result.returncode == ABORT and "テストのコードが見つかりません" in result.stdout, result.stdout + result.stderr


FAKE_PYTHON = r"""#!/bin/sh
# Stands in for the venv's python: the package versions, then "pytest",
# which writes a record like tests/e2e/acceptance.py and fails.
case "$1" in
  -c) echo "Python 3.11 / playwright 1.56.0 / pytest-playwright 0.7.1 / pytest 8.2.0"; exit 0 ;;
esac
report=""; label=""; previous=""
for argument in "$@"; do
  if [ "$previous" = "--e2e-report" ]; then report="$argument"; fi
  if [ "$previous" = "--e2e-env" ]; then label="$argument"; fi
  previous="$argument"
done
printf '%s\n' "| 実行環境の区分 | $label |" \
  '| 判定 | 失敗（準備確認。全必須 E2E の合格ではありません） |' \
  '| 結果（テスト単位） | 成功 6・失敗 1・スキップ 0・未実施 0 |' \
  '| 既知の例外（favicon の 404） | 1 件（コンソールの確認から除いたもの） |' \
  '| 起動したブラウザ | Microsoft Corporation 154.0.0.0 |' > "$report"
echo "tests/e2e/test_x.py::test_x[1280x800] FAILED [100%]"
exit 1
"""


@pytest.fixture
def short_dir():
    """A short folder for the records: the script refuses a record folder
    over 150 characters (MAX_PATH on Windows), and tmp_path can be long."""
    path = pathlib.Path(tempfile.mkdtemp(prefix="e2e-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def code_and_venv(tmp_path):
    """A committed copy of what the script looks at, and a venv whose python is FAKE_PYTHON."""
    if sys.platform == "win32" or not shutil.which("git"):
        pytest.skip("the stand-in python is a POSIX shell script and needs git")
    repo = tmp_path / "コード 置き場"
    source = repo / "fta_tool"
    (source / "tests" / "e2e").mkdir(parents=True)
    (source / "tests" / "e2e" / "conftest.py").write_text("", encoding="utf-8")
    (source / "requirements-dev.txt").write_text("", encoding="utf-8")
    git = ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "code"], check=True)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    venv = fake_venv(tmp_path / "venv")
    python = venv / "bin" / "python"
    python.write_text(FAKE_PYTHON, encoding="utf-8")
    python.chmod(0o755)
    return source, venv, sha


def test_a_run_writes_a_new_record_folder_and_passes_on_the_exit_code(run_script, code_and_venv, short_dir):
    source, venv, sha = code_and_venv
    out = short_dir / "記録 置き場"
    result = run_script("-Mode", "Preflight", "-Venv", str(venv), "-OutRoot", str(out), "-Source", str(source),
                        "-Channel", "msedge", "-ExpectedSha", sha[:7])
    assert result.returncode == 1, result.stdout + result.stderr  # pytest's exit code
    runs = list(out.iterdir())
    assert len(runs) == 1 and runs[0].name.startswith(sha[:7]) and runs[0].name.endswith("-msedge-preflight")
    info = (runs[0] / "run-info.md").read_text(encoding="utf-8")
    assert f"| 対象 SHA | {sha}（未コミットの変更なし） |" in info
    assert "| 終了コード（pytest） | 1 |" in info
    assert "| 判定（e2e-report.md） | 失敗（準備確認。全必須 E2E の合格ではありません） |" in info
    assert "| 既知の例外（favicon の 404） | 1 件（e2e-report.md の「既知の例外として除いたコンソールのエラー」） |" in info
    # Not Windows: the leftover processes are not checked, and the record says so (never "none").
    assert "| 残っていたプロセス | 未確認（Windows 以外では、このスクリプトはプロセスを確認しません） |" in info
    # Where it ran: the development environment with the actual OS, never "the user's Windows PC".
    label = re.search(r"^\| 実行環境の区分 \| (.+) \|$", (runs[0] / "e2e-report.md").read_text(encoding="utf-8"), re.M).group(1)
    assert label.startswith("開発環境（") and label.endswith("、Microsoft Edge、headed）") and "Windows" not in label
    assert f"| 実行環境の区分 | {label}（-Environment 未指定のため OS から判断） |" in info
    assert "FAILED" in (runs[0] / "pytest-output.log").read_text(encoding="utf-8")
    assert "判定             : 失敗" in result.stdout and "Microsoft Corporation 154.0.0.0" in result.stdout

    again = run_script("-Mode", "Full", "-Venv", str(venv), "-OutRoot", str(out), "-Source", str(source), "-Channel", "msedge")
    assert again.returncode == 1
    assert len(list(out.iterdir())) == 2  # a new folder; the first one is untouched
    assert (runs[0] / "run-info.md").read_text(encoding="utf-8") == info


def test_a_run_stops_for_changed_code_another_sha_or_a_code_side_env(run_script, code_and_venv, tmp_path):
    source, venv, sha = code_and_venv
    out = tmp_path / "out"
    args = ("-Mode", "Full", "-Venv", str(venv), "-OutRoot", str(out), "-Source", str(source))
    result = run_script(*args, "-ExpectedSha", "0000000")
    assert result.returncode == ABORT and "一致しません" in result.stdout
    (source / ".env").write_text("AI_PROVIDER=ollama\n", encoding="utf-8")  # untracked: not a change of the code
    result = run_script(*args)
    assert result.returncode == ABORT and ".env" in result.stdout
    (source / ".env").unlink()
    (source / "requirements-dev.txt").write_text("changed\n", encoding="utf-8")
    result = run_script(*args)
    assert result.returncode == ABORT and "未コミットの変更" in result.stdout
    assert not out.exists()


def test_the_environment_is_recorded_as_given(run_script, code_and_venv, short_dir):
    source, venv, sha = code_and_venv
    out = short_dir / "out"
    args = ("-Mode", "Preflight", "-Venv", str(venv), "-OutRoot", str(out), "-Source", str(source), "-Channel", "msedge")
    result = run_script(*args, "-Environment", "Windows")
    assert result.returncode == ABORT and "-Environment" in result.stdout and not out.exists()
    result = run_script(*args, "-Environment", "User")
    assert result.returncode == 1, result.stdout + result.stderr
    info = (next(out.iterdir()) / "run-info.md").read_text(encoding="utf-8")
    assert re.search(r"^\| 実行環境の区分 \| 利用者環境（.+、Microsoft Edge、headed）（-Environment User） \|$", info, re.M), info

"""run_langgraph_comparison.ps1 の Windows PowerShell 5.1 互換性ガード。

Windows PowerShell 5.1 は BOM の無い UTF-8 スクリプトを ANSI（システム
ロケールのコードページ）として読むため、日本語コメントを含む ps1 は
UTF-8 BOM 付きでなければスクリプト解析段階で ParserError になる。
ここでは実行はせず、エンコーディングと構文の回帰だけを検査する:

  1. ファイルが UTF-8 BOM で始まること（必須）
  2. BOM 以降が正しい UTF-8 としてデコードできること
  3. PowerShell 5.1 に存在しない演算子（?? / ?. / && / || 連結・三項演算子）
     を使っていないこと
  4. pwsh / powershell が利用できる環境では
     [System.Management.Automation.Language.Parser]::ParseFile で
     ParserError が 0 件であること（無ければ skip）
"""

import pathlib
import re
import shutil
import subprocess

import pytest

_PS1 = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts" / "run_langgraph_comparison.ps1"
)
_UTF8_BOM = b"\xef\xbb\xbf"


def test_ps1_starts_with_utf8_bom():
    data = _PS1.read_bytes()
    assert data.startswith(_UTF8_BOM), (
        "run_langgraph_comparison.ps1 は UTF-8 BOM 付きで保存してください。"
        "BOM が無いと Windows PowerShell 5.1 が日本語を ANSI として誤解釈し、"
        "ParserError になります。"
    )


def test_ps1_is_valid_utf8():
    data = _PS1.read_bytes()
    text = data[len(_UTF8_BOM):].decode("utf-8")  # 失敗すれば UnicodeDecodeError
    assert "param(" in text


def test_ps1_avoids_powershell7_only_operators():
    text = _PS1.read_bytes().decode("utf-8-sig")
    code_lines = []
    in_block_comment = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("<#"):
            in_block_comment = True
        if not in_block_comment and not stripped.startswith("#"):
            # 文字列リテラル内は誤検知し得るが、対象演算子は現状未使用
            code_lines.append(line)
        if stripped.endswith("#>"):
            in_block_comment = False
    code = "\n".join(code_lines)
    for pattern, label in (
        (r"\?\?", "null 合体演算子 ??"),
        (r"\?\.", "null 条件演算子 ?."),
        (r"&&", "パイプライン連結 &&"),
        (r"\|\|", "パイプライン連結 ||"),
    ):
        assert not re.search(pattern, code), (
            f"PowerShell 5.1 に無い {label} が使われています"
        )


def _find_powershell():
    for name in ("pwsh", "powershell"):
        path = shutil.which(name)
        if path:
            return path
    return None


def test_ps1_parses_without_errors():
    """Parser::ParseFile で ParserError が 0 件（pwsh/powershell が無ければ skip）。"""
    exe = _find_powershell()
    if not exe:
        pytest.skip("pwsh / powershell が見つからないため構文解析チェックをスキップ")
    script = (
        "$tokens = $null; $errors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{_PS1}', [ref]$tokens, [ref]$errors) | Out-Null; "
        "$errors | ForEach-Object { Write-Output $_.Message }; "
        "exit $errors.Count"
    )
    result = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, (
        f"ParserError が {result.returncode} 件あります:\n{result.stdout}\n{result.stderr}"
    )

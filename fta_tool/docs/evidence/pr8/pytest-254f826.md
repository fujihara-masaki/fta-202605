# 通常の pytest（対象 254f826、開発環境 Linux、Chromium 153 を --e2e-browser-executable で明示）

対象：`254f826072b146c11883ed37b5e9e39bacbc6ebf`（クリーンな git worktree、実行の前後とも未コミットの変更なし（`git status --short` が 0 行）、`.env` なし）。2026-11-02 01:15〜01:58 UTC 実行。**Windows の Chrome・Edge での結果ではありません。** 実LLMは使っていません（E2E はテスト用サーバーの e2e-stub、通常の pytest のアプリの DB は一時ディレクトリ）。

| 項目 | 値 |
|---|---|
| 環境 | Linux-6.18.44-fc-v185-x86_64-with-glibc2.39、Python 3.12.3、`requirements-dev.txt` の固定版（playwright 1.56.0 / pytest-playwright 0.7.1、pytest 8.2.0）を入れた venv（リポジトリの外） |
| ブラウザ | Chromium 153.0.8010.12（headless、`--e2e-browser-executable=/opt/pw-browsers/chromium`）。固定版の Chromium 141 は使っていない（PR-C・PR-7 と同じ扱い） |
| 実行の順 | 1. E2E を除く → 2. 累積の全必須 E2E（Full、`e2e-report-254f826-full.md`）→ 3. E2E を含む通常の pytest |
| 後片付け | 実行の後に残ったテスト用サーバー（`stub_server`）のプロセス：0 件 |

## 1. 通常の pytest（E2E を除く）

```
python -m pytest -q -p no:cacheprovider -m "not e2e" -rs
467 passed, 20 skipped, 596 deselected, 1413 warnings in 12.72s
```

終了コード 0。スキップ 20 件は、すべて PowerShell（pwsh / powershell）がないための**環境依存のスキップ**（PR-3〜PR-7 の開発環境と同じ）：

```
SKIPPED [1] tests/test_run_browser_e2e_script.py:92: pwsh / powershell が見つからないため構文解析チェックをスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:123: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:130: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:143: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:154: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:245: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:274: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:290: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:302: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:330: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:339: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_cache_check_script.py:44: pwsh / powershell が見つからないため構文解析チェックをスキップ
SKIPPED [1] tests/test_run_cache_check_script.py:115: pwsh（PowerShell 7）が見つからないため、ラッパーの実行の確認はスキップ（Windows では tests/e2e/test_windows_tools.py）
SKIPPED [4] tests/test_run_cache_check_script.py:128: pwsh（PowerShell 7）が見つからないため、ラッパーの実行の確認はスキップ（Windows では tests/e2e/test_windows_tools.py）
SKIPPED [1] tests/test_run_cache_check_script.py:143: pwsh（PowerShell 7）が見つからないため、ラッパーの実行の確認はスキップ（Windows では tests/e2e/test_windows_tools.py）
SKIPPED [1] tests/test_run_display_check_script.py:49: pwsh / powershell が見つからないため構文解析チェックをスキップ
SKIPPED [1] tests/test_run_langgraph_comparison_script.py:83: pwsh / powershell が見つからないため構文解析チェックをスキップ
```

## 2. 累積の全必須 E2E（Full。UI 改修の必須受入検証）

```
python -m pytest -q -p no:cacheprovider -m e2e --e2e-browser-executable=/opt/pw-browsers/chromium --e2e-required --e2e-env '開発環境（Linux、headless、Chromium 153 を明示）' --e2e-report <runs>/e2e-report-full.md --output <runs>/full-out
596 passed, 487 deselected, 113 warnings in 1293.89s (0:21:33)
```

終了コード 0。記録 `e2e-report-254f826-full.md`：成功 596・失敗 0・**スキップ 0・未実施 0**、判定「合格」、**必須 75 項目すべて成功**。寸法の組は base（全テストの PR-7 の全寸法での実行（FullSizes）は、この記録では未実施）。

## 3. 通常の pytest（E2E を含む）

```
python -m pytest -q -p no:cacheprovider --e2e-browser-executable=/opt/pw-browsers/chromium -rs --output <runs>/all-out
1063 passed, 20 skipped, 1523 warnings in 1295.39s (0:21:35)
```

終了コード 0。スキップ 20 件は 1. と同じ PowerShell のもの（E2E のスキップは 0 件）。

## 件数の比較（PR-7 の受入候補 `b118038`、2026-10-30 の開発環境）

| 試験 | `b118038` | `254f826`（今回） |
|---|---|---|
| E2E を除く | 467 passed / 20 skipped | 467 passed / 20 skipped |
| Full | 596 passed（75/75） | 596 passed（75/75） |
| E2E を含む | 1063 passed / 20 skipped | 1063 passed / 20 skipped |

件数が同じなのは、`b118038` → `254f826` の差分が `fta_tool/docs/` だけで、試験のコードが同じため。

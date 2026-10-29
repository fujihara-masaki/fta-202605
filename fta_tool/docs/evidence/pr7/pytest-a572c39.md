# 通常の pytest（対象 a572c39、開発環境 Linux、Chromium 153 を --e2e-browser-executable で明示）

対象：`a572c390f6a06c0f07b622ce38ca0b701066b137`（クリーンな git worktree、未コミットの変更なし）。2026-10-29 実行。

## E2E を除く（pytest -m "not e2e"）

```
466 passed, 20 skipped, 544 deselected, 1413 warnings in 14.25s
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

## E2E を含む（pytest）

```
1010 passed, 20 skipped, 1523 warnings in 1312.74s (0:21:52)
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

スキップ 20件はすべて PowerShell がないため（この環境では PowerShell の導入・実行は行っていない）。

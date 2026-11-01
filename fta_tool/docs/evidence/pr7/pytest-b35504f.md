# 通常の pytest（対象 b35504f、開発環境 Linux、Chromium 153 を --e2e-browser-executable で明示）

対象：`b35504f826f53359d665a79ae099b5479d6d0b0a`（クリーンな git worktree、未コミットの変更なし、`.env` なし）。2026-10-30 実行。**Windows の Chrome・Edge での結果ではありません。** Full と E2E を含む実行は、途中でこの開発環境のコンテナが再起動して止まったため、同じ worktree でやり直した（下の結果はやり直した実行のもの）。

## 確認の道具（`python -m tests.e2e.launcher_probe`、手順書 第3.0節の手順0）

終了コード 0。Linux では7方式すべてで子が起動した（Windows の失敗は Linux では起きないため。方式の説明は `windows-launcher-fix-b35504f.md`）。

```
direct: 子は起動した（0.05 秒）
inherit-none: 子は起動した（0.1 秒）
share-stdin: 子は起動した（0.1 秒）
share-stdin-base: 子は起動した（0.1 秒）
share-stdin-wait: 子は起動した（0.1 秒）
own-stdin: 子は起動した（0.1 秒）
null-handles: 子は起動した（0.1 秒）
```

## 手順0の試験（8 件、`-W error::pytest.PytestUnhandledThreadExceptionWarning`）

```
PASSED tests/e2e/test_display_check.py::test_a_python_child_starts_under_the_stand_in_launcher[direct]
PASSED tests/e2e/test_display_check.py::test_a_python_child_starts_under_the_stand_in_launcher[share-stdin-wait]
PASSED tests/e2e/test_display_check.py::test_a_python_child_starts_under_the_stand_in_launcher[own-stdin]
PASSED tests/e2e/test_display_check.py::test_a_python_child_starts_under_the_stand_in_launcher[null-handles]
PASSED tests/e2e/test_display_check.py::test_close_waits_for_the_apps_own_process
PASSED tests/e2e/test_display_check.py::test_an_app_started_without_standard_handles_is_reported_at_once
PASSED tests/e2e/test_display_check.py::test_a_child_that_ends_before_the_app_starts_is_reported_at_once
PASSED tests/e2e/test_display_check.py::test_a_server_that_does_not_answer_is_reported_then_stopped
8 passed, 20 deselected, 1 warning in 11.23s
```

## 手順1と同じ7件を 10 回

```
7 passed, 21 deselected, 1 warning in 14.63s
7 passed, 21 deselected, 1 warning in 14.64s
7 passed, 21 deselected, 1 warning in 14.97s
7 passed, 21 deselected, 1 warning in 15.96s
7 passed, 21 deselected, 1 warning in 15.02s
7 passed, 21 deselected, 1 warning in 14.95s
7 passed, 21 deselected, 1 warning in 14.57s
7 passed, 21 deselected, 1 warning in 14.74s
7 passed, 21 deselected, 1 warning in 14.47s
7 passed, 21 deselected, 1 warning in 14.81s
```

## 個別の回帰試験（手順2と同じ選択、24 件）

```
24 passed, 41 deselected, 1 warning in 50.09s
```

## E2E を除く（pytest -m "not e2e"）

```
466 passed, 20 skipped, 595 deselected, 1413 warnings in 10.39s
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
1061 passed, 20 skipped, 1523 warnings in 1387.65s (0:23:07)
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

スキップ 20件はすべて PowerShell がないため。件数は `5773c84`（466／1056 passed）から、E2E を含む実行で +5（模擬ランチャーの下の子の起動 4、子が `main()` の前に終わる場合の報告 1）。すべての実行の後に、テスト用サーバー（`python -m tests.e2e.stub_server`）のプロセスは残っていなかった（0 件）。

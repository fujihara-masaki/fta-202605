# 通常の pytest（対象 32730b8、開発環境 Linux、Chromium 153 を --e2e-browser-executable で明示）

対象：`32730b89e4f8449a73d08f2c8253991b2bc1870d`（クリーンな git worktree、未コミットの変更なし、`.env` なし）。2026-10-30 実行。**Windows の Chrome・Edge での結果ではありません。**

## 修正した試験の個別の実行（手順書 第3.0節の手順2と同じ選択、`-W error::pytest.PytestUnhandledThreadExceptionWarning`）

```
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1280x800]
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1093x500]
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[900x600]
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1024x683]
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[edge150-1275x609]
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[chrome150-1280x630]
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1280x620]
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_the_notifications_are_reached_from_the_top_of_the_page[1280x800]
PASSED tests/e2e/test_pr7_focus.py::test_E_K01_the_notifications_are_reached_from_the_top_of_the_page[1093x500]
PASSED tests/e2e/test_display_check.py::test_the_display_check_tool_runs_its_checks_and_records_them
PASSED tests/e2e/test_display_check.py::test_the_test_server_releases_its_folder_when_closed
PASSED tests/e2e/test_display_check.py::test_close_waits_for_the_apps_own_process
PASSED tests/e2e/test_display_check.py::test_a_python_process_s_output_is_read_in_utf8
PASSED tests/e2e/test_display_check.py::test_the_tool_removes_its_work_folder
PASSED tests/e2e/test_display_check.py::test_a_work_folder_that_cannot_be_removed_is_not_ok
PASSED tests/e2e/test_display_check.py::test_only_the_record_folders_work_is_removed
16 passed, 41 deselected, 1 warning in 43.01s
```

警告は `app/database.py` の SQLAlchemy の `declarative_base()` の非推奨の1件だけ（以前から出ているもの）。記録：`e2e-report-32730b8-individual.md`。

## 後片付けの2件の繰り返し（`releases_its_folder or waits_for_the_apps`、20 回、`-W error::pytest.PytestUnhandledThreadExceptionWarning`）

```
2 passed, 18 deselected, 1 warning in 6.10s
2 passed, 18 deselected, 1 warning in 6.29s
2 passed, 18 deselected, 1 warning in 6.48s
2 passed, 18 deselected, 1 warning in 6.47s
2 passed, 18 deselected, 1 warning in 6.47s
2 passed, 18 deselected, 1 warning in 6.51s
2 passed, 18 deselected, 1 warning in 6.79s
2 passed, 18 deselected, 1 warning in 6.20s
2 passed, 18 deselected, 1 warning in 6.29s
2 passed, 18 deselected, 1 warning in 6.64s
2 passed, 18 deselected, 1 warning in 6.25s
2 passed, 18 deselected, 1 warning in 5.96s
2 passed, 18 deselected, 1 warning in 6.52s
2 passed, 18 deselected, 1 warning in 6.79s
2 passed, 18 deselected, 1 warning in 6.51s
2 passed, 18 deselected, 1 warning in 6.33s
2 passed, 18 deselected, 1 warning in 6.86s
2 passed, 18 deselected, 1 warning in 6.66s
2 passed, 18 deselected, 1 warning in 6.66s
2 passed, 18 deselected, 1 warning in 6.86s
```

20 回とも `2 passed`、終了コード 0。開発環境（Linux）では、開いているファイルの削除は Windows のようには失敗しないため、**この繰り返しは Windows での安定性の確認ではありません**（Windows では手順書 第3.0節の手順1で 10 回繰り返す）。

## E2E を除く（pytest -m "not e2e"）

```
466 passed, 20 skipped, 587 deselected, 1413 warnings in 11.56s
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
1053 passed, 20 skipped, 1523 warnings in 1147.90s (0:19:07)
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

スキップ 20件はすべて PowerShell がないため（この環境では PowerShell の導入・実行は行っていない）。件数は `795cf36`（466／1051 passed）から、E2E を含む実行で +2（テスト用サーバーの停止 1、文字コード 1）。

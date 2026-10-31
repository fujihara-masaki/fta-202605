# 通常の pytest（対象 5773c84、開発環境 Linux、Chromium 153 を --e2e-browser-executable で明示）

対象：`5773c847ad42567711af71b44f35808488f397c3`（クリーンな git worktree、未コミットの変更なし、`.env` なし）。2026-10-30 実行。**Windows の Chrome・Edge での結果ではありません。**

## 手順書 第3.0節の手順1と同じ6件を 10 回（`-W error::pytest.PytestUnhandledThreadExceptionWarning`）

`releases_its_folder or waits_for_the_apps or starts_again or without_standard_handles or does_not_answer or read_in_utf8`：

```
6 passed, 17 deselected, 1 warning in 15.87s
6 passed, 17 deselected, 1 warning in 16.66s
6 passed, 17 deselected, 1 warning in 15.81s
6 passed, 17 deselected, 1 warning in 15.58s
6 passed, 17 deselected, 1 warning in 16.06s
6 passed, 17 deselected, 1 warning in 15.78s
6 passed, 17 deselected, 1 warning in 15.08s
6 passed, 17 deselected, 1 warning in 14.90s
6 passed, 17 deselected, 1 warning in 15.59s
6 passed, 17 deselected, 1 warning in 15.20s
```

10 回とも `6 passed`、終了コード 0。開発環境（Linux）では子が標準入出力を受け継ぎ、開いたファイルの削除も失敗しないため、**この繰り返しは Windows での確認ではありません**。

## 個別の回帰試験（手順2と同じ選択、19 件、`-W error::pytest.PytestUnhandledThreadExceptionWarning`）

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
PASSED tests/e2e/test_display_check.py::test_the_server_starts_again_in_the_same_folder
PASSED tests/e2e/test_display_check.py::test_an_app_started_without_standard_handles_is_reported_at_once
PASSED tests/e2e/test_display_check.py::test_a_server_that_does_not_answer_is_reported_then_stopped
PASSED tests/e2e/test_display_check.py::test_a_python_process_s_output_is_read_in_utf8
PASSED tests/e2e/test_display_check.py::test_the_tool_removes_its_work_folder
PASSED tests/e2e/test_display_check.py::test_a_work_folder_that_cannot_be_removed_is_not_ok
PASSED tests/e2e/test_display_check.py::test_only_the_record_folders_work_is_removed
19 passed, 41 deselected, 1 warning in 56.59s
```

記録：`e2e-report-5773c84-individual.md`（備考に、テスト用サーバーの止まり方と一時フォルダの削除の回数）。

## E2E を除く（pytest -m "not e2e"）

```
466 passed, 20 skipped, 590 deselected, 1413 warnings in 11.42s
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
1056 passed, 20 skipped, 1523 warnings in 1197.07s (0:19:57)
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

スキップ 20件はすべて PowerShell がないため。件数は `32730b8`（466／1053 passed）から、E2E を含む実行で +3（同じフォルダでの再起動 1、起動の失敗の報告と後片付け 2）。すべての実行の後に、テスト用サーバー（`tests.e2e.stub_server`）のプロセスは残っていなかった（0 件）。

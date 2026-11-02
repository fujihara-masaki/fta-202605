# 旧版のアプリに新しい試験を当てた検出力の確認（開発環境）

対象：アプリ・スクリプトは `78e3db4`（受入候補 `a572c39` と同じアプリ）、試験（`fta_tool/tests`）は `d2eb76e` と同一（`git diff --quiet d2eb76e -- fta_tool/tests` で確認）。Linux、Chromium 153（headless、--e2e-browser-executable で明示）。2026-10-29 実行。

実行した試験：`tests/e2e/test_pr7_focus.py`（全件）、`test_pr7_viewports.py` の生成・保存失敗の試験と編集画面のレイアウトの試験、`test_pr7_screens.py` の代表画面の試験、`test_legacy_compat.py` の通知の場所の試験。

結果：**失敗 44・成功 24**（旧版で失敗するのが期待どおり）。主な失敗の理由：生成の後の生成ログの見出しが通知に覆われる、1280×800 で通知3件が生成ログを閉じるを覆う、1093×500 で要因を選んだ直後の保存が表示領域の外、Tab で移った入力欄が固定の保存・取消の帯に覆われる、フォーカスの枠がスクロール領域・表示領域の端で切れる、通知が作業エリアの下の行にない。成功した 24 件は、旧版でも条件を満たしていた寸法（例：高さが十分で編集欄が最初から見える寸法の保存・取消）。

```
__ test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x800] __
request = <FixtureRequest for <Function test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x800]>>
    def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
__ test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x620] __
request = <FixtureRequest for <Function test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x620]>>
    def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
__ test_E_V01_generation_status_log_notifications_and_a_failed_save[1366x650] __
request = <FixtureRequest for <Function test_E_V01_generation_status_log_notifications_and_a_failed_save[1366x650]>>
    def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
__ test_E_V01_generation_status_log_notifications_and_a_failed_save[1093x500] __
request = <FixtureRequest for <Function test_E_V01_generation_status_log_notifications_and_a_failed_save[1093x500]>>
    def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
__ test_E_V01_generation_status_log_notifications_and_a_failed_save[1024x683] __
request = <FixtureRequest for <Function test_E_V01_generation_status_log_notifications_and_a_failed_save[1024x683]>>
    def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
__ test_E_V01_generation_status_log_notifications_and_a_failed_save[900x600] ___
request = <FixtureRequest for <Function test_E_V01_generation_status_log_notifications_and_a_failed_save[900x600]>>
    def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
_ test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome150-1280x630] _
request = <FixtureRequest for <Function test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome150-1280x630]>>
    def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
_ test_E_V01_generation_status_log_notifications_and_a_failed_save[edge150-1275x609] _
request = <FixtureRequest for <Function test_E_V01_generation_status_log_notifications_and_a_failed_save[edge150-1275x609]>>
    def test_E_V01_generation_status_log_notifications_and_a_failed_save(page, page_watch, e2e_server, display_case,
        expect(log.locator('[data-gen-row] [data-category="failed"]')).to_have_count(1)
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1440x900]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1920x1080]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1536x730]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1280x620]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1093x500]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1024x683]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[900x600]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome150-1280x630]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[edge125-1530x731]
FAILED tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[edge150-1275x609]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1280x800]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1093x500]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[900x600]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1024x683]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[edge150-1275x609]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[chrome150-1280x630]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1280x620]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[1280x800]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[1093x500]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[900x600]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[1024x683]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[edge150-1275x609]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[chrome150-1280x630]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[1280x620]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1280x800]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1093x500]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[900x600]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1024x683]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[edge150-1275x609]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[chrome150-1280x630]
FAILED tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1280x620]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x800]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x620]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1366x650]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1093x500]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1024x683]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[900x600]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome150-1280x630]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[edge150-1275x609]
FAILED tests/e2e/test_pr7_screens.py::test_E_V01_representative_screens_of_a_generation[1280x800]
FAILED tests/e2e/test_pr7_screens.py::test_E_V01_representative_screens_of_a_generation[1093x500]
FAILED tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1093x500]
FAILED tests/e2e/test_legacy_compat.py::test_saving_dialogs_and_delete_messages_use_the_shared_notifications[1280x800]
FAILED tests/e2e/test_legacy_compat.py::test_saving_dialogs_and_delete_messages_use_the_shared_notifications[1440x900]
44 failed, 24 passed, 1 warning in 160.75s (0:02:40)
```

同じ試験は、修正版 `d2eb76e` ではすべて成功した（`e2e-report-d2eb76e-full.md`・`e2e-report-d2eb76e-allsizes.md`）。

# Windows 実機の個別の回帰試験（2026-10-30、候補 `795cf36`）：Edge で失敗 1

利用者の報告（2026-10-30）による記録です。その SHA での結果として残し、後の修正の結果で書き換えません。記録フォルダの原本（`e2e-report.md`・`pytest-output.log` など）はこのリポジトリには含めていません。

| 項目 | 値 |
|---|---|
| 対象 SHA | `795cf36b85b7c114df950b255bfe2a726ef6ab88` |
| OS | Windows 11 Home |
| 実行 | 手順書 第3.0節の個別の回帰試験（14 件。headed） |
| Google Chrome | **成功 14**、終了コード 0 |
| Microsoft Edge | **成功 13・失敗 1**、終了コード 1 |
| 準備確認・Full・表示倍率と IME の補助確認・目視 | この候補では行っていない（個別の回帰試験で失敗があったため） |

- E-K01 のキーボード操作（`test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications` の7寸法と `test_E_K01_the_notifications_are_reached_from_the_top_of_the_page` の2寸法）は、**両ブラウザで 9 件すべて成功**。2026-10-30 の Full（`d2eb76e`）の失敗は再発していない。
- Edge で失敗したテスト：`tests/e2e/test_display_check.py::test_the_test_server_releases_its_folder_when_closed`
  - エラー：`PermissionError: [WinError 32]`
  - 削除できなかったファイル：`work/fta_tool.db`
- 両ブラウザで、子プロセスの出力を読むときに `UnicodeDecodeError` が起き、`PytestUnhandledThreadExceptionWarning` が記録された（試験の成否には出ていない）。

原因と修正（候補 `32730b8`）は [windows-individual-fix-32730b8.md](windows-individual-fix-32730b8.md) と計画書 第14.8節。

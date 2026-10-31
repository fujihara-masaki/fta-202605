# Windows 実機の後片付けと文字コードの確認（2026-10-30、候補 `32730b8`）：失敗 1

利用者の報告（2026-10-30）による記録です。その SHA での結果として残し、後の修正の結果で書き換えません。記録フォルダの原本はこのリポジトリには含めていません。

| 項目 | 値 |
|---|---|
| 対象 SHA | `32730b89e4f8449a73d08f2c8253991b2bc1870d`（正しい SHA の worktree） |
| OS | Windows 11 Home |
| 実行 | 手順書 第3.0節の手順1の3件（`releases_its_folder or waits_for_the_apps or read_in_utf8`）。2026-10-30 に2回 |
| `test_the_test_server_releases_its_folder_when_closed` | 2回とも**成功** |
| `test_close_waits_for_the_apps_own_process` | 2回とも**失敗** |
| `test_a_python_process_s_output_is_read_in_utf8` | 2回とも**成功** |
| 手順2（個別の回帰試験）・準備確認・Full | この候補では行っていない（手順1で失敗があったため） |

失敗の内容：`start_server()` の起動の段階で、60 秒たってもサーバーの HTTP の応答がなく、`RuntimeError: E2E server did not start:`。`server.log` は空（エラーの文言なし）。

原因と修正（候補 `5773c84`）は [windows-start-fix-5773c84.md](windows-start-fix-5773c84.md) と計画書 第14.8節。

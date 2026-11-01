# Windows 実機の第3.0節の手順1（2026-10-30、候補 `5773c84`）：1回目で失敗 3、中断

利用者の報告（2026-10-30）による記録です。その SHA での結果として残し、後の修正の結果で書き換えません。記録フォルダの原本はこのリポジトリには含めていません。

| 項目 | 値 |
|---|---|
| 対象 SHA | `5773c847ad42567711af71b44f35808488f397c3`（正しい SHA、クリーンな worktree） |
| OS | Windows 11 Home |
| 実行 | 手順書 第3.0節の手順1（6件を 10 回）。**1回目で3件が失敗したため中断** |
| 成功 | `test_the_test_server_releases_its_folder_when_closed`（通常の終了・一時フォルダの削除）、`test_the_server_starts_again_in_the_same_folder`（同じフォルダでの再起動）、`test_a_python_process_s_output_is_read_in_utf8`（日本語の出力の UTF-8 の読み取り） |
| 失敗 | `test_close_waits_for_the_apps_own_process`、`test_an_app_started_without_standard_handles_is_reported_at_once`、`test_a_server_that_does_not_answer_is_reported_then_stopped`（3件とも試験の模擬ランチャー経由の起動） |
| 手順2・準備確認・Full | この候補では行っていない |

失敗した3件の残った記録（利用者が確認。3件とも同じ）：

| ファイル | 状態 |
|---|---|
| `launcher.pid` | **ある**（終了待ちの試験 2188、標準ハンドルの試験 39696、応答なしの試験 37500） |
| `server.pid` | ない |
| `server-stages.jsonl` | ない |
| `server.log` | あるが空 |

模擬ランチャー自身の Python のコードは実行されている（`launcher.pid` を書いた）。子のプロセスの生成が成功したか、生成の後に何が起きたかは、この候補の記録からは分からない（模擬ランチャーが自分の記録を残していなかった）。アプリの Python は `stub_server.py` の `main()`（最初に `server.pid` を書く）に達していない。

原因の調査と修正（候補 `b35504f`）は [windows-launcher-fix-b35504f.md](windows-launcher-fix-b35504f.md) と計画書 第14.8節。

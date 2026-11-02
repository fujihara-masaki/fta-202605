# CRLF の取り出しでの確認（開発環境、2026-10-27）

Windows の取り出し（`core.autocrlf=true`）を模擬するため、その回だけ `git -c core.autocrlf=true worktree add --detach <フォルダ> <SHA>` で取り出した（リポジトリ・利用者の Git の設定は変えていない）。`app/static/css/components.css` の CR は 689件。ブラウザは代替の Chromium 153.0.8010.12（`--e2e-browser-executable=/opt/pw-browsers/chromium`、headless）。

| 対象 | 実行 | 結果 |
|---|---|---|
| `a42966b`（修正前） | `tests/e2e/test_static_cache.py -k C_07` | 失敗：`assert original.count(DISABLED_RULE.encode()) == 1` → `assert 0 == 1`（Windows の報告と同じ） |
| `0dadaa2`（修正後） | `tests/e2e/test_static_cache.py -k C_07` | 成功 |
| `0dadaa2`（修正後） | `tests/test_c07_disabled_rule.py tests/test_static_cache.py tests/e2e/test_static_cache.py` | 64 passed（回帰の試験 6、H-01〜H-09、C-00〜C-07 の 11） |

これは Windows での実行ではない（Windows の Chrome・Edge での確認は未実施）。

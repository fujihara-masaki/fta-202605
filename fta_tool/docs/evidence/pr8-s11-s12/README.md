# S-11・S-12 の対策の試験記録（受入候補 `40b3778`）

状態（2026-11-02）：**開発環境の自動試験は成功**。**Windows 11 の Chrome・Edge の Preflight → Full、付録D の補足の実操作、PR-8 の最終受入（利用者）は未実施**（手順は [manual-check-pr8.md](../../manual-check-pr8.md) 第5節）。対策の内容は [pr8-s11-s12-options.md](../../pr8-s11-s12-options.md) 第8節。

## 対象

| 項目 | 値 |
|---|---|
| 受入候補（試験の対象） | `40b377813931f2d3b4080a61d0b80ebf7de0b7a1`（ブランチ `claude/pr8-s11-s12-fix` の S-12 のコミット）。クリーンな git worktree、実行の前後とも未コミットの変更なし、`.env` なし |
| 起点 | `feature/ui-redesign` = `0e62163b6460dfea358aea9ff582033c72799654`（PR #27 のマージコミット） |
| コミット | S-11 `91faf12`、S-12 `40b3778`。その後のコミットは `fta_tool/docs/`・`fta_tool/README.md`・`fta_tool/tests/e2e/README.md` だけ（文書・記録。試験は文書を読まない） |
| 対策前の記録との関係 | 対策前の `254f826` の記録（[../pr8/](../pr8/README.md)）と、PR-7 の Windows の記録 `b118038`（[../pr7/](../pr7/windows-2026-10-31-b118038.md)）は変更していない。それぞれの SHA の結果として保持する |

## ファイル

| ファイル | 内容 |
|---|---|
| `pytest-40b3778.md` | 追加の回帰試験（S-11・S-12 を別々に）、通常の pytest（E2E を除く：497 passed / 20 skipped、E2E を含む：1096 passed / 20 skipped。スキップはすべて PowerShell がないための環境依存）、Full のコマンドと件数、対策前との件数の比較、対策前のコードでの検出力 |
| `e2e-report-40b3778-full.md` | 累積の全必須 E2E（Full）の記録：成功 599・失敗 0・スキップ 0・未実施 0、判定「合格」、**必須 77 項目すべて成功**（Chromium 153、headless、18分55秒） |
| `s11-s12-probe-40b3778.md` | PR-8 の実行確認のスクリプトを変えずに受入候補で再実行：削除 3 種は 409 でデータ不変、生成 2 種は即時に `success:false`（対策前は 200 の巻き込み・500・20 秒以内に応答なし） |

## Windows の Full の件数の見込み

| | 開発環境（Linux） | Windows の Full の見込み |
|---|---|---|
| `40b3778` | 599 passed（77/77） | **601**（599 に、Windows だけで実行される `tests/e2e/test_windows_tools.py` の PowerShell の確認 2 件を足した数。PR-7 の `b118038` は開発環境 596・Windows 598 で、同じ差） |

件数は 598 に固定しない。合格の条件は、失敗・スキップ・未実施 0、必須 77 項目すべて成功、追加した E2E 3 件の成功（manual-check-pr8.md 第5節）。見込みと違う場合は理由が分かるまで合格にしない。

## 実施していないもの

- Windows の Chrome・Edge での試験（Preflight・Full）：未実施（利用者が受入候補で行う）。
- 全テストの PR-7 の全寸法での実行（FullSizes）：開発環境でも未実施（Windows は省略が承認済み）。
- Chromium 141（Playwright の固定版のブラウザ）での実行：未実施。
- 実際の uvicorn の複数ワーカーでの同時実行による S-11 の並行の変更の確認：未実施（検査の直後に別の接続で変更を確定する注入で試験）。
- CI：リポジトリに CI の設定はなく、CI の結果はない。

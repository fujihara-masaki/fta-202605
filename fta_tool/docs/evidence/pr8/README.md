# PR-8（文書更新と統合）の試験記録

> 追記（2026-11-02）：S-11・S-12 の対策後の受入候補 `40b377813931f2d3b4080a61d0b80ebf7de0b7a1` の試験記録は [../pr8-s11-s12/README.md](../pr8-s11-s12/README.md)。このフォルダの記録（対象 `254f826`、対策前）は変更していない。

状態（2026-11-02）：開発環境の自動試験は成功。**PR-8 の最終受入（利用者による付録D の確認）は未実施**（手順は [manual-check-pr8.md](../../manual-check-pr8.md)）。S-11・S-12 は判断資料の作成まで（[pr8-s11-s12-options.md](../../pr8-s11-s12-options.md)）。同日、利用者が案1（統合前に専用 PR でサーバー側の対策）を採用した（実装・試験は未実施）。**この記録は対策前のコード（`254f826`）の結果**で、PR-8 の最終受入の主な根拠は、対策後の受入候補の試験と Windows の Preflight → Full になる（manual-check-pr8.md 第1・5節）。

## 対象と、文書の更新との対応

| 項目 | 値 |
|---|---|
| 試験の対象 | `254f826072b146c11883ed37b5e9e39bacbc6ebf`（`feature/ui-redesign` の先頭、PR #26 のマージコミット）。クリーンな git worktree、実行の前後とも未コミットの変更なし、`.env` なし |
| PR-7 の受入候補との関係 | `b118038` との差分は `fta_tool/docs/` だけ（アプリ・試験・スクリプトは同じ） |
| PR-8 のブランチ | `claude/pr8-docs-integration`。試験の後のコミットは `fta_tool/README.md` と `fta_tool/docs/` だけ（文書）。試験はドキュメントを読まない（`tests/` に `docs/`・`README.md` を開く処理がないことを確認）。**したがって、この記録は PR-8 のブランチの HEAD のアプリ・試験にもそのまま当てはまる**（対応は `git diff --name-only 254f826 <HEAD>` で確かめる。PR の本文に記録） |

## ファイル

| ファイル | 内容 |
|---|---|
| `pytest-254f826.md` | 通常の pytest（E2E を除く：467 passed / 20 skipped、E2E を含む：1063 passed / 20 skipped。スキップはすべて PowerShell がないための環境依存）と Full のコマンド・件数、`b118038` との件数の比較 |
| `e2e-report-254f826-full.md` | 累積の全必須 E2E（Full）の記録：成功 596・失敗 0・スキップ 0・未実施 0、判定「合格」、必須 75 項目すべて成功（Chromium 153、headless、21分34秒） |
| `s11-s12-probe-254f826.md` | S-11・S-12 の実行確認（一時 DB。アプリの変更なし）：一覧からの分析の削除・要因の削除で別の分析の要因が消える、循環を含む削除は HTTP 500、循環上の親の生成は 20 秒以内に応答なし |

## 実施していないもの

- Windows の Chrome・Edge での試験：PR-8 では実施していない。Windows の記録は PR-7 の受入候補 `b118038` のもの（[../pr7/windows-2026-10-31-b118038.md](../pr7/windows-2026-10-31-b118038.md)）で、新しい SHA で再実行したものではない。
- 全テストの PR-7 の全寸法での実行（FullSizes）：開発環境でも PR-8 では未実施（`d2eb76e` の 2691 件合格は、その SHA の記録）。
- Chromium 141（Playwright の固定版のブラウザ）での実行：未実施。
- CI：リポジトリに CI の設定はなく、CI の結果はない。

過去の証跡（`evidence/pr7/`・`evidence/pr-c/`・`evidence/pr3/`）は変更していない。

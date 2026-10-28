# PR-7（仕上げ）の試験記録

状態（2026-10-28）：**開発環境（Linux）の自動試験の記録だけ**。Windows 11 の Chrome・Edge での確認と利用者の受入は**未実施**（手順は [manual-check-pr7.md](../../manual-check-pr7.md)）。

## 開発環境での試験の記録（Linux、headless、Chromium 153.0.8010.12 を `--e2e-browser-executable` で明示）

対象：`163b193e52acc4937dc170008e7bc4c83f0b15bb`（クリーンな git worktree）。Playwright 1.56.0 の固定版の Chromium 141 は未実施。

| ファイル | 内容 |
|---|---|
| `e2e-report-163b193-full.md` | 累積の全必須 E2E（基本寸法と PR-7 の表示のテストの寸法）。判定「合格」、成功 529・失敗 0・スキップ 0・未実施 0、必須 75 項目すべて成功、22分55秒 |
| `e2e-report-163b193-allsizes.md` | 全テストを PR-7 の全寸法で（`--e2e-required --e2e-viewport-set pr7`）。判定「合格」、成功 2629・失敗 0・スキップ 0・未実施 0、必須 75 項目すべて成功、79分31秒 |
| `pytest-163b193.md` | 通常の pytest（E2E を除く：464 passed / 20 skipped、E2E を含む：993 passed / 20 skipped。スキップはすべて PowerShell がないため） |
| `screens/` | PR-7 の表示のテストが保存した目視のレビュー用の画面のうち 12 枚（全 200 枚・35 MB から選んだもの。判定には含めない）。寸法と devicePixelRatio を指定した画面で、ブラウザの拡大・Windows の表示倍率を変えた画面ではない |


| 画面 | 寸法（CSS px・DPR） | 内容 |
|---|---|---|
| `163b193-edge150-1275x609-edit.png` | 1275×609・1.5（Edge 拡大150% の実測値） | 構造ナビの折りたたみ |
| `163b193-edge150-1275x609-nav-open.png` | 同上 | 構造ナビを開いた状態 |
| `163b193-chrome150-1280x630-edit.png` | 1280×630・1.5（Chrome 拡大150% の実測値） | 3ペイン |
| `163b193-900x600-edit.png` | 900×600 | 1024px 未満（作業エリアだけが横にスクロール） |
| `163b193-1093x500-generating.png` | 1093×500 | 生成中の状態表示 |
| `163b193-1093x500-failed-save.png` | 1093×500 | 保存失敗の表示と通知（高さ 700px 未満の通知の積み重ね） |
| `163b193-1093x500-unsaved-dialog.png` | 1093×500 | 未保存確認（要因の切替） |
| `163b193-900x600-delete-dialog.png` | 900×600 | 削除確認 |
| `163b193-edge150-1275x609-log-with-notifications.png` | 1275×609・1.5 | 部分失敗の生成ログ（終了の直後。通知が作業エリアの下部に重なる） |
| `163b193-edge150-1275x609-log-after.png` | 1275×609・1.5 | 同（自動で閉じる通知が消えた後） |
| `163b193-1093x500-font-serif-edit.png` | 1093×500 | 代替フォント（serif。この環境では和文は IPAPGothic で描画） |
| `163b193-900x600-list.png` | 900×600 | 一覧 |

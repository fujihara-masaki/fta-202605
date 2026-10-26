# PR-C（静的ファイルのキャッシュ制御）の開発環境の試験記録

対象：`03f91a9df1c48ca336672dbbbabb1808a73ad9d0`（2026-10-26 のレビュー（`748ad40`）の修正の後）と、受入候補の `2405992cdb5273571c3c23e7ffc96410433dff19`（記録の改善の後。アプリ本体は `03f91a9` と同じ）。いずれもクリーンな git worktree で実行した。Windows 実機の確認、Chromium 141 での確認、利用者の受入は**未実施**。

| ファイル | 内容 |
|---|---|
| `e2e-report-2405992.md` | 受入候補の累積の全必須 E2E。判定「合格」、成功 434・失敗 0・スキップ 0・未実施 0、必須 68 項目すべて成功 |
| `pytest-2405992.md` | 受入候補の通常の pytest（901 passed / 19 skipped、スキップはすべて PowerShell がないため） |

以下は `03f91a9` の記録：

| ファイル | 内容 |
|---|---|
| `e2e-report-03f91a9.md` | 累積の全必須 E2E（`pytest -m e2e --e2e-required`）の記録。判定「合格」、成功 434・失敗 0・スキップ 0・未実施 0、必須 68 項目すべて成功 |
| `pytest-03f91a9.md` | 通常の pytest の要約（900 passed / 19 skipped、スキップの理由の一覧。すべて PowerShell がないため） |
| `w02-tool-selfcheck-*.md` | W-02 の道具の自己確認（`tests/e2e/test_cache_manual_check.py`）で道具が作った `result.md`。**キー操作は模擬**（Ctrl+F5 は CDP の強制の再読み込み、F5 は `page.reload`）。表の「利用者の実操作」は、W-02 で利用者が行う手順を示す道具の定型の表示で、この記録では模擬の操作である。W-02 の結果ではない |

`w02-tool-selfcheck-*.md` の内訳：

| ファイル | 場面 | 判定 |
|---|---|---|
| `…-fresh-profile.md` | このオリジンを初めて開くプロフィール | OK |
| `…-uninstrumented-cache.md` | 道具の目印のない旧方式の保存が、同じコンテキスト・同じオリジンに先に残っている（手順1 で静的ファイルを取り直さずに進む。PR #24 のレビューの指摘の場面） | OK |
| `…-twice-first.md`・`…-twice-second.md` | 同じプロフィールで2回続けて実行（2回目は前の回の no-cache の保存から始まる） | 両方 OK |
| `…-forced-reload-ng.md` | 手順3 の F5 を強制の再読み込みにした | NG（期待どおり） |

ブラウザ：Playwright 1.56.0 の固定版が使う Chromium 141 は、この環境のネットワークの方針でダウンロード先（`cdn.playwright.dev`、`playwright.download.prss.microsoft.com`）が拒否され（403）、導入できなかった。代わりに環境に導入済みの Chromium 153.0.8010.12（`/opt/pw-browsers/chromium` → `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`）を `--e2e-browser-executable=/opt/pw-browsers/chromium` で明示して使った（headless）。Chromium 141 と Windows の Chrome・Edge での結果は未確認。

PowerShell：この環境には PowerShell がない（PowerShell 7 の取得は試したが、取得したものの実行は権限で止められたため使っていない）。ラッパーの構文解析・起動の試験はスキップ・未定義で、Windows の準備確認（Windows PowerShell 5.1）で実行される。

記録の中のローカルのパスは、開発環境の一時フォルダのもの。

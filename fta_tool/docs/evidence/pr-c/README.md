# PR-C（静的ファイルのキャッシュ制御）の試験記録

状態（2026-10-28）：Windows の受入試験は実施済み（利用者）。PR-C は利用者の判断で**条件付き受入**、PR #24 は `feature/ui-redesign` へマージ済み（merge commit `2e36aa8`。計画書 第14.10節）。W-02（Chrome）は終了コード 3 のまま扱う（終了コード 0 の完全な合格ではない）。Chromium 141 での確認は未実施。

この記録は、利用者が Windows で行った試験の記録と、開発環境（Linux）で行った試験の記録を分けて置く。

## Windows での試験の記録（利用者が実施）

Windows の受入試験（対象 `e12999efa4ccfe7ab0a2894baca94c997c46e54c`、2026-10-28、利用者が実施。計画書 第14.9節。受入の判断は第14.10節）：

| ファイル | 内容 |
|---|---|
| `w02-chrome-e12999e/` | W-02（Chrome）の道具の記録。利用者から受け取った `w02-chrome-e12999e.zip`（SHA-256 `5564918b1b52e8ecc58ac24507ea3918c79781bfe927c4e2fb2891c4427887e7`）の4ファイル（`result.md`・`result.json`・`static-requests.jsonl`・`probe.jsonl`）を、内容を変えずに置いた。`result.md` が参照する `w02-output.log`・`server.log` は受け取っていない。終了コード 3：改善後の動作 OK、旧方式からの実キー移行は一部未確認（終了コード 0 の完全な合格ではない） |

Chrome・Edge の Preflight・Full の結果（各 Preflight 成功 8、Full 成功 435・失敗 0・スキップ 0・未実施 0）は利用者の報告で、`e2e-report.md` の原本は受け取っていない。

2026-10-27 の Windows Chrome の Full（対象 `a42966b`、不合格：成功 433・失敗 2）は利用者の報告で、記録の原本はこのフォルダに置いていない（計画書 第14.8節）。

## 開発環境での試験の記録（Linux）

開発環境の記録の対象：`03f91a9df1c48ca336672dbbbabb1808a73ad9d0`（2026-10-26 のレビュー（`748ad40`）の修正の後）、受入候補の `2405992cdb5273571c3c23e7ffc96410433dff19`（記録の改善の後。アプリ本体は `03f91a9` と同じ）、修正後の受入候補 `0dadaa2`（下記）。いずれもクリーンな git worktree で実行した。`03f91a9`・`2405992` の記録の時点（2026-10-26）では、Windows 実機の確認と利用者の受入は未実施だった。

修正後の受入候補 `0dadaa2584cfcd0a1ee16886fe99c9fd2b6b39e6`（2026-10-27。Windows Chrome の Full（対象 `a42966b`、不合格）で失敗した C-07 の試験の修正。アプリは `03f91a9` と同じ。計画書 第14.8節）：

| ファイル | 内容 |
|---|---|
| `e2e-report-0dadaa2.md` | 累積の全必須 E2E。判定「合格」、成功 434・失敗 0・スキップ 0・未実施 0、必須 68 項目すべて成功 |
| `pytest-0dadaa2.md` | 通常の pytest（907 passed / 19 skipped、スキップはすべて PowerShell がないため） |
| `crlf-0dadaa2.md` | Windows の CRLF の取り出しを模擬した確認（修正前の C-07 の失敗の再現と、修正後の成功） |

`2405992` の記録：

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

ブラウザ：Playwright 1.56.0 の固定版が使う Chromium 141 は、この環境のネットワークの方針でダウンロード先（`cdn.playwright.dev`、`playwright.download.prss.microsoft.com`）が拒否され（403）、導入できなかった。代わりに環境に導入済みの Chromium 153.0.8010.12（`/opt/pw-browsers/chromium` → `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome`）を `--e2e-browser-executable=/opt/pw-browsers/chromium` で明示して使った（headless）。Chromium 141 での結果は未確認（現在も未実施）。この開発環境の記録は Windows の Chrome・Edge の結果ではない（Windows の結果は上の「Windows での試験の記録」）。

PowerShell：この環境には PowerShell がない（PowerShell 7 の取得は試したが、取得したものの実行は権限で止められたため使っていない）。ラッパーの構文解析・起動の試験はスキップ・未定義で、Windows の準備確認（Windows PowerShell 5.1）で実行される。

記録の中のローカルのパスは、開発環境の一時フォルダのもの。

# W-02 実キー操作による移行の確認（PR-C）

- 判定：**OK（PR-C の動作。旧方式の準備は一部）**（終了コード 3）
- 対象 SHA：`e12999efa4ccfe7ab0a2894baca94c997c46e54c`（作業ツリー クリーン）
- 確認の識別子：`20261028211335-11f5d8`（ページの報告と目印の版はこの識別子のものだけを使った）
- OS：Windows-11-10.0.26200-SP0、Python 3.12.10
- ブラウザ（指定）：Google Chrome、ページが報告した版：[{'brand': 'Not:A-Brand', 'version': '8.0.0.0'}, {'brand': 'Chromium', 'version': '156.0.8078.48'}, {'brand': 'Google Chrome', 'version': '156.0.8078.48'}]
- オリジン：http://127.0.0.1:8001（全手順で同じ）
- Ctrl+F5・F5 は利用者の実操作。それ以外（準備・版の変更・停止と同じポートでの起動・集計・判定）は自動。

## 初期状態の観察と旧方式の準備（手順1。PR-C の合否ではない）

- 旧方式の準備：**一部**（2/38 件）
- 旧方式にできなかったファイル（既存の保存を 304 で確認したもの）：css/base.css, css/components.css, css/edit.css, css/new.css, css/tokens.css, js/common/boot.js, js/common/dialog.js, js/common/dom.js, js/common/http.js, js/common/ime.js, js/common/menu.js, js/common/notify.js, js/common/storage.js, js/common/text.js, js/common/unsaved.js, js/pages/edit.js, js/pages/edit/add-dialog.js, js/pages/edit/bridge.js, js/pages/edit/delete-dialog.js, js/pages/edit/factor-editor.js, js/pages/edit/factor-source.js, js/pages/edit/filter.js, js/pages/edit/generation.js, js/pages/edit/genlog.js, js/pages/edit/inspector.js, js/pages/edit/judgement.js, js/pages/edit/model.js, js/pages/edit/permissions.js, js/pages/edit/refresh.js, js/pages/edit/restrict.js, js/pages/edit/state.js, js/pages/edit/step1.js, js/pages/edit/title.js, js/pages/edit/view.js, js/pages/new.js, style.css

## 終了コード 3 の扱い（改善後の動作は OK、旧方式の準備に不足あり）

- 終了コード 0（完全な OK）とは区別する。手順2・3 の PR-C の動作の判定はすべて OK。
- 不足した準備：上の 36 件は、手順1 の前からこのプロフィールに保存されていた応答（以前の確認の no-cache の応答など）が 304 で確認されたため、旧方式の保存にならなかった。これらのファイルについては、この回の実際の Ctrl+F5 は「旧方式からの移行」の確認になっていない。
- 既存の自動試験で確認できている範囲：旧方式の保存からの移行（3画面の強制の再読み込みで38件が no-cache になり、その後の各操作で新しい版を取得・適用する）は C-04、旧方式の配信で古い版が使われることの検出は C-05 が、同じコンテキスト・同じオリジンで確かめている（開発環境と、Windows の Full）。実際のキー操作での移行は、準備できたファイル（2 件）について、この回で確かめた。
- キャッシュの消去や追加の手動の試験は、この結果を整理して報告した後に、必要かどうかを判断する。

## PR-C の動作の判定（手順2・3）

| 項目 | 判定 | 操作 | 内容 |
|---|---|---|---|
| 手順2 一覧：Ctrl+F5 | OK | 利用者の実操作 | HTML の要求 6 件のうちキャッシュを使わない要求 1 件、ページが使った版 CSS=20261028211335-11f5d8-w1 JS={'js/common/dom.js': '20261028211335-11f5d8-w1'} |
| 手順2 新規作成：Ctrl+F5 | OK | 利用者の実操作 | HTML の要求 4 件のうちキャッシュを使わない要求 1 件、ページが使った版 CSS=20261028211335-11f5d8-w1 JS={'js/common/dom.js': '20261028211335-11f5d8-w1'} |
| 手順2 編集：Ctrl+F5 | OK | 利用者の実操作 | HTML の要求 4 件のうちキャッシュを使わない要求 1 件、ページが使った版 CSS=20261028211335-11f5d8-w1 JS={'js/common/dom.js': '20261028211335-11f5d8-w1', 'js/pages/edit/factor-source.js': '20261028211335-11f5d8-w1'} |
| 手順2：38件が 200・Cache-Control: no-cache・期待どおりの Content-Type（移行） | OK | 自動 | 38/38 件 |
| 手順3：F5 が通常の再読み込み | OK | 利用者の実操作 | HTML の要求 1 件、キャッシュを使わない要求 0 件、ナビゲーションの種類 reload（Ctrl+F5 や DevTools の「キャッシュを無効にする」では NG） |
| 手順3：編集画面の34件がそれぞれ要求された（ファイルの一致） | OK | 自動 | 期待 34 件、要求 34 件 |
| 手順3：変更した3件は w1 の ETag で要求され 200・w2 の本文 | OK | 自動 | 3件とも期待どおり |
| 手順3：変更していない31件がそれぞれ 304 | OK | 自動 | 31 件中 期待と違うもの 0 件 |
| 手順3：ページが使った版（CSS の計算値・下位のモジュールの目印） | OK | 自動 | CSS=20261028211335-11f5d8-w2 js/common/dom.js=20261028211335-11f5d8-w2 js/pages/edit/factor-source.js=20261028211335-11f5d8-w2（期待 20261028211335-11f5d8-w2） |

記録：`static-requests.jsonl`（サーバーが受けた要求と返した応答）、`probe.jsonl`（ページが使った値）、`w02-output.log`（表示した案内と結果）、`server.log`（テスト用サーバーの出力）。

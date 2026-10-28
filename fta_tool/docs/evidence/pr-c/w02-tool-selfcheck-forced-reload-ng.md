# W-02 実キー操作による移行の確認（PR-C）

- 判定：**NG**（終了コード 1）
- 対象 SHA：`03f91a9df1c48ca336672dbbbabb1808a73ad9d0`（作業ツリー クリーン）
- 確認の識別子：`20261026135527-9b25e5`（ページの報告と目印の版はこの識別子のものだけを使った）
- OS：Linux-6.18.44-fc-v153-x86_64-with-glibc2.39、Python 3.12.3
- ブラウザ（指定）：Google Chrome、ページが報告した版：[{'brand': 'Chromium', 'version': '153.0.8010.12'}, {'brand': 'Not_A Brand', 'version': '8.0.0.0'}]
- オリジン：http://127.0.0.1:50667（全手順で同じ）
- Ctrl+F5・F5 は利用者の実操作。それ以外（準備・版の変更・停止と同じポートでの起動・集計・判定）は自動。

## 初期状態の観察と旧方式の準備（手順1。PR-C の合否ではない）

- 旧方式の準備：**すべて**（38/38 件）

## PR-C の動作の判定（手順2・3）

| 項目 | 判定 | 操作 | 内容 |
|---|---|---|---|
| 手順2 一覧：Ctrl+F5 | OK | 利用者の実操作 | HTML の要求 3 件のうちキャッシュを使わない要求 1 件、ページが使った版 CSS=20261026135527-9b25e5-w1 JS={'js/common/dom.js': '20261026135527-9b25e5-w1'} |
| 手順2 新規作成：Ctrl+F5 | OK | 利用者の実操作 | HTML の要求 2 件のうちキャッシュを使わない要求 1 件、ページが使った版 CSS=20261026135527-9b25e5-w1 JS={'js/common/dom.js': '20261026135527-9b25e5-w1'} |
| 手順2 編集：Ctrl+F5 | OK | 利用者の実操作 | HTML の要求 2 件のうちキャッシュを使わない要求 1 件、ページが使った版 CSS=20261026135527-9b25e5-w1 JS={'js/common/dom.js': '20261026135527-9b25e5-w1', 'js/pages/edit/factor-source.js': '20261026135527-9b25e5-w1'} |
| 手順2：38件が 200・Cache-Control: no-cache・期待どおりの Content-Type（移行） | OK | 自動 | 38/38 件 |
| 手順3：F5 が通常の再読み込み | NG | 利用者の実操作 | HTML の要求 1 件、キャッシュを使わない要求 1 件、ナビゲーションの種類 reload（Ctrl+F5 や DevTools の「キャッシュを無効にする」では NG） |
| 手順3：編集画面の34件がそれぞれ要求された（ファイルの一致） | OK | 自動 | 期待 34 件、要求 34 件 |
| 手順3：変更した3件は w1 の ETag で要求され 200・w2 の本文 | NG | 自動 | css/components.css が w1 の ETag を送っていない; js/common/dom.js が w1 の ETag を送っていない; js/pages/edit/factor-source.js が w1 の ETag を送っていない |
| 手順3：変更していない31件がそれぞれ 304 | NG | 自動 | 31 件中 期待と違うもの 31 件：css/base.css：200; css/edit.css：200; css/tokens.css：200; js/common/boot.js：200; js/common/dialog.js：200; js/common/http.js：200; js/common/ime.js：200; js/common/menu.js：200; js/common/notify.js：200; js/common/storage.js：200; js/common/text.js：200; js/common/unsaved.js：200; js/pages/edit.js：200; js/pages/edit/add-dialog.js：200; js/pages/edit/bridge.js：200; js/pages/edit/delete-dialog.js：200; js/pages/edit/factor-editor.js：200; js/pages/edit/filter.js：200; js/pages/edit/generation.js：200; js/pages/edit/genlog.js：200; js/pages/edit/inspector.js：200; js/pages/edit/judgement.js：200; js/pages/edit/model.js：200; js/pages/edit/permissions.js：200; js/pages/edit/refresh.js：200; js/pages/edit/restrict.js：200; js/pages/edit/state.js：200; js/pages/edit/step1.js：200; js/pages/edit/title.js：200; js/pages/edit/view.js：200; style.css：200 |
| 手順3：ページが使った版（CSS の計算値・下位のモジュールの目印） | OK | 自動 | CSS=20261026135527-9b25e5-w2 js/common/dom.js=20261026135527-9b25e5-w2 js/pages/edit/factor-source.js=20261026135527-9b25e5-w2（期待 20261026135527-9b25e5-w2） |

記録：`static-requests.jsonl`（サーバーが受けた要求と返した応答）、`probe.jsonl`（ページが使った値）、`w02-output.log`（表示した案内と結果）、`server.log`（テスト用サーバーの出力）。

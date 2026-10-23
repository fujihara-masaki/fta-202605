# FTA分析支援ツール 静的ファイルのキャッシュ制御改善 仕様・試験計画

## 0. この文書について

| 項目 | 内容 |
|---|---|
| 種類 | 仕様・試験計画（現状調査、改善仕様案、方式比較、試験計画、受入条件、実装範囲、導入・切り戻し） |
| 状態 | **仕様・試験計画の提案。実装未着手。受入未実施。** 推奨方式（第4.3節）の採否は利用者が判断する（第12節） |
| 作成 | 2026-10-23 |
| 調査対象 | `feature/ui-redesign` の `3ce70990262c0b42f2f4dab2236facabcb327905`（PR #23 のマージコミット。PR #22 のマージコミット `8b862be` を含む）。作業ツリーはクリーン、`origin/feature/ui-redesign` と一致（2026-10-23 の作業開始時に GitHub とローカルで確認。依頼時の参考値から進んでいない） |
| この文書の作成で変えたもの | この文書の新規作成と、[実装計画](ui-redesign-implementation-plan.md) 第14.6節「PR-7・PR-8・別提案に残す事項」の静的ファイルのキャッシュの項目への参照の追記だけ。アプリケーションコード・テストコード・依存設定・DB は変えていない |
| 関連文書 | [ui-redesign-implementation-plan.md](ui-redesign-implementation-plan.md)（第14.6節「Windows 実機の確認（対象 `fc337f1`）」の 2026-10-22 の調査、2026-10-23 の追加の確認・受入の判断）、[manual-check-pr6.md](manual-check-pr6.md)（第10.4.3節・第10.5節・第10.6.6節）、[tests/e2e/README.md](../tests/e2e/README.md) |

この文書で守る事実と扱い（既存の記録を変えない）：

1. 2026-10-22 の Chrome の通常のウィンドウの NG（古い `components.css` が使われ、生成中の評価のボタンが淡色にならなかった）と、同日のシークレットウィンドウの OK、2026-10-23 の同じプロファイルの通常のウィンドウの OK（キャッシュ・サイトデータを明示的に消去していない）は、それぞれの事実として残す。
2. 10/22 に古い CSS が使われた根本原因は**未特定**。この文書は「キャッシュを消して直った」「HTTP キャッシュが原因と確定した」とは扱わない。第2節の調査・予備実測で示す仕組みは「アプリの更新の後に古い静的ファイルが使われ得る経路」であり、10/22 の原因の再現・特定ではない。
3. PR-6 の受入合格（2026-10-23、利用者）と PR #22 のマージ（`8b862be`）の判断は変えない。
4. `ERR_NO_BUFFER_SPACE`（Tcpip のイベント 4231）は別の課題とする（第9.4節で関係だけ述べる）。
5. 改善案を作っただけであり、**実装済み・検証済み・受入合格・事象解消とは記載しない。**

記載の区分（この文書全体で使う）：

| 区分 | 意味 |
|---|---|
| 確認（コード・文書） | 調査対象 SHA のコードと文書を読んで確かめたこと |
| 実測（開発環境・今回） | 今回、Linux の開発環境で、一時作業ディレクトリ・一時 DB の E2E 用スタブサーバーに対して測ったこと |
| 予備実測（使い捨ての最小サーバー） | 今回、アプリとは別の最小の Starlette サーバー（スクラッチ領域。リポジトリに入れていない）と Chromium で、ブラウザの再利用の仕組みを確かめたこと。アプリの実装・試験の結果ではない（付録A） |
| 計画 | 将来の実装 PR で行うこと。未実施 |
| 未確認 | 今回確かめていないこと |

---

## 1. 背景と目的

### 1.1 経緯（記録の要約。詳細は実装計画 第14.6節）

| 日 | 環境 | 結果（既存の記録のとおり） |
|---|---|---|
| 2026-10-22 | Chrome の通常のウィンドウ | **NG**：読み込まれた `components.css` に修正の規則がなく、評価のボタンは `opacity=1`・`cursor=pointer`。同じページから `fetch(…, { cache: 'no-store' })` で得たサーバーの応答には規則があった。DevTools のキャッシュの無効とハードリロードの後も同じ（操作は利用者報告。Network の記録なし） |
| 2026-10-22 | Chrome のシークレットウィンドウ | **OK** |
| 2026-10-23 | Chrome の通常のウィンドウ（消去なし） | **OK**：`components.css` は `200 OK (from memory cache)`、内容・読み込まれた規則とも修正後。`Cache-Control` なし |

原因の候補 a〜d（HTTP キャッシュ、別アプリの Service Worker、拡張機能・DevTools の上書き、古いサーバー）は、どれも確定していない（実装計画 第14.6節）。受入の判断では、残るリスクとして「静的ファイルの応答に `Cache-Control` がなく URL に版が付かないため、アプリの更新の後に普段のブラウザでしばらく古い CSS・JavaScript が使われる可能性がある」ことを記録し、キャッシュ制御を後続の改善候補とした。

### 1.2 目的

アプリの更新の後に、利用者が通常の操作で画面を読み込んだとき、**更新された画面（HTML）と整合する CSS・JavaScript（入口のモジュールと、import される下位モジュールのすべて）が使われる**ようにする。原因の確定を前提にせず、更新の後に古い静的ファイルが使われるリスクを減らすことを目的とする。

### 1.3 対象外

- 10/22 の根本原因の特定（この改善では行わない。候補 b・c はアプリの配信では制御できない）。
- すでに実行中の JavaScript を自動で差し替えること、未保存の入力を失う強制の再読み込み、更新の通知の仕組み。
- Service Worker・CDN・フロントエンドのビルド基盤の導入、DB スキーマ・業務 API の契約・生成プロンプト・LangGraph・Quality Gate の変更。
- `ERR_NO_BUFFER_SPACE` の調査。

---

## 2. 現状調査（調査対象 `3ce7099`）

### 2.1 調査の対象と環境

| 項目 | 内容 | 区分 |
|---|---|---|
| リポジトリ・ブランチ | `fujihara-masaki/fta-202605`、`feature/ui-redesign`。HEAD `3ce70990262c0b42f2f4dab2236facabcb327905`、`origin/feature/ui-redesign` と一致、作業ツリーはクリーン、未コミットの変更なし | 確認 |
| PR の状態（GitHub） | PR #22（PR-6）：マージ済み（2026-10-23 03:14 UTC、マージコミット `8b862be`、HEAD の祖先）。PR #23（受入・マージの記録）：マージ済み（07:41 UTC、`3ce7099`）。PR #19：Draft・open（head `feature/ui-redesign`＝`3ce7099`、base `claude/fta-analysis-tool-Yg5yn`＝`8a50db1`）。変更していない | 確認 |
| 後続の課題 | 実装計画 第14.6節「PR-7・PR-8・別提案に残す事項」：静的ファイルのキャッシュの扱い（案A 推奨・案B、未承認、PR-7 か別の PR かは利用者が判断）。手順書 第10.6.6節も同じ | 確認 |
| 依存の指定 | `requirements.txt`：`fastapi==0.111.0`、`uvicorn[standard]==0.29.0`、`jinja2==3.1.4`、`httpx==0.27.0`。Starlette は直接の指定なし（FastAPI 0.111.0 の依存で 0.37.x）。`requirements-dev.txt`：`playwright==1.56.0`（同梱 Chromium 141.0.7390.37）、`pytest-playwright==0.7.1` | 確認 |
| 今回の調査環境 | Linux、Python 3.12.3。スクラッチ領域の専用の仮想環境に `requirements-dev.txt` の固定版を導入：fastapi 0.111.0、**starlette 0.37.2**、jinja2 3.1.4、uvicorn 0.29.0、httpx 0.27.0、playwright 1.56.0、pytest-playwright 0.7.1。システムの Python（3.13、FastAPI なし）は使っていない | 実測 |
| ブラウザ（予備実測） | Playwright 1.56.0 が期待する Chromium 141 はこの環境にない。環境に導入済みの `/opt/pw-browsers/chromium`（**Chromium 153.0.8010.12**、headless）を `executable_path` で起動した（`playwright install` はしていない）。Windows の Chrome・Edge の挙動ではない | 実測 |
| 実LLM | 使っていない（スタブ） | — |

利用者の通常の DB・通常利用中のサーバーは使っていない。応答の実測は `tests.e2e.stub_server` をスクラッチ領域の新しい作業ディレクトリ（一時 DB `fta_tool.db`）でポート 18765 に起動して行い、終了後に停止した（ポート 8000〜8002 は使っていない）。

### 2.2 `/static` の配信（確認）

- [`app/main.py`](../app/main.py) 172行：`mimetypes.add_type("text/javascript", ".js")`（Windows のレジストリで `.js` が `text/plain` になる場合への対策。PR-1 以来）。
- 同 173行：`app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")`。Starlette の `StaticFiles` をそのまま使い、サブクラス・ミドルウェア・応答ヘッダーの追加はない。
- アプリ全体にキャッシュ関連のミドルウェア・設定はない（`Cache-Control` の文字列はアプリのコードにない）。
- 配信されるファイル：`app/static/` の **38件**（CSS 7件：`css/tokens.css`・`base.css`・`components.css`・`list.css`・`new.css`・`edit.css`、`style.css`。JavaScript 31件：`js/common/` 10件、`js/pages/` 3件、`js/pages/edit/` 18件）、合計 344,640 バイト（調査対象 SHA の作業ツリー）。

### 2.3 HTML から直接参照するファイル（確認）

| テンプレート | 画面 | CSS（`<link>`） | JavaScript（`<script type="module">`） |
|---|---|---|---|
| [`base.html`](../app/templates/base.html) | 全画面の共通部分 | `/static/css/tokens.css`、`/static/css/base.css`、`/static/css/components.css`、`{% block screen_styles %}`（既定は `/static/style.css`） | `/static/js/common/boot.js`、`{% block extra_scripts %}` |
| [`index.html`](../app/templates/index.html) | 分析一覧 | `screen_styles` を `/static/css/list.css` に置き換え | `/static/js/pages/list.js` |
| [`analysis_form.html`](../app/templates/analysis_form.html) | 新規作成 | `/static/css/new.css` に置き換え | `/static/js/pages/new.js` |
| [`analysis_detail.html`](../app/templates/analysis_detail.html) | 分析・編集 | `/static/css/edit.css` と `/static/style.css` | `/static/js/pages/edit.js` |

- URL はすべて版のない固定のパス（クエリ・ハッシュ・版のセグメントなし）。テンプレートの構造テスト（[`tests/test_ui_templates.py`](../tests/test_ui_templates.py) の T-01・T-03 など）は、この URL を完全一致で検査している。
- `analysis_detail.html` の分析データと `analysis_form.html` のサンプルは、`<script type="application/json">` で HTML に埋め込まれている（HTML と JavaScript の版が合わないと、埋め込みの形と読み取りの処理が合わないおそれがある）。

### 2.4 JavaScript の import の依存関係（確認）

すべての `import` は静的な `import … from '<相対パス>'`（`./`・`../` で始まる）で、**動的な `import()`、絶対パス・クエリ付きの指定子、`<script>` 以外の読み込みはない**。どの入口からも到達しないモジュールはない。

| 画面 | 入口 | 読み込まれる JavaScript（入口を含む） | CSS | 合計 | バイト数 |
|---|---|---|---|---|---|
| 分析一覧 | `boot.js`＋`pages/list.js` | 10件（`common/` の boot・menu・unsaved・dialog・dom・notify・http・ime・text、`pages/list.js`） | 4件 | 14件 | 91,463 |
| 新規作成 | `boot.js`＋`pages/new.js` | 9件（`common/` の boot・menu・unsaved・dialog・dom・notify・ime・text、`pages/new.js`） | 4件 | 13件 | 87,885 |
| 分析・編集 | `boot.js`＋`pages/edit.js` | 29件（`common/` の10件すべて、`pages/edit.js`、`pages/edit/` の18件） | 5件 | 34件 | 315,302 |

- 依存の深さ：`edit.js` → `edit/inspector.js` → `edit/factor-editor.js` → `edit/factor-source.js` の3段が最も深い。入口が変わらず下位のモジュールだけが変わる更新（例：`edit/judgement.js`・`common/unsaved.js` だけの修正）は普通に起こる。
- `common/unsaved.js` などはモジュールの中に状態（生成の段階、未保存の登録）を持ち、`boot.js` と各画面の入口が**同じ URL** で import して同じ実体を共有している。ES モジュールは URL ごとに1つの実体になるため、URL を変える方式では、すべての読み込みが同じ URL になることが必要になる（第4節）。
- E2E は `page.evaluate` の中で `import('/static/js/common/unsaved.js')` などとして画面と同じモジュールの実体を参照している（[`tests/e2e/edit_helpers.py`](../tests/e2e/edit_helpers.py) 277行、`test_edit_generation_saves.py`・`test_edit_leave.py`・`test_edit_switch.py`・`test_edit_inspector.py`・`test_edit_generation_leave.py`・`test_foundation.py`）。URL に版を付けると、これらは画面と別の実体を読み込み、誤った値（例：常に `idle`）を返すおそれがある。

### 2.5 CSS の中の参照（確認）

7件の CSS に `@import` と `url()` はない（フォント・画像の参照なし。T-01 の `test_T01_static_css_and_js_have_no_external_urls_or_web_fonts` が外部 URL とウェブフォントがないことを検査している）。CSS から下位の資産への依存はないため、対象は第2.3節の `<link>` の7件で閉じる。

### 2.6 応答ヘッダー（実測、開発環境・`3ce7099`）

| 要求 | 状態 | 主なヘッダー |
|---|---|---|
| `GET /static/css/components.css` | 200 | `content-type: text/css; charset=utf-8`、`content-length: 16479`、`last-modified: Fri, 23 Oct 2026 13:50:13 GMT`（作業ツリーのファイルの時刻＝取り出した時刻）、`etag: "08b7d8cb6c728441c4c5bdea35af8f9e"`。**`Cache-Control`・`Expires`・`Vary` なし** |
| `GET /static/js/common/unsaved.js` | 200 | `content-type: text/javascript; charset=utf-8`。ほかは同上 |
| `GET /static/style.css` | 200 | 同上 |
| `HEAD /static/css/components.css` | 200 | GET と同じヘッダー、本文なし |
| `GET /static/css/nope.css`（存在しない） | 404 | `content-type: application/json`、本文 `{"detail":"Not Found"}`。検証子・`Cache-Control` なし |
| `GET /static/css/`（ディレクトリ） | 404 | 同上（`html=False`） |
| `POST /static/css/components.css` | 405 | `{"detail":"Method Not Allowed"}` |
| `GET /`、`GET /analyses/new`、`GET /analyses/1` | 200 | `content-type: text/html; charset=utf-8`。**`Cache-Control`・`ETag`・`Last-Modified` なし** |
| `GET /nodes/1`（業務 API の例） | 404（要因なし） | `application/json`。検証子・`Cache-Control` なし |
| `GET /analyses/1/export/json`・`csv`・`markdown` | 200 | `content-disposition: attachment; filename=fta_1.*`、各 `content-type`。検証子・`Cache-Control` なし |

### 2.7 ETag・Last-Modified と条件付き要求（確認：Starlette 0.37.2 のコード、実測）

**生成**（`starlette/responses.py` の `FileResponse.set_stat_headers`）：

- `Last-Modified` = `formatdate(st_mtime)`（**秒の単位**）。
- `ETag` = `md5(str(st_mtime) + "-" + str(st_size))` の16進（引用符付きの強い ETag）。`st_mtime` は小数の秒（例 `1792763863.091672`）で、**内容は使わない**。内容が変わっても、更新時刻（小数を含む）とサイズが同じなら同じ ETag になる。
- ヘッダーは `setdefault` で設定される（`FileResponse` に `headers` で渡した値が優先される）。

**判定**（`starlette/staticfiles.py` の `StaticFiles.is_not_modified`）：

1. `If-None-Match` の各値から前後の空白・`W`・`/` を除き、ETag と一致すれば 304。
2. **一致しなかった場合も** `If-Modified-Since` を評価し、`If-Modified-Since >= Last-Modified` なら 304。

RFC 9110 第13.1.3節は「`If-None-Match` がある要求では `If-Modified-Since` を無視しなければならない」としており、2 はこれと異なる。ブラウザは保存した応答に ETag と Last-Modified の両方があれば両方を送る（予備実測で Chromium 153 が両方を送ることを確認）。このため、**ETag が変わっていても、新しいファイルの時刻（秒の単位）が保存済みの `Last-Modified` 以前なら 304 になり、古い内容が使われ続ける**。

304 の応答（`NotModifiedResponse`）は `cache-control`・`content-location`・`date`・`etag`・`expires`・`vary` だけを引き継ぐ。`StaticFiles` は GET・HEAD 以外に 405、パスの外へ出る要求・存在しないファイル・ディレクトリに 404 を返す。

**実測（開発環境のスタブサーバー、`components.css`）**：

| 要求ヘッダー | 状態 |
|---|---|
| `If-None-Match`＝現在の ETag | 304 |
| `If-None-Match`＝`W/`＋現在の ETag | 304 |
| `If-None-Match`＝別の値のみ | 200 |
| `If-None-Match`＝別の値＋`If-Modified-Since`＝現在の `Last-Modified` | **304**（上記 2 による） |
| `If-None-Match`＝別の値＋`If-Modified-Since`＝過去 | 200 |
| `If-Modified-Since` のみ（未来の時刻） | 304 |
| `If-None-Match: *` | 200（`*` は扱われない。ブラウザは送らない） |
| `HEAD`＋`If-None-Match`＝現在の ETag | 304 |

**境界条件（実測、Starlette 0.37.2 の `StaticFiles` を一時ディレクトリで直接使用）**：旧版を取得した後に内容を変え、旧版の ETag（と Last-Modified）を送った。

| 変更の仕方 | ETag | Last-Modified | `If-None-Match` のみ | `If-None-Match`＋`If-Modified-Since`（ブラウザの再検証） |
|---|---|---|---|---|
| 同じサイズ、更新時刻を保持（コピーで時刻を引き継ぐ） | 同じ | 同じ | **304（見落とし）** | **304（見落とし）** |
| 同じサイズ、同じ秒の中で更新（+0.5秒） | 変わる | 同じ | 200 | **304（見落とし）** |
| サイズが変わる、更新時刻を保持 | 変わる | 同じ | 200 | **304（見落とし）** |
| 古い時刻のファイルへ置換（作成時刻の古い作業ツリーへの切替、切り戻し、アーカイブの展開） | 変わる | 変わる（過去へ） | 200 | **304（見落とし）** |
| 通常の更新（現在の時刻） | 変わる | 変わる | 200 | 200 |

現行の構成では、これらの再検証は経験則の鮮度が切れた後にだけ起こる（第2.8節）。案A（`no-cache` だけ）を入れると再検証が毎回になるため、この見落としが通常の読み込みのたびに効くようになる（第2.8節の予備実測 B・C）。

### 2.8 ブラウザ側の再利用（予備実測、使い捨ての最小サーバー・Chromium 153 headless）

アプリと同じ形（HTML から CSS 1件と入口のモジュール、入口が相対パスで下位のモジュールを import）の最小のページで確かめた。同じブラウザコンテキスト・同じオリジンのまま、サーバー側でファイルを書き換えた。通信の差し替え・キャッシュの無効化は使っていない（強制の再読み込みは A の手順4 だけ）。手順は付録A。

**現行と同じ配信（`Cache-Control` なし。ファイルの時刻は10日前）**

| 手順 | 静的ファイルの要求（サーバーの記録） | 使われた版 |
|---|---|---|
| 1. 初回（v1） | 3件とも 200 | v1 |
| 2. 同じ版でもう一度 `goto` | **要求なし** | v1 |
| 3. CSS・下位モジュールを v2 にして `goto` | **要求なし** | **v1（古い）** |
| 4. リンクのクリック | 要求なし | v1 |
| 5. 再読み込み（`page.reload`、F5 相当） | **要求なし** | v1 |

→ `Last-Modified` から経験則で鮮度を決めて検証せずに使い、F5 でも静的ファイルの要求は出なかった（HTML の要求は記録していない）。

**`Cache-Control: no-cache`＋`If-None-Match` 優先の判定**

| 手順 | 静的ファイルの要求 | 使われた版 |
|---|---|---|
| 1. 初回 | 3件とも 200 | v1 |
| 2. 同じ版で `goto` | 3件とも 304（`If-None-Match`・`If-Modified-Since` の両方あり） | v1 |
| 3. v2 にして `goto` | 3件とも 200 | **v2** |
| 4. リンク・5. F5 | 304 | v2 |
| 6. 下位モジュールだけ v3b に変えて `goto` | 200（下位モジュールが新しい内容で実行された） | CSS v2・下位 v3b |

Playwright 1.56 の `response.status` は、再検証の応答を 304 と報告した（参考。判定はサーバーの記録による）。

**A：従来のキャッシュからの移行**（同じコンテキスト・同じオリジン）

| 手順 | 要求 | 使われた版 |
|---|---|---|
| 1. 現行の配信で v1（時刻は10日前） | 200（`Cache-Control` なし） | v1 |
| 2. サーバーを `no-cache`＋判定の補正に切り替え、v2 にして `goto` | **要求なし** | **v1** |
| 3. F5 | **要求なし** | **v1** |
| 4. 強制の再読み込み（CDP `Page.reload` の `ignoreCache`、Ctrl+F5 相当） | 200（`no-cache`） | v2 |
| 5. v3 にして通常の `goto` | 200（`no-cache`） | **v3** |

→ 新しい応答ヘッダーは、ブラウザがその URL をサーバーに問い合わせるまで、保存済みの応答に影響しない。一度問い合わせて新しい応答（200 か 304）を受けた後は、通常の操作で更新が反映された。

**B：`no-cache` だけ（判定の補正なし）、同じ秒の中の更新**：v1 の後に v2 を同じ秒で書くと、通常の `goto` で **304（v1 のまま）**。判定の補正を入れると同じファイルで 200（v2）。

**C：`no-cache` だけ、古い時刻のファイルへ置換**：新しいほうの後に古い時刻のファイルへ置き換えると **304（新しいほうのまま）**。判定の補正を入れると 200。

**D：履歴の移動（戻る。Playwright の既定で BFCache は無効）**：`no-cache` でも、戻るでは静的ファイルの**要求なし**で以前の版が使われた（更新後の v2 ではなく v1）。その後の通常の `goto` では 200（v2）。

予備実測の限界：Linux の headless の Chromium 153 で、Windows の Chrome・Edge（channel、headed）、ディスクキャッシュ（Playwright のコンテキストは一時的なもの）、実際のアプリの画面では確かめていない。経験則の鮮度の詳細（ブラウザの実装の値）も測っていない。

### 2.9 Service Worker などの有無（確認）

- アプリの JavaScript に `serviceWorker`・`caches.`（Cache Storage）の利用はない。テンプレートに manifest・preload の指定もない。
- 10/22 の原因の候補 b（同じオリジンに以前に登録された別アプリの Service Worker）・c（拡張機能、DevTools のローカルの上書き）は、アプリの応答ヘッダーや URL では制御できない。この改善でも解決を保証しない（第3.3節）。Service Worker を新設する前提にはしない。

### 2.10 HTTP キャッシュ・BFCache・sessionStorage・localStorage の違い

| 仕組み | 保存されるもの | 有効な範囲・期間 | このアプリでの利用（確認） | この改善との関係 |
|---|---|---|---|---|
| HTTP キャッシュ（メモリ・ディスク） | HTTP の応答（静的ファイル、HTML など） | ブラウザのプロファイル（シークレット・Playwright のコンテキストでは一時的）。鮮度は `Cache-Control`、なければ経験則 | 設定なし。静的ファイルは経験則で検証なしに再利用される（第2.8節） | **対象**。応答ヘッダーで再利用と再検証を決める。メモリ・ディスクのキャッシュの利用（`(memory cache)`・`(disk cache)`・304）自体は不具合ではない |
| BFCache（戻る・進むのキャッシュ） | ページ全体（DOM、実行中の JavaScript の状態） | 同じタブの履歴。短時間 | 利用を前提に対策済み：`pageshow`（`persisted`）で送信中・生成中の状態を戻す（[`common/unsaved.js`](../app/static/js/common/unsaved.js) 116行、[`pages/edit/generation.js`](../app/static/js/pages/edit/generation.js) 728〜730行、[`pages/new.js`](../app/static/js/pages/new.js) 268行）、`pagehide` で状態を保存（[`pages/edit.js`](../app/static/js/pages/edit.js) 444行） | 復元されたページは古い版のまま動く。この改善では差し替えない（第3.3節）。HTML に `no-store` を付けると Chrome では BFCache の対象外になり得るため、HTML の配信は変えない（第5.5節） |
| sessionStorage | 画面の状態（`fta:edit:v1:<id>`：表示・絞り込み・スクロール）、生成ログ（`fta:genlog:v1:<id>`） | タブごと。タブの複製では写しが渡る | [`pages/edit/state.js`](../app/static/js/pages/edit/state.js) 51行、[`pages/edit/genlog.js`](../app/static/js/pages/edit/genlog.js) 48行（`common/storage.js` の `sessionStore`） | 変えない。キーに形式の版（`v1`）があり、JavaScript の更新で形式を変える場合は版を上げる（既存の方針）。静的ファイルのキャッシュとは独立 |
| localStorage | — | オリジンごと、期限なし | `common/storage.js` に `localStore` があるが、画面の処理からの利用はない（E2E の `test_foundation.py` だけ） | 変えない |

### 2.11 再利用できる既存の試験・基盤（確認）

| 既存のもの | 内容 | この計画での使い方 |
|---|---|---|
| `tests/test_ui_templates.py` の `client`（TestClient、一時 DB） | テンプレートの構造、`test_javascript_is_served_with_a_javascript_mime_type`（`pages/` と `pages/edit/` の JS の `content-type`） | HTTP の試験（H-xx）の土台。MIME の検査を全38件へ広げる |
| `tests/e2e/stub_server.py`・`support.start_server(workdir, port, extra_env)` | 一時作業ディレクトリ・一時 DB の実アプリ、スタブの生成、`stub_control.json` の `delay`（`delay_seconds`）、外部通信の遮断、`FTA_E2E_ACCESS_LOG`（診断用。ヘッダーを記録しない） | キャッシュの試験の専用サーバー。試験専用の設定（静的ファイルの配信元の一時コピー、配信方式の切替、静的ファイルの要求・応答ヘッダーの記録）を追加する（第6.3節） |
| `tests/e2e/acceptance.py`（`REQUIRED_IDS`、必須受入検証でスキップ・未実施を失敗にする） | 累積の必須 ID（PR-6 時点で60項目） | 新しい試験 ID を必須に加える |
| `tests/e2e/test_edit_generation_leave.py` の `bfcache_page` | `--disable-back-forward-cache` を外した専用のブラウザでの実 BFCache の試験（E-G08・E-G12） | 回帰の確認。模擬の `pageshow` イベントの試験とは区別して記録する |
| E-G04（生成中の操作制限、評価のボタンの無効） | 一時的なコンテキストでの初回の読み込み | 回帰の確認に使う。**キャッシュ更新の試験の成功としては流用しない** |
| E-X01、T-01 | 外部への通信・外部 URL がない | 回帰の確認 |
| `scripts/run_browser_e2e.ps1`（Setup・Preflight・Full・Diagnose） | Windows の Chrome・Edge（`--browser-channel`、headed、一時プロフィール）で準備確認・全必須 E2E、記録フォルダ | Full で新しい必須 E2E も実行される（スクリプトの変更は不要の見込み。実装時に確認） |
| 手順書 [manual-check-pr6.md](manual-check-pr6.md) 第5.1節・第10.5節 | 手動確認のスタブ（環境変数で `mode=delay`・20秒）、DevTools での Status・Size・ヘッダー・CSSOM の確かめ方 | Windows 実機の確認（W-xx）の手順の土台 |

### 2.12 既存計画の記述への補足（過去の観測事実は変えない）

実装計画 第14.6節の案A・案Bの説明は判断の前の記録として残し、この文書で次の条件を補う。

| 既存の記述 | 補足 |
|---|---|
| 案A：「毎回問い合わせて、変わっていなければ 304。JavaScript のモジュールの中の `import` にも効く」 | `import` 先にも効くことは予備実測と合う。ただし Starlette 0.37.2 の判定（第2.7節）のままでは、同じ秒の更新・時刻を保持した置換・古い時刻への置換で「変わっていても 304」になる。案A には判定の補正が要る（第4.3節の案A+） |
| 案B：「モジュールの中の `import` には別の仕組みが要り、変更が広い」 | `?v=` のようなクエリは相対パスの `import` に引き継がれないため正しい。URL のパスの区切り（例 `/static/<版>/…`）に版を置けば、相対パスの `import` は版を引き継ぐ（第4.1節 B2）。ただしテンプレート・E2E の URL の変更が広いことは変わらない |
| 「どちらも、すでにブラウザに残ったキャッシュには効かない（次に取り直した時から効く）」 | 案A については予備実測 A と合う。URL を変える方式（案B）は、新しい HTML が読み込まれた時点で古い URL の応答を使わなくなるため、残ったキャッシュの影響を受けにくい（ただし HTML が新しく取得されることが条件） |
| 「経験則（一般に `Last-Modified` からの経過時間の約1割）」 | RFC 9111 第4.2.2節が典型として示す値で、ブラウザの実装による。期間は「応答を保存した時点の `Last-Modified` からの経過時間」に依存し、作業ツリーを作った時刻からの経過で変わる |
| 「同じ `ETag` の問い合わせに 304」 | 違う ETag でも `If-Modified-Since` が新しいファイルの時刻以後なら 304（第2.7節の実測） |

---

## 3. 改善の目的と保証範囲

### 3.1 用語

| 用語 | 意味 |
|---|---|
| 新規の画面読み込み | アドレスバーへの入力・ブックマーク・新しいタブで画面を開くこと |
| 通常の画面遷移 | 画面内のリンク（ヘッダーの「分析一覧」「新規作成」、一覧の「編集」など）、フォームの送信と 303 のリダイレクト（新規作成）による移動 |
| 通常の再読み込み | F5・再読み込みのボタン（Ctrl+F5・Shift+F5・Ctrl+Shift+R は含まない） |
| 強制の再読み込み | Ctrl+F5・Shift+F5・Ctrl+Shift+R（キャッシュを使わずに取得する）。自動試験では CDP の `Page.reload`（`ignoreCache: true`）を同等のものとして使う |
| 履歴の移動 | 戻る・進む。BFCache から復元される場合と、BFCache を使わずに読み込み直す場合がある |
| 更新 | サーバーを止め、`app/static/` のファイルを入れ替え（作業ツリーの切替・取り出しを含む）、サーバーを起動すること（第3.5節） |

### 3.2 保証すること（導入後）

| ID | 内容 |
|---|---|
| G-1 | 改善の導入後に取得・再検証した静的ファイルについて、次回以降の更新では、**新規の画面読み込み・通常の画面遷移・通常の再読み込み**のたびに、その画面が使う CSS（7件のうちその画面のもの）と JavaScript（入口と、import されるすべての下位モジュール）がサーバーに再検証され、**その時点のサーバーの内容**が使われる |
| G-2 | 内容が変わっていないファイルは 304 で再利用され、本文を再送しない（メモリ・ディスクのキャッシュの利用と 304 は正常な動作として扱う） |
| G-3 | ファイルの時刻・サイズの扱い（同じ秒の更新、同じサイズ、時刻を保持した置換、古い時刻への置換）にかかわらず、内容が変われば 200 で新しい内容を返す（第5.4節） |
| G-4 | CSS・JavaScript の `Content-Type`（`text/css; charset=utf-8`、`text/javascript; charset=utf-8`）、存在しないファイル・ディレクトリ・GET/HEAD 以外への応答、HTML・業務 API・出力の応答は変えない |

### 3.3 保証しないこと

| ID | 内容 | 理由 |
|---|---|---|
| N-1 | すでに開いている画面の CSS・JavaScript を更新後の内容に差し替えること | 実行中のモジュールは差し替えられない。強制の再読み込みは未保存の入力を失うおそれがある。利用者が次に画面を読み込んだ時点で G-1 が働く |
| N-2 | BFCache から復元された画面が新しい版になること | ページ全体が以前の状態で戻る仕組み。既存の `pageshow` の処理（生成中・送信中の状態を戻す）は維持する |
| N-3 | BFCache を使わない履歴の移動（戻る・進む）で新しい版になること | ブラウザは履歴の移動で保存済みの応答を検証せずに使うことがある（予備実測 D）。続く通常の画面遷移・再読み込みで G-1 が働く |
| N-4 | Service Worker、拡張機能、DevTools のローカルの上書き、プロキシなど、アプリの配信の外にある仕組みが返す内容 | アプリの応答では制御できない（10/22 の候補 b・c を含む） |
| N-5 | 更新の途中（サーバーの稼働中にファイルを書き換えている間）に読み込んだ画面の版の一貫性 | 前提（第3.5節）で除く |
| N-6 | 改善の導入前に保存された応答（第3.4節）が、導入の直後の通常の操作で置き換わること | 新しいヘッダーは、ブラウザがその URL を問い合わせるまで保存済みの応答に効かない（予備実測 A） |

### 3.4 改善の導入前に保存された応答からの移行

| ID | 内容 |
|---|---|
| M-1 | 導入前に保存された静的ファイルの応答（`Cache-Control` なし、経験則の鮮度）は、ブラウザがその URL をサーバーに問い合わせた時点で、新しい方式の応答（200、または 304 による保存済みのヘッダーの更新。RFC 9111 第4.3.4節）に置き換わる。置き換わった後は G-1 が働く |
| M-2 | 問い合わせが起こる条件：(a) 経験則の鮮度が切れた後の最初の利用（期間はブラウザの実装と、その応答の保存時の `Last-Modified` からの経過時間による。上限は事前に決められない）、(b) その画面での**強制の再読み込み1回**（Ctrl+F5）。通常の再読み込み（F5）では置き換わらない（予備実測 A） |
| M-3 | 移行の操作（利用者向けの案内。導入の手順に書く）：導入の後に最初に使うときに、**分析一覧・新規作成・分析・編集の3画面でそれぞれ Ctrl+F5 を1回**行う。3画面で38件のすべてが読み込まれる（`style.css` は編集画面、`list.css`・`new.css` はそれぞれの画面、`storage.js` と `pages/edit/` は編集画面）。キャッシュ・サイトデータの消去、プロファイルの作り直しは求めない。未保存の入力がない状態で行う |
| M-4 | 移行の操作を行わなくても、導入の PR 自体は静的ファイルの内容を変えないため、導入の直後に古い応答が使われても、その内容は「導入前の最後に取得した版」であり、導入による新しい不整合は生じない。リスクは「導入前から古い版が残っていた場合」と「M-2 (a) の前に次の更新が来た場合」に残る |

M-3 は強制の再読み込みを**移行の操作**として定義するもので、通常の利用で更新が反映されることの根拠には使わない（更新の反映は、移行の後の通常の操作で確かめる。第6.5節 C-04）。

### 3.5 前提（更新の手順）

1. 更新は「サーバーを止める → ファイルを入れ替える → サーバーを起動する」の順に行う（現在の運用：作業ツリーごとにサーバーを起動している）。稼働中のファイルの書き換えは前提にしない。
2. 同じオリジン（`http://127.0.0.1:<ポート>`）で配信する。ポートが変わればオリジンが変わり、キャッシュは別になる（移行の問題は生じないが、sessionStorage なども別になる）。
3. 同じオリジンに、このアプリ以外の Service Worker・上書きがない（N-4）。

---

## 4. 方式の比較

### 4.1 候補

| 案 | 内容 |
|---|---|
| A | 既存計画の案A。`/static` の応答に `Cache-Control: no-cache` を付ける。判定・ETag は Starlette のまま |
| **A+** | 案A に、条件付き要求の判定の補正（`If-None-Match` があればそれだけで判定し `If-Modified-Since` を無視）と、**内容から作る ETag** を加える。URL・テンプレートは変えない |
| B1 | テンプレートの `<link>`・`<script>` の URL に `?v=<版>` を付ける |
| B2 | URL のパスに版を置く（例 `/static/<リリースの識別子>/css/…`）。識別子は静的ファイル全体の内容のハッシュ。相対パスの `import` は版を引き継ぐ。長期の保存（`max-age`＋`immutable`）も可能 |
| B3 | ファイルごとの内容のハッシュを名前に入れる（`components.<hash>.css`）。`import` の指定子も書き換える |
| C | A+ と B2 の併用（または、A+ に導入時1回だけの URL の基点の変更を加える） |
| D | `Clear-Site-Data: "cache"` を HTML の応答に付け、オリジンのキャッシュを消させる |
| E | `/static` の応答に `Cache-Control: no-store` を付ける |

### 4.2 比較

| 観点 | A | **A+** | B1 | B2 | B3 | C | D | E |
|---|---|---|---|---|---|---|---|---|
| CSS と import 先を含む適用範囲 | 38件すべて（マウント単位） | 38件すべて | `<link>`・入口の `<script>` だけ。**下位モジュールは旧版のまま**（入口だけに `?v=` を付ける設計になる） | 38件すべて（相対 `import` が版を引き継ぐ） | すべて（指定子の書き換えが前提） | すべて | オリジンのキャッシュ全体 | 38件すべて |
| 変更するファイル | `main.py` | `main.py`（＋小さなクラス1つ） | テンプレート4件 | テンプレート4件、`main.py`（版付きの配信・識別子の計算・テンプレートの関数）、URL を完全一致で検査するテスト、E2E の `import('/static/…')` 約10ファイル、手順書 | B2 に加えビルドの工程（ファイル名・指定子の書き換え） | A+＋B2 | `main.py`、送る条件の管理 | `main.py` |
| 保守の負担 | 小 | 小 | 小（ただし不完全） | 中：E2E の `import()` が別の実体を読むと誤判定になるため、版付きの URL を使う共通の関数が要る | 大：ビルド基盤の新設 | 中〜大 | 中 | 小 |
| 同じ内容の再利用・要求数・転送量 | 毎回の再検証（一覧14・新規13・編集34件の条件付き要求、内容が同じなら 304 で本文なし） | A と同じ | 現行と同じ（経験則） | `immutable` なら版が同じ間は要求なし。`no-cache` なら A と同じ | 要求なし | A と同じか少ない | 毎回の全取得（消去後） | **毎回の全取得**（編集画面で約315KB） |
| 更新時の挙動 | 再検証で反映。**ただし同じ秒・時刻を保持した置換・古い時刻への置換で 304 の見落とし** | 内容が変われば必ず 200 | 入口・CSS だけ反映、下位モジュールは旧版（混在） | 新しい HTML から新しい URL を使う | 同左 | 同左 | 消去のたびに反映 | 毎回反映 |
| 切り戻し時の挙動 | 古い時刻のファイルへ戻すと 304 の見落とし（第2.7節） | 内容の比較で正しく 200 | 旧版の URL が残っていれば旧版 | 旧版の識別子は内容のハッシュのため、残った応答も同じ内容で正しい | 同左 | 同左 | — | 毎回反映 |
| 従来のキャッシュが残っている場合 | 問い合わせるまで効かない（M-2） | 同左（M-3 の操作で移行） | 新しい URL は即時に移行。下位は残る | **新しい HTML を読んだ時点で移行**（古い URL を使わない） | 同左 | 同左 | 送った応答の後は消える | 問い合わせるまで効かない |
| HTML 側の変更の必要 | 不要 | 不要 | テンプレートの変更。HTML が新しく取得されることが条件 | 同左。HTML の鮮度が前提（現在は検証子なしで毎回取得） | 同左 | 同左 | HTML の応答に付ける | 不要 |
| FastAPI・Jinja2・標準 ES モジュールとの適合 | そのまま | サブクラスで実現（Starlette の公開のメソッドの上書き） | そのまま | Jinja2 の関数と独自の配信が要る。`import` は相対のため適合 | **ビルドなしの構成と合わない** | B2 と同じ | 消去の範囲が広い（BFCache・他の応答も失う）。送る回数の管理が要る | そのまま |
| 既存の試験への影響 | 小 | 小 | テンプレートの URL の検査 | 大（第2.4節の E2E の `import()`、URL の完全一致の検査） | 大 | 大 | 中 | 小 |

### 4.3 推奨：案A+（案Aに条件付き要求の判定の補正と内容から作る ETag を加える）

**採用の理由**：

1. 目的（G-1）を、URL・テンプレート・JavaScript を変えずに満たす。`/static` のマウント単位で効くため、CSS 7件と、入口・下位を含む JavaScript 31件のすべてに同じ規則が当たる。下位モジュールだけの更新も、入口と同様に再検証される（予備実測の手順6）。
2. 案A だけでは、Starlette 0.37.2 の判定（`If-None-Match` が一致しなくても `If-Modified-Since` で 304）と、時刻・サイズだけの ETag のため、作業ツリーの切替・切り戻し・同じ秒の更新で古い内容が使われ続ける（第2.7節の実測、予備実測 B・C）。判定の補正と内容の ETag で、更新の手順の時刻の扱いに依存しなくなる（G-3）。
3. 変更が小さく（`main.py` とクラス1つ）、既存の E2E の `import('/static/…')` やテンプレートの URL の検査に影響しない。切り戻しも小さい（第10.3節）。
4. 再検証の費用（一覧14件・新規13件・編集34件の条件付き要求、内容が同じなら 304）は、ローカルで1人が使うこのツールでは小さい。
5. 既存計画で第一候補とした案A と同じ方向で、HTML の配信・BFCache の動き・sessionStorage の扱いを変えない。

**残る制約**（利用者の判断の材料）：

- **従来のキャッシュからの移行は自動ではない**（N-6、M-2）。導入の後に3画面で Ctrl+F5 を1回ずつ行う案内（M-3）が要る。行わない場合のリスクは M-4 のとおり限られるが、0 にはならない。即時の移行を必須とするなら、URL を変える方式（C）が要り、その場合は第2.4節の E2E の `import()` の書き換えを含む大きな変更になる（第12節 判断2）。
- 毎回の再検証で要求の数が増える（内容が同じなら本文は送らない）。
- N-1〜N-5 は保証しない。10/22 の候補 b・c が原因であれば、この改善では解決しない。
- 予備実測は Linux の headless の Chromium 153 で、Windows の Chrome・Edge では未確認（実装後の試験で確かめる）。

### 4.4 採らない案の理由

- **B1**：相対パスの `import` にクエリが引き継がれないため、入口と CSS だけが新しくなり下位モジュールが旧版のまま混在する。採らない。
- **B2**：移行が即時という利点はあるが、URL の変更が広く（テンプレート、URL の完全一致の検査、E2E の `import()` が別の実体を読む問題）、長期の保存は「同じ URL が同じ内容を表す」条件（識別子が静的ファイル全体の内容のハッシュで、識別子の違う要求に別の内容を返さない）を守る仕組みが要る。今回の目的には過大。将来、配信の規模が大きくなった場合の候補として残す。
- **B3**：ビルド基盤が要り、現在の構成（ビルドなしの標準 ES モジュール）と合わない。
- **C**：移行の即時性だけのために B2 の費用を負う。利用者が即時の移行を必須とする場合だけ検討する（第12節 判断2）。
- **D**：消去の範囲が広く（オリジンのすべてのキャッシュ。ブラウザによっては BFCache の項目も失う）、送る回数を管理する仕組み（クッキーなど）が要る。採らない。
- **E**（`no-store`）：再利用をやめても正しさは A+ と変わらず、毎回の全取得の費用だけが増える。保存済みの応答への効果は A と同じ（問い合わせるまで効かない）。採らない。HTML への `no-store` は BFCache に影響し得るため行わない（第5.5節）。
- **時刻・乱数の付与**（毎アクセスで URL を変える）：版の管理ではなく、キャッシュを常に使わない手段であり、同じモジュールの実体の共有も壊す。採らない。

---

## 5. 推奨方式（案A+）の仕様

### 5.1 仕様の項目

| ID | 仕様 |
|---|---|
| SP-01 | `/static` の通常のファイルへの GET・HEAD の 200 応答に `Cache-Control: no-cache` を付ける |
| SP-02 | 同じ要求の 304 応答にも `Cache-Control: no-cache` と ETag を付ける（Starlette の `NotModifiedResponse` が引き継ぐ） |
| SP-03 | ETag は**ファイルの内容**から作る強い ETag とする（例：SHA-256 の16進の先頭32文字を引用符で囲む）。内容が同じなら、時刻・サイズ・作業ツリーが違っても同じ値になる |
| SP-04 | `If-None-Match` がある要求は、ETag の弱い比較（`W/` を除いて比較。`,` 区切りの複数の値、`*` を扱う）だけで判定し、`If-Modified-Since` を無視する（RFC 9110 第13.1.3節・第13.2.2節） |
| SP-05 | `If-None-Match` がない要求の `If-Modified-Since` は、現行どおり評価する（`If-Modified-Since >= Last-Modified` で 304）。ブラウザは ETag があれば `If-None-Match` を送るため、ブラウザの再検証はこの判定に依存しない |
| SP-06 | `Last-Modified` は現行どおり（ファイルの時刻）付ける（診断で作業ツリーを見分けるため。判定には SP-04・SP-05 の範囲でだけ使う） |
| SP-07 | `Content-Type` は現行どおり（`.css` は `text/css; charset=utf-8`、`.js` は `main.py` の `mimetypes` の固定により `text/javascript; charset=utf-8`） |
| SP-08 | 存在しないファイル・ディレクトリ・パスの外への要求（404）、GET・HEAD 以外（405）の応答は現行どおり（`Cache-Control` を付けない） |
| SP-09 | HTML（`/`、`/analyses/new`、`/analyses/{id}`）の応答は変えない（`Cache-Control`・ETag・`Last-Modified` なし）。理由は第5.5節 |
| SP-10 | 業務 API（`/analyses/…`・`/nodes/…` の POST・GET）、出力（`/analyses/{id}/export/*`）、リダイレクトの応答は変えない |
| SP-11 | テンプレートの URL、JavaScript の `import`、CSS・JavaScript の内容は変えない（この改善の PR では静的ファイルの内容を変えない。M-4） |
| SP-12 | 導入の手順に、従来のキャッシュからの移行の操作（M-3）を書く |

### 5.2 HTTP 応答の方針

| 対象の URL | メソッド | 条件 | 状態 | 設定するヘッダー（変更点は太字） |
|---|---|---|---|---|
| `/static/<ファイル>`（38件） | GET | 条件なし、または `If-None-Match` が一致しない | 200 | **`Cache-Control: no-cache`**、**`ETag: "<内容のハッシュ>"`**、`Last-Modified`（現行）、`Content-Type`（現行）、`Content-Length`（現行）、本文 |
| 同 | GET | `If-None-Match` が一致（`W/` 付き・複数値・`*` を含む） | 304 | **`Cache-Control: no-cache`**、**`ETag`**、`Date`。本文なし |
| 同 | GET | `If-None-Match` なし、`If-Modified-Since >= Last-Modified` | 304 | 同上（現行の判定を維持） |
| 同 | GET | `If-None-Match` なし、`If-Modified-Since < Last-Modified` | 200 | 200 の行と同じ |
| 同 | HEAD | 上の各条件 | 200／304 | GET と同じヘッダー、本文なし |
| `/static/<存在しないもの>`、ディレクトリ、パスの外 | GET・HEAD | — | 404 | 現行どおり（`application/json`、`Cache-Control` なし） |
| `/static/<ファイル>` | POST など | — | 405 | 現行どおり |
| `/`、`/analyses/new`、`/analyses/{id}` | GET | — | 200／404 | 現行どおり（変更なし） |
| 業務 API・出力・`POST /analyses` の 303 | 各 | — | 各 | 現行どおり（変更なし） |
| `/favicon.ico` | GET | — | 404（現行） | 変更なし。PR-7 で favicon を `/static` の下に置く場合は SP-01〜SP-08 が適用される |

### 5.3 ETag の生成と判定（実装の概略。計画）

`StaticFiles` のサブクラス（例：`app/static_files.py` の `RevalidatedStaticFiles`）で、Starlette 0.37.2 の公開のメソッド `file_response` と `is_not_modified` を上書きする。

- `file_response`：ファイルを読んでハッシュを計算し、`FileResponse(full_path, status_code=…, stat_result=…, headers={"etag": …, "cache-control": "no-cache"})` を作る（`set_stat_headers` は `setdefault` のため、渡した ETag が使われる。`Last-Modified`・`Content-Length` は従来どおり時刻・サイズから）。その後に `is_not_modified` で 304 を決める。
- `is_not_modified`：SP-04・SP-05。
- 費用：要求ごとに最大 34KB（`common/unsaved.js`）のファイルを1回余分に読む。編集画面で合計約315KB。ローカルの1人の利用では小さいと考える（実装の PR で応答時間を確かめる。第6.5節 H-01）。時刻・サイズをキーにした結果の再利用は、時刻を保持した置換で古い値を返すため行わない。
- Starlette の版を上げる場合は、上書きしたメソッドの名前・引数が変わっていないかを確かめる（依存の更新は今回の対象外）。

### 5.4 境界条件の整理

| 条件 | 現行 | 案A | 案A+ | 扱い |
|---|---|---|---|---|
| 同じ秒の中の更新（サイズ同・異） | 経験則の鮮度の間は要求なし。再検証時は 304 の見落とし | **304 の見落とし**（予備実測 B） | 内容の ETag と SP-04 で 200 | **対応**（SP-03・SP-04）。H-04・C-06 で確かめる |
| 同じサイズで時刻を保持した置換（`copy` で時刻を引き継ぐ、アーカイブの展開など） | 同じ ETag で 304 の見落とし | 同左 | 内容の ETag で 200 | **対応**（SP-03）。H-04 で確かめる |
| サイズが変わり時刻を保持 | ETag は変わるが `If-Modified-Since` で 304 | 同左 | 200 | **対応**（SP-04）。H-04 |
| 古い時刻のファイルへの置換（作成時刻の古い作業ツリーへの切替、切り戻し） | `If-Modified-Since` で 304 | **304 の見落とし**（予備実測 C） | 200 | **対応**（SP-04）。H-04・C-06 |
| `If-None-Match` と `If-Modified-Since` が同時 | 両方で判定（RFC と異なる） | 同左 | `If-None-Match` だけ | **対応**（SP-04）。ブラウザの通常の再検証がこの形（予備実測で確認） |
| `If-Modified-Since` だけ（ETag を保存しないクライアント） | 時刻で判定 | 同左 | 時刻で判定（同じ秒の更新は見落とし得る） | **前提**：ブラウザは ETag を送る。ブラウザ以外の利用は対象外。H-05 で現行の判定の維持を確かめる |
| 時刻の分解能が粗いファイルシステム（FAT・exFAT の2秒など） | 同じ秒の更新と同じ | 同左 | 内容の ETag で影響なし | 対応（SP-03） |
| サーバーの稼働中のファイルの書き換え | ハッシュと本文の間の不一致があり得る | 同左 | 同左 | **前提**（第3.5節 1）。試験の対象外 |
| ブラウザが保存した古い応答（導入前） | — | 問い合わせるまで効かない | 同左 | **移行**（M-1〜M-4）。C-04 で確かめる |

### 5.5 HTML の扱い

- 現行の HTML の応答には検証子（ETag・`Last-Modified`）も `Cache-Control` もないため、経験則の鮮度の対象にならず、通常の画面遷移・再読み込みでは毎回サーバーから取得される（実装の PR で C-03 として確かめる。予備実測では HTML の要求を記録していない）。
- **変更しない**。理由：(1) G-1 に HTML の変更は要らない（URL を変えないため、HTML の鮮度は版の切替の条件にならない）。(2) `no-store` は Chrome では BFCache の対象外になり得るため、既存の BFCache の試験（E-G12）と利用者の操作を変える。(3) `no-cache` の明示は現在の動きと同じで、効果がない。
- 履歴の移動（N-3）では、HTML も保存済みのものが使われ得る。この改善では扱わない。

### 5.6 業務 API・出力への影響

`/static` のマウントの中だけを変えるため、業務 API（JSON）、出力（JSON・CSV・Markdown の添付）、リダイレクトの応答は変わらない（H-07 で現行のヘッダーと同じことを確かめる）。JavaScript の `fetch` の既定のキャッシュの扱いも変えない。

---

## 6. 試験計画（すべて計画。今回は実施していない）

### 6.1 方針

- 試験は、実装の PR で次の4種類に分ける：**HTTP の自動試験**（pytest、TestClient・一時ディレクトリ）、**ブラウザの自動試験**（Playwright。開発環境の同梱 Chromium と、Windows の Chrome・Edge の channel）、**Windows の自動試験**（`run_browser_e2e.ps1` の Full に含める）、**Windows の実操作・目視**（必要な範囲に絞る）。
- 合格は、ヘッダーが付いていることに加え、**定義した更新・移行の条件で、期待する版の資産が実際に使われる**こと（適用された CSS、実行された JavaScript、サーバーの記録の組み合わせ）とする。
- 既存の E-G04 などの成功（一時的なコンテキストでの初回の読み込み）を、キャッシュ更新の試験の成功として流用しない。

### 6.2 キャッシュ更新の試験の成立条件（第6.5節の C-01〜C-07 に適用）

| 条件 | 実装での守り方 |
|---|---|
| 1. 旧版の読み込みから新版の確認まで、同じブラウザコンテキスト・同じオリジンを維持する | 1つの試験関数の中で1つのコンテキスト・1つのページを使い続ける。サーバーは試験の間止めず、同じポートのまま（配信方式の切替はサーバーの設定ファイルで行う。第6.3節） |
| 2. 途中でコンテキストを作り直さない、キャッシュを消さない | `context.clear_cookies` などの消去、新しいコンテキストの作成を使わない |
| 3. `page.route`・`context.route`・HAR からの応答・CDP のキャッシュの無効化を使わない | 試験のファイルに `route(`・`route_from_har`・`Network.setCacheDisabled`・`setExtraHTTPHeaders` がないことを静的に検査する試験（C-00）を置く。`Page.reload` の `ignoreCache` は C-04 の移行の手順だけで使い、検査で場所を限る |
| 4. DevTools の「キャッシュを無効にする」・強制の再読み込みだけの結果を根拠にしない | 自動試験は DevTools を使わない。Windows の実操作では「キャッシュを無効にする」を外したまま記録する。強制の再読み込みは M-3 の移行の操作としてだけ使い、更新の反映はその後の通常の操作で判定する |
| 5. 通常の画面遷移・再訪と、通常の再読み込みを区別する | 各試験で「リンクのクリック（通常の画面遷移）」「`page.goto`（新規の読み込みに相当）」「`page.reload`（F5）」を別の段階として判定・記録する |
| 6. 旧版が取得・保存され、キャッシュを使える状態であることを確かめる | 旧版を読み込んだ後、内容を変える前に同じ画面へもう一度移り、対象の資産が 304（案A+）または要求なし（現行の配信）になったことをサーバーの記録で確かめる。確かめられなければ試験を失敗にする（成立していない試験を合格にしない） |
| 7. CSS の適用結果・JavaScript の動作・通信の記録を組み合わせる | CSS：試験用の印（`:root` のカスタムプロパティ）の計算値と、実際の規則（例：`.ui-judgement__option:disabled`）の CSSOM・計算値。JavaScript：試験用の印（モジュールの最上位で設定する値）と、画面の動作。通信：サーバー側の記録（状態・`If-None-Match`・`If-Modified-Since`・ETag・`Cache-Control`・`Content-Type`）。ブラウザの表示や Playwright の `response.status` だけで 304・使われた内容を決めない |

### 6.3 試験用の構成（実装の PR で追加する。アプリのコードは試験のために変えない）

| 項目 | 内容 |
|---|---|
| 静的ファイルの一時コピー | 試験ごとに `app/static/` を pytest の一時ディレクトリへコピーし、試験用サーバーがそれを配るようにする。**リポジトリの `app/static/` と利用者のデータは書き換えない** |
| 試験用サーバーの設定（試験専用） | `tests/e2e/stub_server.py` に試験専用の環境変数を追加：`FTA_E2E_STATIC_DIR`（`static` のマウントの配信元を一時コピーへ向ける。マウントの `app` を同じクラスで作り直す）、`FTA_E2E_STATIC_LOG`（`/static` の要求ごとに、パス・メソッド・状態・`If-None-Match`・`If-Modified-Since`・応答の ETag・`Cache-Control`・`Content-Type` を JSON lines で記録。本文・クッキーは記録しない） |
| 配信方式の切替（検出力の確認・移行の試験用） | 作業ディレクトリの `static_control.json`（`{"policy": "app" \| "baseline" \| "nocache-only"}`）を要求ごとに読む：`app`＝アプリの実装、`baseline`＝Starlette の `StaticFiles` そのもの（調査対象 SHA の配信と同じ）、`nocache-only`＝案A（`no-cache` だけ、判定・ETag は Starlette のまま）。サーバーを止めずに同じオリジンで切り替える |
| 旧版・新版の作り方 | 一時コピーの中で、Python で書き換える。CSS：対象のファイルの末尾に `:root{--fta-cache-probe-<ファイル名>:"v1"}` を加え、新版で `"v2"` にする。実際の規則の確認には、旧版で `.ui-judgement__option:disabled` の規則を除き、新版で戻す（PR-6 の修正前後の差に相当する形。**10/22 の再現とは扱わない**）。JavaScript：対象のモジュールの末尾に `globalThis.__ftaCacheProbe = Object.assign(globalThis.__ftaCacheProbe ?? {}, {"<パス>": "v1"});` を加え、新版で `"v2"` にする |
| 時刻の設定 | 旧版のファイルの時刻を `os.utime` で10日前にする（現行の配信なら経験則で長く再利用される状態にし、試験の検出力を持たせる）。境界条件の試験では、同じ秒・時刻の保持・古い時刻を `os.utime` で作る |
| 生成中の表示 | 既存のスタブの `stub_control.json` の `{"mode": "delay", "delay_seconds": N}` を使う（ブラウザの通信の差し替えに依存しない） |
| ブラウザ | 開発環境は同梱の Chromium（headless）。Windows は `--browser-channel chrome`・`msedge`（headed、Playwright の一時プロフィール）。BFCache の試験だけは既存の `bfcache_page` と同じく `--disable-back-forward-cache` を外す |

### 6.4 試験の一覧

| ID | 観点 | 種類 | 必須／条件付き | 対応する仕様・保証 |
|---|---|---|---|---|
| H-01 | 初回取得（全38件のヘッダー・`Content-Type`） | HTTP 自動 | 必須 | SP-01・SP-03・SP-06・SP-07、G-4 |
| H-02 | HEAD | HTTP 自動 | 必須 | SP-01・SP-02 |
| H-03 | 同じ版の再取得（304） | HTTP 自動 | 必須 | SP-02・SP-04、G-2 |
| H-04 | 内容の変更後の条件付き要求（境界条件を含む） | HTTP 自動 | 必須 | SP-03・SP-04、G-3 |
| H-05 | `If-Modified-Since` だけの要求 | HTTP 自動 | 必須 | SP-05 |
| H-06 | エラーの応答（404・405） | HTTP 自動 | 必須 | SP-08、G-4 |
| H-07 | HTML・業務 API・出力への影響なし | HTTP 自動 | 必須 | SP-09・SP-10、G-4 |
| H-08 | 対象の範囲（テンプレートの URL・`import` が `/static` の中に閉じる、CSS に `@import`・`url()` なし、版のクエリなし） | 静的検査（自動） | 必須 | SP-11 |
| H-09 | 検出力の確認（Starlette のままでは H-04 の見落としが起きる） | HTTP 自動 | 必須 | 第6.7節 |
| C-00 | 試験の成立条件の静的検査（通信の差し替え・キャッシュの無効化を使っていない） | 静的検査（自動） | 必須 | 第6.2節 |
| C-01 | CSS だけの更新 | ブラウザ自動 | 必須 | G-1・G-2 |
| C-02 | 下位の JavaScript モジュールだけの更新 | ブラウザ自動 | 必須 | G-1 |
| C-03 | HTML が通常の画面遷移・再読み込みで毎回取得されること | ブラウザ自動 | 必須 | 第5.5節（SP-09 の前提） |
| C-04 | 従来の方式からの移行 | ブラウザ自動 | 必須 | M-1〜M-3、N-6 |
| C-05 | 検出力の確認（現行の配信・案A のままで古い資産が使われることを検出できる） | ブラウザ自動 | 必須 | 第6.7節 |
| C-06 | 境界条件（同じ秒の更新、古い時刻への置換）をブラウザの再検証で | ブラウザ自動 | 必須 | G-3 |
| C-07 | 生成中の評価のボタンの無効の見た目が、CSS の更新の後に通常の操作で効く | ブラウザ自動 | 必須 | G-1（代表の画面の動作） |
| C-08 | 履歴の移動・BFCache の観察 | ブラウザ自動 | 条件付き（記録のみ。合否に含めない） | N-2・N-3 |
| R-01 | 通常の pytest | 自動 | 必須 | 回帰 |
| R-02 | 累積の必須 E2E（開発環境、Windows Chrome・Edge） | 自動 | 必須 | 回帰（第6.8節） |
| W-01 | Windows での応答ヘッダー・MIME・304 の確認（DevTools） | Windows 実操作 | 必須 | SP-01〜SP-07 |
| W-02 | Windows の普段のプロファイルでの移行（M-3）と、その後の通常の操作 | Windows 実操作 | 必須 | M-1〜M-3 |
| W-03 | 次の実際の更新（例：PR-7 の取り込み）での反映の観察 | Windows 実操作 | 条件付き（次の更新の時に行う。この PR の受入には含めない） | G-1 |

### 6.5 各試験の詳細

**H-01 初回取得**
- 目的：38件のすべてが正常に取得され、ヘッダーと `Content-Type` が仕様どおりであることを確かめる。
- 前提：アプリ（`app.main.app`）の TestClient（一時 DB）。
- 入力：`app/static/` の下のファイルを列挙した38件（列挙の件数が 0 でないことも検査）。
- 手順：各ファイルに条件なしで GET。
- 期待・判定：200、`Cache-Control: no-cache`、ETag が引用符付きの強い ETag でファイルの内容のハッシュと一致、`Last-Modified` あり、`.css` は `text/css; charset=utf-8`、`.js` は `text/javascript` で始まる、本文がファイルと同じ。応答時間を記録する（判定には使わない）。
- 証跡：pytest の出力。必須。

**H-02 HEAD**：H-01 と同じ38件に HEAD。200、GET と同じヘッダー、本文なし。`If-None-Match` が一致すれば 304。必須。

**H-03 同じ版の再取得**
- 目的：再検証で正常な 304 を返すことを確かめる。
- 手順：H-01 の ETag・`Last-Modified` を使い、(a) `If-None-Match` のみ、(b) `W/` 付き、(c) `"x", <ETag>` の複数値、(d) `*`、(e) `If-None-Match`＋`If-Modified-Since`（ブラウザの形）で GET。
- 期待：すべて 304、本文なし、`Cache-Control: no-cache`、同じ ETag。必須。

**H-04 内容の変更後の条件付き要求**
- 目的：旧版の識別情報を送った場合に、更新後の内容を取得できることを、境界条件を含めて確かめる。
- 前提：アプリと同じクラスを一時ディレクトリに向けて使う（リポジトリのファイルは変えない）。
- 入力・旧版と新版：一時ディレクトリの CSS・JS を書き、旧版の ETag・`Last-Modified` を記録した後、次の5通りで新版にする：通常の更新、同じサイズで時刻を保持、同じ秒の中の更新、サイズが変わり時刻を保持、古い時刻への置換。
- 手順：旧版の `If-None-Match`＋`If-Modified-Since` で GET。
- 期待：5通りとも 200、本文が新版、ETag が新版の内容のハッシュ。内容を旧版に戻した場合は旧版の ETag と一致し 304（切り戻しの形）。必須。

**H-05 `If-Modified-Since` だけ**：`If-None-Match` なしで、`If-Modified-Since` が `Last-Modified` 以後なら 304、前なら 200（SP-05 の現行の判定の維持）。必須。

**H-06 エラーの応答**：存在しないファイル・ディレクトリ・`..` を含むパスに 404（`application/json`、`Cache-Control` なし）、POST・PUT に 405。調査対象 SHA の応答（第2.6節）と状態・`Content-Type`・本文が同じ。必須。

**H-07 HTML・業務 API・出力**：`/`、`/analyses/new`、`/analyses/{id}`、`GET /nodes/{id}`、出力3種、`POST /analyses` の 303 に、`Cache-Control`・ETag・`Last-Modified` が加わっていないこと、`Content-Type`・`Content-Disposition` が現行どおりであること。必須。

**H-08 対象の範囲**：テンプレートを描画した HTML の `<link>`・`<script src>` がすべて `/static/` で始まりクエリ・ハッシュを含まないこと、全 JS の `import` の指定子が相対パスで実在するファイルに解決されること、CSS に `@import`・`url(` がないこと、`app/static/` のすべてのファイルが3画面のどれかから到達されること（到達しないファイルがあれば一覧を出して失敗。意図して置くファイルは明示して除く）。必須。

**H-09 検出力の確認（HTTP）**：H-04 の5通りを Starlette の `StaticFiles` そのもので行い、「同じサイズで時刻を保持」「同じ秒」「サイズが変わり時刻を保持」「古い時刻」の4通りで 304 になる（見落としが起きる）ことを確かめる。試験が見落としを検出できることの確認であり、10/22 の再現ではない。必須。

**C-00 成立条件の静的検査**：キャッシュの試験のファイルに `route(`・`route_from_har`・`setCacheDisabled`・`clear_cookies`・`new_context(` の2回目以降の呼び出しがないこと、`ignoreCache` が C-04 の移行の関数の中にだけあることを、ソースの検査で確かめる。必須。

**C-01 CSS だけの更新**
- 目的：キャッシュを保持したブラウザで、新しい CSS が実際に適用されることを確かめる。
- 前提：専用の試験用サーバー（一時コピー、`policy=app`）、1つのコンテキスト。分析を1件作る。
- 入力：`components.css` と `edit.css` に試験用の印 `v1`（時刻は10日前）。
- 手順：(1) 編集画面を開く。(2) ヘッダーの「分析一覧」をクリックし、一覧の「編集」で編集画面へ戻る（通常の画面遷移）。サーバーの記録で対象の CSS が 304 であることを確かめる（成立条件6）。(3) `components.css` だけを `v2` にする（`edit.css` と JS は変えない）。(4) 通常の画面遷移で編集画面へ。(5) `page.goto` で編集画面へ。(6) `page.reload`（F5）。
- 期待・判定：(4)〜(6) のそれぞれで、`--fta-cache-probe-components` が `"v2"`、`--fta-cache-probe-edit` が `"v1"`。サーバーの記録で (4) の `components.css` が 200（`If-None-Match` に旧版の ETag）、`edit.css` と JS が 304。コンソールのエラーなし。
- 証跡：サーバーの記録（JSON lines）、計算値の記録、失敗時の trace。必須。分析一覧・新規作成の画面でも同じ形で `list.css`・`new.css` を確かめる（パラメータ化）。

**C-02 下位の JavaScript モジュールだけの更新**
- 目的：入口の JavaScript が同じでも、更新された import 先が実行されることを確かめる。
- 入力：`pages/edit/factor-source.js`（深さ3）、`common/dom.js`（共通、複数の経路から import される）、`pages/edit/judgement.js` に試験用の印 `v1`。
- 手順：C-01 と同じ。(3) で印を `v2` にするのは下位のモジュールだけ（`edit.js`・`boot.js` は変えない）。
- 期待・判定：`globalThis.__ftaCacheProbe` の3件が `"v2"`、`edit.js`・`boot.js` は 304、変えたモジュールは 200。画面の動作の確認として、評価のボタンを押して保存の通知が出ること（`judgement.js` の処理）、インスペクタで詳細が表示されること（`factor-source.js`）。`page.evaluate` の中で `import('/static/…')` を使って値を読まない（読むと試験自身が要求を出すため）。必須。

**C-03 HTML の取得**：C-01 の各段階で、サーバーの記録に HTML（`/analyses/{id}`、`/`）の GET 200 が段階ごとにあること。必須。

**C-04 従来の方式からの移行**
- 目的：導入前の応答が残った状態から、定義した操作（M-3）で移行し、その後は通常の操作で更新が反映されることを確かめる。
- 前提：1つのコンテキスト、同じオリジン。`policy=baseline`（調査対象 SHA の配信）で開始。
- 入力：全資産に印 `v1`（時刻は10日前）。
- 手順：(1) `baseline` で一覧・新規作成・編集の3画面を開き、もう一度移って静的ファイルの要求がないことを確かめる（旧版が保存されている）。(2) `policy=app` に切り替え、CSS 1件と下位の JS 1件を `v2` にする。(3) 通常の画面遷移と F5 で3画面を開く（**観察**：`v1` のままであることを記録する。N-6 のとおりで、合否の対象ではない）。(4) 3画面でそれぞれ強制の再読み込み（`Page.reload`、`ignoreCache: true`）を1回。(5) 同じ2件を `v3` にする。(6) 通常の画面遷移・`goto`・F5 で3画面を開く。
- 期待・判定：(4) の後に全38件が `Cache-Control: no-cache` で取得されている（サーバーの記録）。(6) で印が `v3`、変えた2件は 200（`If-None-Match` あり）、ほかは 304。**判定は (6)（移行の後の通常の操作）で行い、(4) の結果を更新の反映の根拠にしない。**
- 証跡：段階ごとのサーバーの記録と計算値。必須。

**C-05 検出力の確認（ブラウザ）**：C-01 の手順を (a) `policy=baseline`、(b) `policy=nocache-only`（同じ秒の更新）で行い、(a) では (4) で要求がなく `v1` のまま、(b) では 304 で `v1` のままになることを確かめる。期待どおりに古い資産を検出できなければ、そのブラウザの版では C-01 などの陽性の試験の意味を再評価する（合格扱いにしない）。作った条件は 10/22 の根本原因の再現とは扱わない。必須。

**C-06 境界条件**：`policy=app` で、(a) 同じ秒の中の更新、(b) 古い時刻への置換（旧版より前の時刻の新版）を C-01 の手順で行い、通常の画面遷移で新版が使われること（サーバーの記録が 200）。時刻を保持した同じサイズの置換は H-04 で扱い、ブラウザでは必須にしない（サーバーの判定だけで決まり、ブラウザは同じ要求を送るため）。必須。

**C-07 生成中の評価のボタン（代表の画面の動作）**
- 目的：CSS の更新が、生成中の操作制限の見た目に実際に効くことを確かめる（10/22 に問題になった表示。**10/22 の再現ではない**）。
- 入力：旧版の `components.css` は `.ui-judgement__option:disabled` の規則を除いたもの（時刻は10日前）、新版は現行の内容。スタブは `{"mode": "delay", "delay_seconds": 5}`。
- 手順：旧版で編集画面を開き、もう一度移って 304 を確かめた後、新版にして通常の画面遷移で編集画面へ。生成を始め、生成中の評価のボタンを調べる。
- 期待・判定：生成中に `:disabled` の評価のボタンすべてが `opacity 0.55`・`cursor not-allowed`、クリックで評価が変わらない。終了後に `opacity 1`・`pointer`、評価を変えて保存できる。サーバーの記録で `components.css` が 200。必須。

**C-08 履歴の移動・BFCache の観察**：(a) Playwright の既定（BFCache 無効）で、更新の後に戻るを行い、どの版が使われたかを記録する。(b) `--disable-back-forward-cache` を外したブラウザで、更新の後に戻ると BFCache から復元され（`pageshow` の `persisted`）、以前の版のまま動くことを記録する。いずれも N-2・N-3 の確認で、合否に含めない（記録のみ）。既存の E-G12 の実 BFCache の試験は R-02 で必須として扱う。

**W-01 Windows での応答の確認**
- 前提：実装の PR の受入候補 SHA、手順書 第5.1節と同じスタブ（新しい作業フォルダ・試験 DB、ポート 8001、`mode=delay`・20秒）。Chrome・Edge のそれぞれ。普段のプロファイルを使ってよいが、データの一括の消去はしない。DevTools の「キャッシュを無効にする」は外したまま。
- 手順：編集画面を開き、Network で `components.css`・`edit.js`・`pages/edit/factor-source.js` の Status・Size・応答ヘッダー（`Cache-Control`・ETag・`Content-Type`）と要求ヘッダー（`If-None-Match`・`If-Modified-Since`）を撮る。F5 の後にもう一度撮る（304 が見える）。
- 期待：`Cache-Control: no-cache`、`.js` が `text/javascript`、F5 の後は 304（または `(memory cache)`。304・メモリキャッシュ自体は不具合にしない）。画面が正常に動く。
- 証跡：画像、`chrome://version`・`edge://version` の画像（正式な版・チャンネル）、SHA と作業ツリーの状態の表示。必須。

**W-02 Windows の普段のプロファイルでの移行**
- 目的：導入前の応答が残っている可能性のある普段のプロファイルで、M-3 の操作で移行でき、その後の通常の操作で更新が反映されることを確かめる。
- 手順：(1) 導入前の SHA（例 `3ce7099`）で一度3画面を開いておく（普段の利用で既に開いていれば不要）。(2) 受入候補 SHA に切り替えて起動し、DevTools の Network（無効化は外す）を開いて3画面を通常に開き、`components.css` の Status・Size を記録する（観察）。(3) 3画面で Ctrl+F5 を1回ずつ。(4) 試験専用の一時コピーの作業ツリー（受入候補 SHA から作ったもの）で `components.css` に目印の規則（例：`:root{--fta-cache-probe:"w2"}`）を加え、サーバーを再起動する（同じポート）。(5) 通常の画面遷移と F5 で編集画面を開き、Console で `getComputedStyle(document.documentElement).getPropertyValue('--fta-cache-probe')` が `"w2"` であること、Network で `components.css` が 200 であることを撮る。(6) 一時コピーを削除する。
- 期待：(5) で `"w2"`・200。(2) の観察は合否に含めない。普段の作業ソースと利用者の DB は書き換えない。必須。

**W-03 次の実際の更新での観察**：導入後の最初の実際の更新（例：PR-7 の取り込み）で、Windows の普段のプロファイルの通常のウィンドウで、強制の再読み込み・消去をせずに、変更のあった CSS・JS が 200 で取得され画面に反映されたことを記録する。条件付き（その更新の確認の一部として行う）。

### 6.6 境界条件の扱い（まとめ）

- 同じ秒・同じサイズ・時刻の保持・古い時刻への置換は、利用者の更新の手順（作業ツリーの作成・切替、取り出し、コピー）で起こり得るため、**HTTP の試験（H-04）で必須**とし、ブラウザの再検証の形（`If-None-Match`＋`If-Modified-Since`）が実際に送られることを C-06 で確かめる。
- 稼働中のファイルの書き換えは、更新の手順の前提（第3.5節）で除き、試験の対象外とする。
- `If-Modified-Since` だけの要求の同じ秒の見落としは、ブラウザ以外の利用の前提として対象外とする（H-05 で判定の維持だけを確かめる）。

### 6.7 検出力の確認（対策を外した構成）

- HTTP：H-09（Starlette の `StaticFiles` そのもの）。
- ブラウザ：C-05（`policy=baseline` と `policy=nocache-only`）。C-04 の (3) の観察も、従来の応答が残ることを示す。
- これらは「この試験が古い資産の使用を検出できる」ことの確認であり、作った条件を 10/22 の根本原因の再現とは扱わない。

### 6.8 回帰の確認

| 対象 | 確認の仕方 |
|---|---|
| 通常の pytest | R-01。既存の件数と比べ、失敗 0。スキップは既存の理由（pwsh がない）だけ |
| 累積の必須 E2E | R-02。開発環境（同梱 Chromium）と Windows の Chrome・Edge（`run_browser_e2e.ps1` の Preflight・Full）。PR-6 時点の必須 ID 60項目と新しい ID のすべてが成功、スキップ・未実施 0。不合格の回は記録として残し、判定の条件を変えない |
| Windows の JavaScript の MIME | H-01 は開発環境の実行。Windows では R-02 の全 E2E（モジュールが実行されなければ失敗する）と W-01 の `Content-Type` で確かめる |
| 生成中の評価のボタンの無効の見た目と操作の抑止 | E-G04（R-02）と C-07 |
| 未保存の入力の離脱の確認・生成中の F5 | 既存の E-E10〜E-E13・E-G08 など（R-02）。F5 のブラウザ標準の確認は手順書 第5.2節の実操作を Chrome で1回（静的ファイルの再検証が増えても確認が出ること） |
| sessionStorage による生成ログ・画面の状態の保持 | 既存の E-G 系（`test_edit_generation_log.py`）・状態の復元の試験（R-02） |
| 実 BFCache と模擬のイベント | 実 BFCache は `test_edit_generation_leave.py` の `bfcache_page`（E-G08・E-G12）。模擬の `pageshow` の試験とは結果を分けて記録する |
| 外部への依存 | E-X01・T-01（R-01・R-02）。この改善で外部の資源を加えない |
| 要求の数 | 試験用サーバーの記録で、編集画面の再訪の要求の件数（34件の条件付き要求）を記録する。`ERR_NO_BUFFER_SPACE` が出た場合は既存の扱い（失敗のまま記録、判定の条件を変えない）に従う |

### 6.9 Windows 実機の確認（範囲）

- 自動で行うもの：C-00〜C-07 と R-02 を `run_browser_e2e.ps1` の Full で Chrome・Edge のそれぞれで実行する（スクリプトは新しい必須 ID も実行する見込み。実装の PR で確かめ、必要なら変更する）。Playwright の一時プロフィールを使うため、普段のプロファイルには触れない。
- 実操作・目視で行うもの：W-01（Chrome・Edge）、W-02（Chrome は必須。Edge は普段のプロファイルで使っている場合）、R-02 の補足の F5 の確認（Chrome）。評価のボタンの見た目は C-07 の自動の確認があるため、W-02 の (5) で編集画面の生成中の画像を1枚撮る程度に絞る。
- 普段のプロファイルのデータの一括の消去は求めない。試験専用のプロファイルを使う場合も、旧版から新版までの一連の手順の間はキャッシュを保つ。

### 6.10 証跡

| 証跡 | 内容 |
|---|---|
| 対象 | 試験の SHA、作業ツリーの状態（`git status --porcelain` の結果が空）、Python と依存の版 |
| 環境 | OS の版、ブラウザの正式な版・チャンネル（`chrome://version`・`edge://version`、自動試験は `e2e-report.md` の記録） |
| 旧版・新版 | 一時コピーの各ファイルの印の値と SHA-256、時刻（`os.utime` の値） |
| 通信 | `/static` の要求ごとの URL・メソッド・状態（200・304 など）・`If-None-Match`・`If-Modified-Since`・応答の ETag・`Cache-Control`・`Content-Type`（試験用サーバーの記録）。HTML の要求の状態 |
| 使われた内容 | CSS の印の計算値・実際の規則の CSSOM と計算値、JavaScript の印の値と画面の動作の結果 |
| 結果 | 自動試験の成功・失敗・スキップ・未実施の件数と ID（`e2e-report.md`、pytest の出力）。実操作は画像と、利用者報告かどうかの区別 |

### 6.11 判定のルール

- 未実施・スキップの試験を合格にしない。成立条件（第6.2節）を満たさなかった試験は、結果にかかわらず不合格（または無効）とする。
- ブラウザの表示（Size 欄の `(memory cache)` など）だけで、サーバーの 304 や使われた内容を決めない。サーバーの記録と、適用された CSS・実行された JavaScript で判定する。
- ヘッダーが付いていることだけでは合格にしない（第7節）。

---

## 7. 受入条件（実装の PR に対して。今回は未実施）

| ID | 条件 |
|---|---|
| AC-1 | H-01〜H-09 が開発環境で成功（スキップ 0） |
| AC-2 | C-00〜C-07 が、開発環境の同梱 Chromium、Windows の Chrome、Windows の Edge のそれぞれで成功（スキップ・未実施 0）。C-05 で検出力が確認できている |
| AC-3 | **定義した更新の条件（第3.5節）で、通常の画面遷移・新規の読み込み・F5 のそれぞれにおいて、変更した CSS・下位の JavaScript の新版が実際に使われ**（C-01・C-02・C-07）、**定義した移行の操作（M-3）の後の通常の操作で新版が使われる**（C-04・W-02） |
| AC-4 | R-01・R-02 が成功（累積の必須 ID と新しい ID のすべて。Windows の Chrome・Edge を含む） |
| AC-5 | W-01・W-02 が OK（画像・記録あり。利用者報告の項目は区別して記録） |
| AC-6 | HTML・業務 API・出力・エラーの応答が現行どおり（H-06・H-07） |
| AC-7 | 実装計画・手順書・この文書に、実装と確認の結果、移行の操作（M-3）、残る制約（N-1〜N-6）を記録 |

C-08・W-03 は受入の条件に含めない（記録のみ・次の更新の時）。

---

## 8. 仕様・試験・受入の対応

| 仕様・保証 | 試験 | 受入 |
|---|---|---|
| SP-01・SP-02（`no-cache`） | H-01・H-02・H-03、W-01 | AC-1・AC-5 |
| SP-03（内容の ETag） | H-01・H-04・H-09 | AC-1 |
| SP-04（`If-None-Match` 優先） | H-03・H-04・H-09、C-06 | AC-1・AC-2 |
| SP-05（`If-Modified-Since` のみ） | H-05 | AC-1 |
| SP-06・SP-07（`Last-Modified`・`Content-Type`） | H-01、W-01、R-02 | AC-1・AC-4・AC-5 |
| SP-08（エラー） | H-06 | AC-6 |
| SP-09（HTML を変えない）・第5.5節の前提 | H-07、C-03 | AC-2・AC-6 |
| SP-10（API・出力） | H-07 | AC-6 |
| SP-11（URL・import・内容を変えない） | H-08、R-01 | AC-1・AC-4 |
| SP-12・M-1〜M-3（移行） | C-04、W-02 | AC-3・AC-5・AC-7 |
| G-1（更新の反映） | C-01・C-02・C-07、W-03（条件付き） | AC-3 |
| G-2（304・再利用） | H-03、C-01 の手順 (2) | AC-1・AC-2 |
| G-3（境界条件） | H-04、C-06 | AC-1・AC-2 |
| G-4（変えないもの） | H-01・H-06・H-07、R-01・R-02 | AC-4・AC-6 |
| N-2・N-3（保証しない） | C-08（記録のみ）、既存 E-G08・E-G12（R-02） | AC-4（既存の BFCache の動作を壊さない） |
| 試験の成立条件 | C-00、C-01〜C-07 の手順の確認、C-05・H-09 | AC-2 |

---

## 9. 実装範囲と他の作業との関係（計画）

### 9.1 PR の構成

キャッシュ制御は、PR-7（仕上げ）とは区別した**独立の実装 PR**（仮称 PR-C「静的ファイルの再検証」）とする。`feature/ui-redesign` から分岐し、`feature/ui-redesign` へマージする。PR-7 の受入条件・範囲は変えない。

### 9.2 変更予定のファイル

| ファイル | 変更 |
|---|---|
| `app/static_files.py`（新規） | `StaticFiles` のサブクラス（SP-01〜SP-08） |
| `app/main.py` | `/static` のマウントをサブクラスに替える（1行と import）。`mimetypes` の固定は維持 |
| `tests/test_static_cache.py`（新規） | H-01〜H-09 |
| `tests/test_ui_templates.py` | 既存の MIME の試験との重複を整理する場合だけ（変えなくてもよい） |
| `tests/e2e/stub_server.py` | 試験専用の `FTA_E2E_STATIC_DIR`・`FTA_E2E_STATIC_LOG`・`static_control.json` の配信方式の切替（第6.3節）。既定の動作（未設定時）は変えない |
| `tests/e2e/test_static_cache.py`（新規） | C-00〜C-08 と専用のサーバーの fixture |
| `tests/e2e/acceptance.py` | 新しい必須 ID の追加 |
| `tests/e2e/README.md`、`docs/manual-check-pr<N>.md`（新規）、実装計画、この文書 | 実行方法、Windows の手順（W-01・W-02）、結果 |
| `scripts/run_browser_e2e.ps1` | 変更しない見込み（Full が新しい必須 ID も実行することを確かめる） |

変えないもの：テンプレート、CSS・JavaScript の内容、DB スキーマ、業務 API の契約、生成プロンプト、LangGraph、Quality Gate、`requirements*.txt`（Starlette の版を含む）。Service Worker・CDN・ビルド基盤は導入しない。

### 9.3 実施の順序

1. この計画の承認（第12節の判断）。
2. PR-C の実装と開発環境の自動確認（R-01・R-02・H・C）。
3. Windows の自動確認（Chrome・Edge の Preflight・Full）と実操作（W-01・W-02）。
4. 受入・マージ。
5. PR-7 に着手。PR-7 は旧 CSS・JS の削除や favicon の追加で静的ファイルを変えるため、PR-C を先に入れると、PR-7 の取り込みが新しい方式での最初の実際の更新になり、W-03 を PR-7 の確認と合わせて行える。PR-7 の後に PR-C を行うことも可能（その場合、PR-7 の更新は従来の方式で配られる）。順序は利用者が判断する（第12節 判断3）。

PR-C は PR-7・PR-8 のどちらにも依存しない。PR-7 が `favicon` を `/static` の下に置く場合、PR-C の規則が適用される（PR-7 の E2E の既知の例外の廃止とは独立）。

### 9.4 `ERR_NO_BUFFER_SPACE` との関係

`ERR_NO_BUFFER_SPACE`（Tcpip のイベント 4231）は別の課題のまま扱う。PR-C は再訪のたびの条件付き要求を増やす（編集画面で最大34件。現行は経験則の鮮度の間は要求なし）。E2E は各試験が新しいコンテキストで初回の読み込みが多いため影響は小さいと考えるが、確かめていない。PR-C の Windows の全 E2E で同じエラーが出た場合は、既存の扱い（既知の例外にせず失敗のまま記録、判定の条件を変えない）に従い、要求の数の記録（第6.8節）とあわせて報告する。

---

## 10. 導入と切り戻し

### 10.1 導入の手順（案）

1. 利用中のサーバーを止める。
2. PR-C を含む SHA を取り出す（作業ツリーの切替を含む）。
3. サーバーを起動する。
4. ブラウザで、未保存の入力がない状態で、分析一覧・新規作成・分析・編集（任意の分析）の3画面を開き、それぞれで **Ctrl+F5 を1回**行う（M-3）。キャッシュ・サイトデータの消去は不要。
5. 以後の更新は、第3.5節の手順（止める → 入れ替える → 起動する）で行い、追加の操作は要らない（G-1）。

### 10.2 導入後にブラウザに残るもの

- 導入の後に取得・再検証した静的ファイルの応答は、`Cache-Control: no-cache` と内容の ETag 付きで保存される。
- 手順4を行わなかった画面の資産は、導入前の応答（`Cache-Control` なし）のまま残り、M-2 (a) まで検証なしで使われ得る。

### 10.3 切り戻し

- 方法：実装計画 第9節と同じく、PR-C のマージコミットを `git revert -m 1` で戻す（強制 push はしない）。PR-C は他の PR から独立しているため単独で戻せる。利用環境では PR-C の前の SHA を取り出して再起動してもよい。
- コードを戻した後にブラウザに残るもの：PR-C の配信で保存された応答は `Cache-Control: no-cache` を持ったまま残る。戻した後のサーバー（Starlette のまま）への再検証では、ブラウザは内容の ETag と `Last-Modified` を送る。サーバーの ETag（時刻・サイズ）とは一致しないため、Starlette は `If-Modified-Since` で判定する：ファイルが同じ（時刻も同じ）なら 304（保存済みの `no-cache` は 304 では消えず残る。RFC 9111 第3.2節）、ファイルが新しい時刻で変わっていれば 200（`Cache-Control` なしの応答に置き換わり、経験則の鮮度に戻る）。
- 戻した後の注意：戻すと第2.7節の見落とし（古い時刻のファイルへの置換などで 304）と経験則の再利用が戻る。静的ファイルの内容も同時に古い版へ戻す場合（作成時刻の古い作業ツリーへの切替など）は、戻した後に3画面で Ctrl+F5 を1回ずつ行う。
- 戻しても、DB・sessionStorage・localStorage の内容には影響しない（この改善はそれらを変えない）。

### 10.4 切り戻しを判断する目安

静的ファイルが取得できない・`Content-Type` が変わってモジュールが実行されない、304 が返り続けて更新が反映されない、要求の増加で操作が目に見えて遅くなる、既存の必須 E2E が PR-C の変更によって不合格になる。

---

## 11. 今回行ったこと・行っていないこと

| 区分 | 内容 |
|---|---|
| 行った（確認） | 調査対象 SHA・PR の状態・後続の課題、`/static` の配信、テンプレートの参照、JavaScript の import の依存関係（全38件）、CSS の参照、Service Worker などの有無、ストレージの用途、Starlette 0.37.2 の ETag の生成と判定のコード、既存の試験・基盤・Windows の手順 |
| 行った（実測） | 一時作業ディレクトリ・一時 DB のスタブサーバーでの応答ヘッダーと条件付き要求（第2.6節・第2.7節）、Starlette 0.37.2 の境界条件（第2.7節） |
| 行った（予備実測） | 使い捨ての最小サーバーと Chromium 153（headless）での再利用・再検証・移行・履歴の移動（第2.8節、付録A）。アプリの実装・試験ではない |
| 行っていない | アプリ・テストのコードの変更、依存の更新、通常の pytest と累積の必須 E2E の実行（今回はアプリを変えていないため不要）、Windows の Chrome・Edge での確認、ディスクキャッシュ・普段のプロファイルでの確認、PR の作成・マージ |
| 未確認 | Windows の Chrome・Edge の経験則の鮮度・F5 の動き・履歴の移動での再利用、HTML が通常の画面遷移で毎回取得されること（実アプリでの記録。第5.5節）、内容のハッシュの計算の応答時間への影響、要求の増加と `ERR_NO_BUFFER_SPACE` の関係、10/22 の原因 |

---

## 12. 利用者の判断が必要な事項

| 判断 | 選択肢 | 推奨 |
|---|---|---|
| 判断1：方式 | (1) 案A+（第4.3節）、(2) 案A のまま（判定の補正なし。第5.4節の見落としを受け入れる）、(3) 別の案 | (1)。案A だけでは、作業ツリーの切替・切り戻し・同じ秒の更新で 304 の見落としが通常の読み込みのたびに起こり得る（第2.7節の実測、予備実測 B・C） |
| 判断2：従来のキャッシュからの移行 | (1) 導入時に3画面で Ctrl+F5 を1回ずつ行う案内（M-3）、(2) 即時の移行を必須とし、URL を変える方式（第4.1節 C）を加える | (1)。(2) はテンプレート・URL の検査・E2E の `import()` の書き換えを含む大きな変更で、導入の PR は静的ファイルの内容を変えないためリスクは限られる（M-4） |
| 判断3：時期・PR | (1) 独立の PR-C を PR-7 の前に行う、(2) PR-7 の後・PR-8 の前に行う、(3) PR-7 に含める | (1)。PR-7 の範囲と受入を変えず、PR-7 の取り込みを新しい方式の最初の実際の更新として観察できる（W-03） |
| 判断4：保証しない範囲の受け入れ | N-1〜N-6（開いている画面、BFCache・履歴の移動、Service Worker・拡張機能、更新の途中、導入前の応答） | 受け入れる。すでに開いている画面の自動の差し替えや強制の再読み込みは、未保存の入力を失うおそれがある |
| 判断5：Windows の実操作の範囲 | W-01（Chrome・Edge）、W-02（Chrome は必須、Edge は普段使う場合）、W-03（次の更新の時） | 第6.9節のとおり |

---

## 付録A 予備実測の方法（スクラッチ領域。リポジトリに入れていない）

- 環境：Linux、Python 3.12.3、スクラッチ領域の仮想環境（`requirements-dev.txt` の固定版。starlette 0.37.2、uvicorn 0.29.0、playwright 1.56.0）、Chromium 153.0.8010.12（`/opt/pw-browsers/chromium`、headless、`executable_path` で起動。Playwright の既定の起動引数で BFCache は無効）。
- サーバー：最小の Starlette アプリを uvicorn でスレッドに起動（`127.0.0.1` の空きポート）。`/` は `<link rel="stylesheet" href="/static/a.css">` と `<script type="module" src="/static/entry.js">` を返す HTML（検証子なし）。`entry.js` は `import {v} from './sub.js'`。`/static` は一時ディレクトリを配る `StaticFiles`、またはそのサブクラス（`file_response` で `Cache-Control: no-cache` を加え、`is_not_modified` で `If-None-Match` があればそれだけで判定）。ASGI の包みで、静的ファイルの要求ごとにパス・状態・`If-None-Match`・`If-Modified-Since` の有無・応答の `Cache-Control` を記録。
- 版の判定：CSS は `#p{--v:'<版>'}` の計算値、JavaScript は `sub.js` が設定する `window.SUBV`。
- 操作：1つのコンテキスト・1つのページで、`page.goto`・リンクのクリック・`page.reload` を行い、その間にサーバーのファイルを書き換え・`os.utime` で時刻を設定した。移行の手順4だけ CDP の `Page.reload`（`ignoreCache: true`）を使った。`page.route`・HAR・キャッシュの無効化は使っていない。
- 境界条件の HTTP の実測：Starlette 0.37.2 の `StaticFiles` を一時ディレクトリに向け、TestClient で旧版の ETag・`Last-Modified` を送った（第2.7節）。
- この方法は、実装の PR の C-xx の試験を作る際の参考にとどめ、その結果を試験の成功として流用しない。

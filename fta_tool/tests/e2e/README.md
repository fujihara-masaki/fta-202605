# 実ブラウザテスト（E2E）と UI 改修の必須受入検証

画面改修（[実装計画](../../docs/ui-redesign-implementation-plan.md) 第5.9.6節・第8.0節、J-26）の実ブラウザテストです。
Playwright で Chromium を動かし、本体のアプリ（FastAPI・Jinja2・JavaScript）を操作して確認します。

- **実LLMは呼びません。** テスト用サーバー（`stub_server.py`）が AI プロバイダをスタブに差し替え、実プロバイダの取得と外部への HTTP 通信を遮断して記録します。記録があればテストは失敗します。
- **利用者の DB は使いません。** テスト用サーバーは一時ディレクトリを作業ディレクトリにして起動し、DB（`fta_tool.db`）はその中に作られます（リポジトリ内では起動しません）。通常の pytest でも、アプリの DB エンジンは一時ディレクトリに向けます（`tests/conftest.py`）。親子関係に不整合があるデータ（PR-3、J-25）は、このテスト用の一時 DB にだけ直接書き込みます（`support.py` の `insert_node`・`set_parent`）。
- 各テストは画面寸法 1280×800 と 1440×900 の2通りで実行します（計画 第8.0節の基本寸法）。PR-7 の表示のテスト（E-V01〜E-V03・E-F01、`test_pr7_*.py`）は、これに加えて計画 第5.9.4節の想定寸法（1920×1080・1536×730・1280×620・1366×650・1093×500・1024×683・900×600）と、2026-10-28 の利用者環境の実測値（Chrome 1920×945・1536×756（DPR 1.25）・1280×630（DPR 1.5）、Edge 1530×731（DPR 1.25）・1275×609（DPR 1.5））で実行します（`acceptance.py` の `PR7_CASES`）。`--e2e-viewport-set pr7` を付けると、寸法を自分で選ばないすべてのテストを、基本寸法とこの12寸法で実行します（計画 第8.7節）。**寸法と devicePixelRatio の指定は、ブラウザの拡大や Windows の表示倍率の確認ではありません**（実際の拡大は `display_check.py`、下記）。PR3-LAYOUT は、これに加えて利用者環境の実測値（計画 第5.9.4節。Windows 11・1920×1080・表示倍率100%・ブラウザ最大化で測った `document.documentElement.clientWidth`×`clientHeight`：Chrome 1905×945、Edge 1912×914）の表示領域でも実行します。いずれも Linux の Chromium での自動確認で、実利用環境（Windows の Edge・Chrome、表示倍率）での確認（手動）の代わりにはなりません。
  PR3-LAYOUT は、要求した表示領域と、ブラウザで測った値（アプリの表示前の about:blank と、編集画面の表示後）を記録します。差を許容するのは chrome-1905x945 だけで、条件は下記「表示領域の差（2026-10-06）」のとおりです。
- 各テストの終了時に、ブラウザのコンソールエラー、ページの例外、アプリ以外への通信（E-X01）がないことを確認します。**例外はありません**（2026-10-03 から PR-6 まで除いていた favicon の 404 の既知の例外は、PR-7 で favicon を実装して廃止しました。下記「favicon」）。

## 準備

```bash
cd fta_tool
pip install -r requirements-dev.txt        # 本番用 requirements.txt ＋ playwright・pytest-playwright（版を固定）
python -m playwright install chromium      # Chromium を取得（初回のみ。Linux で依存ライブラリも入れる場合は --with-deps）
```

`requirements-dev.txt` の `playwright==1.56.0` は Chromium 141.0.7390.37 を使います。
Claude Code のリモート実行環境（Linux）では、このブラウザが `/opt/pw-browsers` に導入済みで、`PLAYWRIGHT_BROWSERS_PATH` が設定されているため `playwright install` は不要です。

## 実行方法

| 目的 | コマンド（`fta_tool/` で実行） | ブラウザ・Playwright がない場合 |
|---|---|---|
| 通常の開発 | `pytest` | E2E はスキップ（ほかのテストの結果は変わらない） |
| UI 改修の必須受入検証 | `pytest -m e2e --e2e-required --e2e-env "<実行環境の区分>" --e2e-report e2e-report.md` | **失敗**（スキップ・未実施は合格にしない） |
| インストール済みの Chrome での準備確認（下記） | `pytest -m e2e --e2e-preflight --browser chromium --browser-channel chrome --headed --e2e-report <新しいフォルダ>/e2e-report.md --basetemp <新しいフォルダ>/pytest-tmp --output <新しいフォルダ>/failures --screenshot only-on-failure --tracing retain-on-failure` | **失敗**（スキップ・0件も失敗。同梱の Chromium には切り替えない） |
| インストール済みの Chrome での必須受入検証 | 上の `--e2e-preflight` を `--e2e-required` に替える | **失敗** |

- `--e2e-required` の代わりに環境変数 `FTA_E2E_REQUIRED=1` でも必須受入検証になります。
- 固定版の Playwright が使うブラウザ（Chromium 141）を導入できない環境では、`--e2e-browser-executable=<Chromium の実行ファイル>` で別の Chromium を明示して使えます（PR-C のレビューで追加）。記録の「ブラウザの channel（指定）」「起動したブラウザ」「ブラウザの実行ファイル」に、指定した実行ファイルであることと、その版・パスが書かれます。所定のブラウザでの結果の代わりにはなりません。`--browser-channel` とは同時に使えません。`--e2e-env` の代わりに `FTA_E2E_ENV` も使えます。
- 必須受入検証では、`acceptance.py` の `REQUIRED_IDS`（PR-7 時点の累積：E-L01〜E-L08、E-X01、E-N01〜E-N06、PR1-BASE-*、PR1-STUB、PR2-IME、PR2-NO-SAMPLES、E-E01〜E-E09、E-E19、PR3-LEGACY-OPS、PR3-LEGACY-NOTIFY、PR3-LAYOUT、PR3-DELETE-SCOPE、PR3-GEN-PARENTS、PR-4 で追加した E-E10〜E-E13・E-E20・PR4-LAYOUT、PR-5 で追加した E-E14〜E-E18・PR5-LAYOUT、PR-6 で追加した E-G01〜E-G12、PR-C で追加した C-00〜C-07、PR-7 で追加した E-K01〜E-K03・E-V01〜E-V03・E-F01。計 75 項目。重複・欠落は `tests/test_e2e_infrastructure.py` が検査する）の各項目について、対応するテストがすべて実行されて成功することを求めます。スキップしたテストは失敗として報告し、`-k` などで実行しなかった項目は「未実施」として失敗にします。PR1-COMPAT-NEW（移行前の新規作成画面の互換確認）は PR-2 で E-N01〜E-N06 に、PR1-COMPAT-EDIT（移行前の分析編集画面の互換確認）は PR-3 で E-E01〜 と PR3-LEGACY-OPS に置き換えました。
- テンプレートの構造テスト（T-01〜T-04、`tests/test_ui_templates.py`）と不正な親子関係の区分・削除範囲のテスト（T-07、`tests/test_node_integrity.py`。テストごとの一時 DB）は通常の pytest で実行します。必須受入検証では、通常の pytest と E2E の両方の結果を記録してください。
- PR-7 のオプション：`--e2e-viewport-set pr7`（上記。記録の「寸法の組」に書く。指定しなければ base で、記録に「全テストの全寸法での実行は未実施」と書く）、`--e2e-screens <フォルダ>`（PR-7 の表示のテストが、目視のレビュー用の画面を保存する。記録の「目視のレビュー用の画面」に一覧。判定には含めない）。
- 失敗の調査には pytest-playwright のオプションが使えます：`--headed`（画面を表示）、`--slowmo 200`、`--screenshot only-on-failure --tracing retain-on-failure --output <絶対パス>`。
- **`--output` には、新しいフォルダを指定してください。** pytest-playwright 0.7.1 は、開始時に `--output`（既定は実行したフォルダの `test-results`）を削除します。pytest の `--basetemp` も、開始時に中身を消します。どちらにも、過去の記録や手動確認のフォルダを指定しないでください。
- ブラウザのコンソールのエラー、ページの例外、アプリ以外への通信は、テストの終わり（テスト本体の失敗として）と後片付けの両方で確認します。テスト本体の失敗にするのは、pytest-playwright が失敗したテストの画面と trace だけを残すためです。記録の備考には、エラーの文と、その出どころの URL を書きます。
- **favicon（PR-7）**：全画面が `base.html` で `/static/favicon.svg`（`type="image/svg+xml"`）を宣言します。宣言があるため、ブラウザは `/favicon.ico` を要求しません（アプリは `/favicon.ico` に応答しない。業務 API は変えていない）。favicon は `/static` の静的ファイルとして PR-C と同じキャッシュ制御（`no-cache`、内容の ETag）で配信されます（`tests/test_static_cache.py` の H-01・H-02）。2026-10-03 の利用者の判断で除いていた「ブラウザ自身の `/favicon.ico` の 404」の既知の例外（`support.py` の `FAVICON_404_TEXT`、CDP の記録との照合、記録の「既知の例外として除いたコンソールのエラー」）は廃止しました。`/favicon.ico` を含むどの 404 も、ほかのコンソールのエラーと同じく失敗です（`test_console_check.py`：実ブラウザで7件の 404 がすべて失敗の対象になり、アプリの favicon は読み込める。`tests/test_e2e_infrastructure.py`：例外の名前が残っていない、記録に「コンソールのエラーの例外：なし」、全画面が favicon を宣言し 200 で返る）。E-X01 の `test_E_X01_every_screen_has_the_apps_own_icon` は、3画面で favicon の宣言・200・`no-cache` と、`/favicon.ico` を要求しないことを確かめます。

- 表示領域の差（2026-10-06）：Windows の Chrome での準備確認（`766200a`）で、PR3-LAYOUT の chrome-1905x945 だけが、要求 1905×945 に対し `clientWidth`×`clientHeight` 1906×946 で失敗しました（アプリの表示前の about:blank から 1906×946）。この開発環境（Linux）で、ブラウザの表示倍率を 1.25 にした模擬（`--force-device-scale-factor=1.25`。記録用の一時的な起動で、テストの設定ではない）で同じ値になります。1905 CSS px は 1.25 倍で 2381.25 物理画素になり、ブラウザが整数の画素に切り上げるため、表示領域が 1905.6×945.6（visualViewport）になり、整数の `clientWidth`×`clientHeight` が 1906×946 になります。Playwright の `device_scale_factor`（1・1.25）では変わりません。1280×800・1440×900・1912×914 は 1.25 倍でも一致し、1.5 倍・1.75 倍では 1905×945 も一致します。**Windows で表示倍率が原因であることは確認していません**（記録の devicePixelRatio・visualViewport で確かめる）。
  要求の寸法をそのまま再現する方法は、ブラウザの表示倍率を 1 に固定する起動オプション（全テストの条件が変わり、利用者の表示倍率での確認でなくなる）か、Windows の表示倍率の変更（変更しない）しかないため採らず、利用者の指示（2026-10-06）による検証条件の限定変更として、次の場合だけ差を許容します（`support.py` の `judge_viewport`）：対象は chrome-1905x945 だけ（`acceptance.py` の `VIEWPORT_ALLOWED`）、実測が要求と同じか各軸 +1 CSS px まで大きい、その差がアプリの表示前からあり表示後も同じ、要求と実測の間（両端を含む）にレイアウトの境界（1280px、ペインの幅の変化が止まる幅など。`support.py` の `LAYOUT_BOUNDARIES`。編集画面のスタイルの表示領域に依存する規則が変わると `tests/test_e2e_infrastructure.py` が失敗する）がない。許容したときも、ページ全体の横スクロール、ペインの収まり、主要な操作の表示と被覆の検査は、実測の寸法を基準に最後まで行います。1280×800 と edge-1912x914 は一致が必要です。許容しない差（表示後に変わった、+2 以上や小さい、境界を跨ぐ、対象外のケース）と、ペインのはみ出し・ページの横スクロール・操作の被覆や非表示が検出されることを、`test_the_size_check_refuses_what_it_must_not_tolerate`・`test_the_layout_check_catches_what_does_not_fit` で確かめています。
- 画面を表示して実行すると（`--headed`。同梱の Chromium でも同じ）、ブラウザはページの favicon を自動で要求します。PR-6 までは、アプリに favicon がないため `/favicon.ico` が 404 になり、2026-10-03 から既知の例外として除いていました（計画書 第14.3節）。PR-7 からは `/static/favicon.svg` が 200 で返り、例外はありません（上の「favicon」）。

## 記録

`--e2e-report <パス>` を付けると、PR に貼れる Markdown の記録を書き出します（パスは実行したディレクトリからの相対パス）。
記録には、実行日時、開始・終了（ローカル時刻）と所要時間、実行環境の区分（開発環境・利用者環境・検証環境・CI の別。Windows 用スクリプトは区分と実際の OS を書く）、OS、Python、Playwright の版、ブラウザと版、指定した channel と実際に起動したブラウザ（作成元・版・実行ファイル・プロフィール。起動できなかった場合はその理由）、headed／headless と slowmo、対象コミット（未コミットの変更の有無）、実行コマンド、コード側の `.env` の有無、テスト用サーバー（AI: e2e-stub、URL、一時 DB の作業フォルダ、ログ）、失敗時の証跡の設定（画面・trace と保存先。設定で、ファイルが残ったことは示さない）、画面寸法、結果の件数（成功・失敗・スキップ・未実施）と判定、受入項目ごと・テストごとの結果（失敗はエラーの文）、失敗したテストの証跡（実際に残ったファイルと、画面を撮れなかった理由）、PR3-LAYOUT の画面寸法の要求と実測（表示前・表示後の `clientWidth`×`clientHeight`・`innerWidth`×`innerHeight`・visualViewport・devicePixelRatio・`scrollWidth`×`scrollHeight` と、一致・許容した差・許容しない差の判定）、コンソールのエラーの例外（PR-7 から「なし」）、寸法の組（`--e2e-viewport-set`）、PR-7 の表示領域の記録（テストごとの寸法の出所・要求の寸法と DPR・実測・レイアウト・描画に使われたフォント）と目視のレビュー用の画面の一覧が入ります。
失敗したテストでは、ページの後片付けの初めに画面（`page-at-failure.png`）を撮ります。pytest-playwright の画面（`test-failed-1.png`）は撮れなかったときに理由を残さないため、撮れなかったときの理由をこちらで記録します（例：画面の遷移が終わらないままのページでは `Page.screenshot` が 5 秒で時間切れになる。この開発環境で確かめた）。
記録にはローカルのパス（ユーザー名を含むことがある）が入ります。GitHub などに貼る前に確認してください。
端末にも同じ要約（「実ブラウザテスト（E2E）の受入記録」）が表示されます。

## 実行場所（PR-1 で確定）

必須の E2E は、実行できる開発環境・検証環境・CI のいずれかで行います（計画 第5.9.6節。利用者本人の PC での実行は必須にしない）。
PR-1 では、Claude Code のリモート実行環境（Linux、Python 3.11、上記の Playwright と Chromium の headless shell）を実行場所とし、上記の手順で実行しました。
Windows の開発環境でも同じ手順で実行できます（`pip install -r requirements-dev.txt` と `python -m playwright install chromium` の後に同じコマンド）。
2026-10-03 から、PR-3 の Google Chrome での確認は、利用者の Windows PC のインストール済みの Chrome Stable でこの E2E を実行し、少数の目視確認を加える方式です（Edge は手動で確認済み。手順書 第11〜13節）。この場合は `playwright install` を使わず、自動確認専用の venv に `requirements-dev.txt` の固定版だけを入れます。

**実利用環境での手動確認は別に行います。** 利用者の Windows 環境での Edge・Chrome、表示倍率、日本語入力（変換確定の Enter）、主要操作の確認は、この E2E の成功では代替しません（計画 第5.7節・第8.1節の手動確認）。

## ファイル

| ファイル | 内容 |
|---|---|
| `conftest.py` | テスト用サーバー（セッションで1回起動）、テストごとの DB とスタブの初期化、画面寸法（`display_case`：寸法と DPR。`--e2e-viewport-set` は `tests/conftest.py` の `pytest_generate_tests`）、ブラウザ起動（channel、起動したブラウザの記録、起動できないときの案内）、ページの監視（テストの終わりと後片付け）、Windows での失敗時の保存先の名前、失敗したテストの画面（撮れなかった理由の記録） |
| `stub_server.py` | 本体アプリをスタブの AI プロバイダで起動する（`python -m tests.e2e.stub_server --port N`、作業ディレクトリは `FTA_E2E_WORKDIR`）。スタブの動作は `FTA_E2E_STUB_MODE` またはテストが書く `stub_control.json`（`create`・`delay`・`no_candidates`・`error`、PR-6 で `warning`（品質警告付きの作成）・`all_excluded`（全候補除外）と、親ごとに区分を変える `by_parent` を追加。PR-6 の手順書は、実操作・目視の遅延と部分失敗にも同じスタブを使う）。編集画面の親子関係の確認への障害の注入も同じファイルで指定する（`"integrity": "lookup_error"`：確認用の問い合わせが失敗する、`"integrity_scope_limit": N`：削除範囲の走査を N 件で打ち切る。データは変えない）。診断のときだけ、`FTA_E2E_ACCESS_LOG` のファイルに要求ごとの受信・応答の開始と終了・相手の切断を書く（メソッド・パス・時刻・User-Agent の種類・接続元のポート番号だけ。クエリ・ヘッダー・本文は書かない。テストでは使わない） |
| `support.py` | サーバーの操作（既存 API でのデータ作成、DB の参照、テスト用 DB への不整合データの直接書き込み、`stub_control.json` の変更）、ページの監視（コンソールのエラー・ページの例外・外部への通信。例外なし）、ダイアログの記録、画面の保存（撮れなかった理由を返す） |
| `diagnose_navigation.py` | 最初の画面遷移の診断（テストではない。合否は判定しない）。新しい一時サーバーの同じ URL を、Python（httpx）・Playwright のブラウザ（最小の構成とテストと同じ構成。止まるときはサンドボックスありの起動も）・Playwright を使わない起動で開き、サーバーの記録とブラウザの NetLog の要約を `diagnose-report.md` に書く。Windows の設定は読み取るだけ（プロキシの設定の有無とポリシーの名前。値は書かない） |
| `edit_helpers.py` | 分析編集画面のテストで共通の要素の指定と確認（選択の一致、共通の通知の指定など） |
| `acceptance.py` | 必須受入検証（スキップの失敗扱い、未実施の検出、必須項目の一覧、記録の出力） |
| `test_list_page.py` | 分析一覧（E-L01〜E-L08） |
| `test_new_analysis_page.py` | 新規分析作成（E-N01〜E-N06、PR2-IME、PR2-NO-SAMPLES）。PR2-NO-SAMPLES はサンプルの設定ファイルがない状態の2つ目のテスト用サーバーで確認する |
| `test_foundation.py` | 外部通信（E-X01）、通知・保存領域・アクセシビリティ・スタブの確認（PR1-BASE-*、PR1-STUB） |
| `test_edit_page.py` | 分析編集の骨格（E-E01〜E-E06、E-E09、PR3-LAYOUT） |
| `test_edit_refresh.py` | 部分更新（E-E07、E-E19） |
| `test_edit_integrity.py` | 不正な親子関係の表示（E-E08）、削除範囲（PR3-DELETE-SCOPE）、生成・追加の親（PR3-GEN-PARENTS） |
| `test_legacy_compat.py` | 分析編集で暫定的に旧処理（app.js）を使う操作と、その通知（PR3-LEGACY-OPS、PR3-LEGACY-NOTIFY） |
| `test_console_check.py` | ページの確認がコンソールのエラーを除かないことを、実ブラウザで確かめる（同じサーバーの script・CSS・画像・API・クエリ付き・ページが読む `/favicon.ico` の 404 がすべて失敗の対象。アプリの favicon はエラーなく読める）。受入 ID はなし（すべての E2E が通る確認そのものの検査） |
| `layout_checks.py` | PR-7 の表示の判定（実際の DOM の位置・寸法・可視性・最前面の要素）：`reach()`（表示領域の中・中心と4点の最前面・ページを横にスクロールしない。保存・取消とダイアログのボタンは `scroll=False` でスクロールなし。ほかはペイン（長い一覧）をスクロールして届けばよい。通知に覆われていればスクロールの有無にかかわらず失敗（2026-10-29 の修正で、通知の上へスクロールして判定する処理は廃止）。どれで届いたか（表示のまま／ペインのスクロール／届かない）を記録の「主要な操作への到達」に分けて書く）、`focus_shown()`・`tab_walk()`（実際のキーの後、テストがスクロールせずに、フォーカスのある操作と枠が見える範囲の中にあり最前面。押すたびに通知が出ていることも確かめる）、ページ・ペインの横スクロール、レイアウト（3ペイン／折りたたみ）、重なり |
| `test_pr7_viewports.py` | PR-7 の表示（E-V01〜E-V03）：想定寸法・実測値の寸法での編集画面のレイアウトと主要な操作、構造ナビの開閉、生成中の状態表示・生成ログ・通知・保存失敗、ダイアログ、一覧・新規作成。検査が不具合を検出すること（最小幅 1100px の復活、1280px 未満の3ペイン、通知のインスペクタへの重なり、保存・取消の固定の解除、覆い、インスペクタのはみ出し） |
| `test_pr7_keyboard.py` | PR-7 のキーボード・フォーカス・読み上げ（E-K01〜E-K03）：Tab・Enter・Space・矢印・Esc だけの代表シナリオ（基本寸法と Edge 150% の 1275×609）、ダイアログの初期フォーカス・背後へ出ない・Esc・戻り先、読み上げ領域への書き込み（DOM。スクリーンリーダーの読み上げではない）。モーダルでないダイアログ・読み上げ領域がない場合を検出すること |
| `test_pr7_fonts.py` | PR-7 の代替フォント（E-F01）：BIZ UDPGothic を除いた3種で見出し・ボタンが欠けない・重ならない、主要な操作に届く。描画に使われたフォントを CDP で記録 |
| `test_pr7_focus.py` | PR-7 の 2026-10-29 の修正（計画 第8.7節の条件2・3・4、E-V01・E-V03・E-K01）：保存・取消が要因の編集欄の出た時点から（入力の前・入力中・保存の成功と失敗の後・要因の切替と部分更新の後）スクロールなしで見える。通知（消えないエラーを含む複数）の表示中の Tab・Shift+Tab・矢印でフォーカスが見えて覆われない。フォーカスの後に出た通知が何も隠さず、フォーカス・入力・選択・未保存の状態を変えない（作業エリア・インスペクタ・一覧） |
| `display_check.py` | PR-7 の実機の補助の道具（テストではない）：インストール済みの Chrome・Edge を最大化・表示領域の指定なし・一時プロフィールで起動し、利用者が Ctrl と + で拡大を変えるのを `devicePixelRatio` で検出して、各拡大で E-V01〜E-V03 と同じ確認を実際のウィンドウで行い、画面と実測を記録する。`--ime` で Microsoft IME の入力を判定する（入力欄の準備の時点から要求を記録し、変換の確定の Enter で送らないこと、次の Enter で1回だけ送って応答が成功し、テスト用 DB に確定した文字が保存されたこと。絞り込みは要求を送らず、件数と行が確定した文字に合うこと）。Windows では `scripts/run_display_check.ps1`（[手順](../../docs/manual-check-pr7.md)） |
| `test_display_check.py` | `display_check.py` の自己確認（開発用の `--simulate-zoom`：拡大を寸法と DPR で模す。実際の拡大の確認ではない。この実行では IME の判定は行わない）。想定を下回る寸法を「参考・利用者の判断」と記録すること。IME の判定（`judge_ime`）を、ページの中で合成した変換のイベントと Enter で試験する（確定の Enter での送信は確定の前・同時・後のどれでも NG、次の Enter で送らない・保存に失敗する・絞り込みが反映されない・絞り込みで要求を送ると NG）。**確認ツールの判定ロジックの検査で、Microsoft IME の確認ではない** |
| `test_edit_generation.py` | 生成（PR-6）：一次の生成と自動保存（E-G01）、二次・三次の対象と親ごとの要求（E-G02）、8つの結果区分・品質警告・部分失敗・通知（E-G03）、生成後の部分更新（E-G05）、追加生成（E-G07） |
| `test_edit_generation_run.py` | 生成中（PR-6）：操作の制限と削除の3か所（E-G04）、生成中のブラウザ離脱の確認（E-G08）、生成準備の待機・失敗・取りやめ・10秒の説明（E-G09）、詳細の取得待ちと再取得（E-G10）、保存の抑止と2択（E-G11）、各終了経路での制限の解除（E-G12） |
| `test_edit_generation_leave.py` | 生成中にページを離れて戻った場合（PR-6 レビュー R7、E-G08・E-G12）：実行中・準備中・反映中・生成していないページ、再開・再送しないこと、遅れて届いた応答が後の生成と選択を変えないこと、戻った後の離脱確認。`_simulated` は pagehide・pageshow を画面に送る模擬（バックフォワードキャッシュではない）、`_real_bfcache` は実際に別のアドレスへ移動して戻り `pageshow.persisted === true` を確かめる（Playwright の `--disable-back-forward-cache` を外した専用のブラウザ。チャンネルの指定がなくヘッドレスなら Playwright のフル Chromium） |
| `test_edit_generation_log.py` | 生成ログの保持（PR-6、E-G06）：sessionStorage の内容、再読み込み後の復元、別の分析と別タブ（開き方ごと）、閉じる、保存領域が使えない場合 |
| `test_edit_manual_items.py` | PR-3 の手動確認の項目のうち、それまでの E2E が確かめていなかった部分（2026-10-03。実際の2つのタブでの評価の変更後の復帰、未評価に戻す、No・未評価の絞り込み、一次要因の削除後の選択、不整合の全区分の追加の無効と理由、各ペインのスクロール、生成中の親ごとの表示）。対応表は手順書の第11節 |
| `test_static_cache.py` | 静的ファイルのキャッシュ制御（PR-C、C-00〜C-07。[計画](../../docs/static-assets-cache-control-plan.md) 第6節）。試験ごとに専用のテスト用サーバーを起動し、`/static` を一時コピーから配り（`FTA_E2E_STATIC_DIR`。リポジトリのファイルは変えない）、全要求をキャッシュのヘッダーと送った本文の SHA-256 付きで記録する（`FTA_E2E_STATIC_LOG`）。1つのコンテキスト・1つのオリジンの中で、リンク・goto・F5 の各操作の直前にまだ取得していない版へ変え（更新ステップ）、旧 ETag の送信・200・新しい本文・ページが使った版と、変えていないファイルの 304、HTML の要求の到達（C-03）を判定する。`static_control.json` の `baseline`（PR-C の前の配信）・`nocache-only`（案A だけ）で、検出力（C-05）と移行（C-04）を確かめる。通信の差し替え・キャッシュの無効化は使わない（C-00 が検査する。強制の再読み込みは C-04 の移行の手順だけ） |
| `cache_manual_check.py` | W-02（普段のプロフィールでの実際の Ctrl+F5・F5）の道具（テストではない）。準備・版の変更・停止と同じポートでの起動・要求とページの報告の集計・判定・記録・後片付けを行い、利用者はキー操作だけを行う。ページの報告は、テスト用サーバーが確認のあいだだけ HTML に加えるスクリプトが、回の識別子を付けて送る（`FTA_E2E_PROBE_LOG`・`FTA_E2E_PROBE_RUN`。確認の前から保存された静的ファイルが使われても画面を検出できる）。手順1 は記録で、手順3 は編集画面の34件と名前で照合する。Windows では `scripts/run_cache_check.ps1` から実行する（[手順](../../docs/manual-check-pr-c.md)） |
| `test_cache_manual_check.py` | `cache_manual_check.py` の自己確認（キー操作は模擬：Ctrl+F5 は CDP の強制の再読み込み、F5 は `page.reload`）。初めてのプロフィール、道具の目印のない旧方式の保存が残ったプロフィール、同じプロフィールでの2回続けての実行で OK、手順3 の強制の再読み込みで NG。W-02 そのものではない |
| `static_assets.py` | 画面ごとの期待の静的ファイル（`test_static_cache.py` と `cache_manual_check.py` で共用） |
| `test_windows_tools.py` | W-02 のラッパー（`scripts/run_cache_check.ps1`）と PR-7 の `scripts/run_display_check.ps1` を、その PC の PowerShell ごと（Windows PowerShell 5.1、pwsh）に実行して確かめる（構文解析、誤った SHA での中止、W-02 は「未完了」の記録と終了コード）。Windows の準備確認に含む。`run_display_check.ps1` は構文解析と誤った SHA での中止だけで、道具を通常どおり起動して終えることは確かめない。PowerShell のない環境では試験を定義しない |

テスト基盤そのもの（準備確認、記録、起動失敗の案内、ポート、失敗時の保存先と実際に残った証跡、コンソールのエラーに例外がないこと、必須 ID の一覧、PR-7 の寸法）は `tests/test_e2e_infrastructure.py`、診断（サーバーの記録、NetLog の要約と伏せる情報、記録の分類）は `tests/test_diagnose_navigation.py`、Windows 用のスクリプト（実行前の確認、記録フォルダ、終了コード、実行環境の区分と OS、残っていたプロセスの記録、診断の実行）は `tests/test_run_browser_e2e_script.py` が確かめます（ブラウザは使いません）。

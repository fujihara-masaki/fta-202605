# 実ブラウザテスト（E2E）と UI 改修の必須受入検証

画面改修（[実装計画](../../docs/ui-redesign-implementation-plan.md) 第5.9.6節・第8.0節、J-26）の実ブラウザテストです。
Playwright で Chromium を動かし、本体のアプリ（FastAPI・Jinja2・JavaScript）を操作して確認します。

- **実LLMは呼びません。** テスト用サーバー（`stub_server.py`）が AI プロバイダをスタブに差し替え、実プロバイダの取得と外部への HTTP 通信を遮断して記録します。記録があればテストは失敗します。
- **利用者の DB は使いません。** テスト用サーバーは一時ディレクトリを作業ディレクトリにして起動し、DB（`fta_tool.db`）はその中に作られます（リポジトリ内では起動しません）。通常の pytest でも、アプリの DB エンジンは一時ディレクトリに向けます（`tests/conftest.py`）。親子関係に不整合があるデータ（PR-3、J-25）は、このテスト用の一時 DB にだけ直接書き込みます（`support.py` の `insert_node`・`set_parent`）。
- 各テストは画面寸法 1280×800 と 1440×900 の2通りで実行します（計画 第8.0節の基本寸法）。PR3-LAYOUT は、これに加えて利用者環境の実測値（計画 第5.9.4節。Windows 11・1920×1080・表示倍率100%・ブラウザ最大化で測った `document.documentElement.clientWidth`×`clientHeight`：Chrome 1905×945、Edge 1912×914）の表示領域でも実行します。いずれも Linux の Chromium での自動確認で、実利用環境（Windows の Edge・Chrome、表示倍率）での確認（手動）の代わりにはなりません。
- 各テストの終了時に、ブラウザのコンソールエラー、ページの例外、アプリ以外への通信（E-X01）がないことを確認します。

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

- `--e2e-required` の代わりに環境変数 `FTA_E2E_REQUIRED=1` でも必須受入検証になります。`--e2e-env` の代わりに `FTA_E2E_ENV` も使えます。
- 必須受入検証では、`acceptance.py` の `REQUIRED_IDS`（PR-3 時点：E-L01〜E-L08、E-X01、E-N01〜E-N06、PR1-BASE-*、PR1-STUB、PR2-IME、PR2-NO-SAMPLES、E-E01〜E-E09、E-E19、PR3-LEGACY-OPS、PR3-LEGACY-NOTIFY、PR3-LAYOUT、PR3-DELETE-SCOPE、PR3-GEN-PARENTS）の各項目について、対応するテストがすべて実行されて成功することを求めます。スキップしたテストは失敗として報告し、`-k` などで実行しなかった項目は「未実施」として失敗にします。PR1-COMPAT-NEW（移行前の新規作成画面の互換確認）は PR-2 で E-N01〜E-N06 に、PR1-COMPAT-EDIT（移行前の分析編集画面の互換確認）は PR-3 で E-E01〜 と PR3-LEGACY-OPS に置き換えました。
- テンプレートの構造テスト（T-01〜T-04、`tests/test_ui_templates.py`）と不正な親子関係の区分・削除範囲のテスト（T-07、`tests/test_node_integrity.py`。テストごとの一時 DB）は通常の pytest で実行します。必須受入検証では、通常の pytest と E2E の両方の結果を記録してください。
- 失敗の調査には pytest-playwright のオプションが使えます：`--headed`（画面を表示）、`--slowmo 200`、`--screenshot only-on-failure --tracing retain-on-failure --output <絶対パス>`。
- **`--output` には、新しいフォルダを指定してください。** pytest-playwright 0.7.1 は、開始時に `--output`（既定は実行したフォルダの `test-results`）を削除します。pytest の `--basetemp` も、開始時に中身を消します。どちらにも、過去の記録や手動確認のフォルダを指定しないでください。
- ブラウザのコンソールのエラー、ページの例外、アプリ以外への通信は、テストの終わり（テスト本体の失敗として）と後片付けの両方で確認します。テスト本体の失敗にするのは、pytest-playwright が失敗したテストの画面と trace だけを残すためです。記録の備考には、エラーの文と、その出どころの URL を書きます。

## インストール済みの Google Chrome・Microsoft Edge で実行する（2026-10-03）

`--browser chromium --browser-channel chrome`（Edge は `msedge`）で、Playwright 同梱の Chromium ではなく、インストール済みのブラウザを使います。
`playwright install chrome` などは使いません（Playwright の文書のとおり、既存のインストールを上書きするため）。

- Playwright は決まった場所（Windows では `%LOCALAPPDATA%`・`%ProgramFiles%`・`%ProgramFiles(x86)%` の `Google\Chrome\Application\chrome.exe` など）でブラウザを探します。見つからない・起動できない場合は、同梱の Chromium に切り替えずに失敗します（必須受入検証と準備確認では、スキップも失敗）。
- テストからテスト用サーバー（同じ PC の 127.0.0.1）への接続は、環境変数や Windows のシステム設定のプロキシを使いません（`httpx` の `trust_env=False`）。ブラウザも、同じ PC への接続にはプロキシを使いません。
- 起動のたびに一時プロフィール（`%TEMP%` の `playwright_chromiumdev_profile-…`）を作り、`--disable-extensions` などを付けて起動します。通常のプロフィール、ログイン状態、Cookie、拡張機能は使いません。企業のポリシー（レジストリ）は、プロフィールと関係なく適用されることがあります。
- `browser_type.name` は Chrome・Edge でも `chromium` です。記録には、指定した channel と、実際に起動したブラウザ（`chrome://version` の作成元・版・実行ファイル・プロフィール）を書きます。
- 準備確認：`--e2e-preflight` は、編集画面を開いて主要な要素を確かめる既存のテスト（`acceptance.py` の `PREFLIGHT_TESTS`：E-E01 の2件と PR3-LAYOUT、計7件）だけを実行します。ブラウザの起動、テスト用サーバー、テストデータ、終了までが成り立つかの確認で、**全必須 E2E の合格ではありません**。スキップ、0件、見つからないテストは失敗です。`--e2e-required` とは同時に使えません。
- Windows では `scripts/run_browser_e2e.ps1` で、初回準備（自動確認専用の venv）・準備確認・全必須 E2E を実行できます。手順は [manual-check-pr3.md](../../docs/manual-check-pr3.md) の第12節です。
- 画面を表示して実行すると（`--headed`。同梱の Chromium でも同じ）、ブラウザがページを最初に開いたときに `/favicon.ico` を自動で要求します。アプリに favicon がないため 404 になり、コンソールのエラーとして、テスト用サーバーごとの最初のテストが失敗します（同梱の headless shell は要求しません）。扱いは利用者の判断待ちです（計画書 第14.3節）。

## 記録

`--e2e-report <パス>` を付けると、PR に貼れる Markdown の記録を書き出します（パスは実行したディレクトリからの相対パス）。
記録には、実行日時、開始・終了（ローカル時刻）と所要時間、実行環境の区分（開発環境・検証環境・CI の別）、OS、Python、Playwright の版、ブラウザと版、指定した channel と実際に起動したブラウザ（作成元・版・実行ファイル・プロフィール。起動できなかった場合はその理由）、headed／headless と slowmo、対象コミット（未コミットの変更の有無）、実行コマンド、コード側の `.env` の有無、テスト用サーバー（AI: e2e-stub、URL、一時 DB の作業フォルダ、ログ）、失敗時の画面・trace の保存先、画面寸法、結果の件数（成功・失敗・スキップ・未実施）と判定、受入項目ごと・テストごとの結果（失敗はエラーの文）が入ります。
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
| `conftest.py` | テスト用サーバー（セッションで1回起動）、テストごとの DB とスタブの初期化、画面寸法、ブラウザ起動（channel、起動したブラウザの記録、起動できないときの案内）、ページの監視（テストの終わりと後片付け）、Windows での失敗時の保存先の名前 |
| `stub_server.py` | 本体アプリをスタブの AI プロバイダで起動する（`python -m tests.e2e.stub_server --port N`、作業ディレクトリは `FTA_E2E_WORKDIR`）。スタブの動作は `FTA_E2E_STUB_MODE` またはテストが書く `stub_control.json`（`create`・`delay`・`no_candidates`・`error`）。編集画面の親子関係の確認への障害の注入も同じファイルで指定する（`"integrity": "lookup_error"`：確認用の問い合わせが失敗する、`"integrity_scope_limit": N`：削除範囲の走査を N 件で打ち切る。データは変えない） |
| `support.py` | サーバーの操作（既存 API でのデータ作成、DB の参照、テスト用 DB への不整合データの直接書き込み、`stub_control.json` の変更）、ページの監視、ダイアログの記録 |
| `edit_helpers.py` | 分析編集画面のテストで共通の要素の指定と確認（選択の一致、共通の通知の指定など） |
| `acceptance.py` | 必須受入検証（スキップの失敗扱い、未実施の検出、必須項目の一覧、記録の出力） |
| `test_list_page.py` | 分析一覧（E-L01〜E-L08） |
| `test_new_analysis_page.py` | 新規分析作成（E-N01〜E-N06、PR2-IME、PR2-NO-SAMPLES）。PR2-NO-SAMPLES はサンプルの設定ファイルがない状態の2つ目のテスト用サーバーで確認する |
| `test_foundation.py` | 外部通信（E-X01）、通知・保存領域・アクセシビリティ・スタブの確認（PR1-BASE-*、PR1-STUB） |
| `test_edit_page.py` | 分析編集の骨格（E-E01〜E-E06、E-E09、PR3-LAYOUT） |
| `test_edit_refresh.py` | 部分更新（E-E07、E-E19） |
| `test_edit_integrity.py` | 不正な親子関係の表示（E-E08）、削除範囲（PR3-DELETE-SCOPE）、生成・追加の親（PR3-GEN-PARENTS） |
| `test_legacy_compat.py` | 分析編集で暫定的に旧処理（app.js）を使う操作と、その通知（PR3-LEGACY-OPS、PR3-LEGACY-NOTIFY） |
| `test_edit_manual_items.py` | PR-3 の手動確認の項目のうち、それまでの E2E が確かめていなかった部分（2026-10-03。実際の2つのタブでの評価の変更後の復帰、未評価に戻す、No・未評価の絞り込み、一次要因の削除後の選択、不整合の全区分の追加の無効と理由、各ペインのスクロール、生成中の親ごとの表示）。対応表は手順書の第11節 |

テスト基盤そのもの（準備確認、記録、起動失敗の案内、ポート、失敗時の保存先）は `tests/test_e2e_infrastructure.py`、Windows 用のスクリプトは `tests/test_run_browser_e2e_script.py` が確かめます（ブラウザは使いません）。

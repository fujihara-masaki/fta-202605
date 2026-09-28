# 実ブラウザテスト（E2E）と UI 改修の必須受入検証

画面改修（[実装計画](../../docs/ui-redesign-implementation-plan.md) 第5.9.6節・第8.0節、J-26）の実ブラウザテストです。
Playwright で Chromium を動かし、本体のアプリ（FastAPI・Jinja2・JavaScript）を操作して確認します。

- **実LLMは呼びません。** テスト用サーバー（`stub_server.py`）が AI プロバイダをスタブに差し替え、実プロバイダの取得と外部への HTTP 通信を遮断して記録します。記録があればテストは失敗します。
- **利用者の DB は使いません。** テスト用サーバーは一時ディレクトリを作業ディレクトリにして起動し、DB（`fta_tool.db`）はその中に作られます（リポジトリ内では起動しません）。通常の pytest でも、アプリの DB エンジンは一時ディレクトリに向けます（`tests/conftest.py`）。
- 各テストは画面寸法 1280×800 と 1440×900 の2通りで実行します（計画 第8.0節の基本寸法）。これは想定寸法での自動確認で、実利用環境の表示倍率・画面寸法の確認（手動）の代わりにはなりません。
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

- `--e2e-required` の代わりに環境変数 `FTA_E2E_REQUIRED=1` でも必須受入検証になります。`--e2e-env` の代わりに `FTA_E2E_ENV` も使えます。
- 必須受入検証では、`acceptance.py` の `REQUIRED_IDS`（PR-2 時点：E-L01〜E-L08、E-X01、E-N01〜E-N06、PR1-BASE-*、PR1-STUB、PR1-COMPAT-EDIT、PR2-IME、PR2-NO-SAMPLES）の各項目について、対応するテストがすべて実行されて成功することを求めます。スキップしたテストは失敗として報告し、`-k` などで実行しなかった項目は「未実施」として失敗にします。PR1-COMPAT-NEW（移行前の新規作成画面の互換確認）は、PR-2 で新規作成画面を移行したため E-N01〜E-N06 に置き換えました。
- テンプレートの構造テスト（T-01〜T-03、`tests/test_ui_templates.py`）は通常の pytest で実行します。必須受入検証では、通常の pytest と E2E の両方の結果を記録してください。
- 失敗の調査には pytest-playwright のオプションが使えます：`--headed`（画面を表示）、`--slowmo 200`、`--screenshot only-on-failure --tracing retain-on-failure --output <絶対パス>`。

## 記録

`--e2e-report <パス>` を付けると、PR に貼れる Markdown の記録を書き出します（パスは実行したディレクトリからの相対パス）。
記録には、実行日時、実行環境の区分（開発環境・検証環境・CI の別）、OS、Python、Playwright の版、ブラウザと版、対象コミット（未コミットの変更の有無）、実行コマンド、画面寸法、結果の件数（成功・失敗・スキップ・未実施）と判定、受入項目ごと・テストごとの結果が入ります。
端末にも同じ要約（「実ブラウザテスト（E2E）の受入記録」）が表示されます。

## 実行場所（PR-1 で確定）

必須の E2E は、実行できる開発環境・検証環境・CI のいずれかで行います（計画 第5.9.6節。利用者本人の PC での実行は必須にしない）。
PR-1 では、Claude Code のリモート実行環境（Linux、Python 3.11、上記の Playwright と Chromium の headless shell）を実行場所とし、上記の手順で実行しました。
Windows の開発環境でも同じ手順で実行できます（`pip install -r requirements-dev.txt` と `python -m playwright install chromium` の後に同じコマンド）。

**実利用環境での手動確認は別に行います。** 利用者の Windows 環境での Edge・Chrome、表示倍率、日本語入力（変換確定の Enter）、主要操作の確認は、この E2E の成功では代替しません（計画 第5.7節・第8.1節の手動確認）。

## ファイル

| ファイル | 内容 |
|---|---|
| `conftest.py` | テスト用サーバー（セッションで1回起動）、テストごとの DB とスタブの初期化、画面寸法、ブラウザ起動、ページの監視 |
| `stub_server.py` | 本体アプリをスタブの AI プロバイダで起動する（`python -m tests.e2e.stub_server --port N`、作業ディレクトリは `FTA_E2E_WORKDIR`）。スタブの動作は `FTA_E2E_STUB_MODE` またはテストが書く `stub_control.json`（`create`・`delay`・`no_candidates`・`error`） |
| `support.py` | サーバーの操作（既存 API でのデータ作成、DB の参照）、ページの監視、ダイアログの記録 |
| `acceptance.py` | 必須受入検証（スキップの失敗扱い、未実施の検出、必須項目の一覧、記録の出力） |
| `test_list_page.py` | 分析一覧（E-L01〜E-L08） |
| `test_new_analysis_page.py` | 新規分析作成（E-N01〜E-N06、PR2-IME、PR2-NO-SAMPLES）。PR2-NO-SAMPLES はサンプルの設定ファイルがない状態の2つ目のテスト用サーバーで確認する |
| `test_foundation.py` | 外部通信（E-X01）、通知・保存領域・アクセシビリティ・スタブの確認（PR1-BASE-*、PR1-STUB） |
| `test_legacy_compat.py` | 未移行の画面（分析編集）が引き続き使えることの確認（PR1-COMPAT-EDIT） |

# FTA分析支援ツール

FTA（フォルトツリー解析）を支援するWebアプリケーションです。AIによる要因候補の自動生成、作業ステップ・構造ナビ・インスペクタによる要因の評価と編集、JSON/CSV/Markdown形式でのエクスポートをサポートします。

## 機能

- **分析一覧**: 分析の一覧（表）、タイトルの行内の改名、出力、削除（要因数を示す確認ダイアログ）
- **新規分析作成**: 分析タイトル・頂上事象・AIへの参考情報の入力（2列）。デモ用サンプルのプレビューと転記
- **分析・編集画面**（作業ステップ ①頂上事象・参考情報 → ②一次要因 → ③二次要因 → ④三次要因 → ⑤確認・出力）
  - **構造ナビ**（左）：頂上事象から三次要因までの木。選んだ要因をすべての表示で同期
  - **作業エリア**（中央）：表示タブ「作業・ツリー・一覧表」、絞り込み、ステップごとの操作バー・生成ログ・作業リスト
  - **インスペクタ**（右）：選んだ要因の評価、詳細（タイトル・説明・メモ・直接要因評価・評価コメント・根拠・再発防止策）の編集と保存、子要因の追加、削除
- **AIによる要因生成**: 一次要因（頂上事象の下）と、Yes と評価した要因を親にした二次・三次要因の**通常生成**
- **追加生成**: 既存の要因と重複しないよう、一次要因全体または選んだ親1件の下にAIで追加
- **手動追加**: AIを使わない要因の追加（手動・未評価）
- **Yes/No評価と直接要因評価**: 該当判断（Yes/No/未評価。Yes が次の階層の通常生成の親）と、別の軸の直接要因評価（5値）・根拠・再発防止策・コメント
- **生成ログ**: 親ごとの結果（作成・候補0件・全候補除外・処理失敗・通信失敗など）と部分失敗の通知。生成中は書き込みと画面の移動を制限
- **未保存の内容の保護**: 画面の移動・要因の切替・再読み込みの前に確認（保存して移動・破棄して移動・編集を続ける）
- **AIへの参考情報**: 頂上事象と分けて「システム構成・対象範囲」「障害発生時の状況・観測事実」を保存し、AI生成の参考情報に使用（出力・API・設計資料では「分析コンテキスト」（`analysis_context`）と呼ぶ）
- **品質警告**: 生成候補の品質チェック結果（「要確認」）の表示
- **エクスポート**: JSON / CSV / Markdown形式で出力（形式ごとの項目の違いは⑤に表示）

画面の詳しい仕様（操作・状態・制約）は [現行画面・操作仕様](docs/ui-current-spec.md) を参照してください。

## UI仕様・再設計資料

| 文書 | 位置づけ |
|---|---|
| [現行画面・操作仕様](docs/ui-current-spec.md) | **現行仕様（正）**。UI 再設計の実装後のコードを根拠にした画面・操作・状態・制約と、確認の区分（コード確認・自動試験・Windows 実機・未確認） |
| [画面改修 実装計画](docs/ui-redesign-implementation-plan.md) | UI 再設計（一覧A／新規作成B／分析編集B）の実装計画と、判断（第6節）・各 PR の記録（第14節） |
| [設計記録（統合案 第2版）](docs/proposals/ui-design-integrated-v2.md) | 取り込んだ提案の原文（未承認の内容を含む。現行仕様ではない） |
| [UI再設計ブリーフ](docs/ui-redesign-brief.md) | 再設計の検討時に Claude Design へ渡した制約・シナリオ（当時の資料） |
| [PR-8 最終受入の手順](docs/manual-check-pr8.md)・[S-11・S-12 の判断資料](docs/pr8-s11-s12-options.md) | 基準ブランチへの統合の前の受入の準備と、未解決の API の制約（S-11・S-12）の判断資料・採用した対策の方針 |

生成品質の詳細は引き続き `docs/` 内の各専用文書を参照してください。

## ディレクトリ構成

```
fta_tool/
  app/
    main.py            # FastAPI アプリケーション本体（ルート）
    detail_view.py     # 編集画面に渡す表示用データ（親子関係の区分・削除範囲・生成対象の判定）
    static_files.py    # /static の配信（no-cache と内容の ETag）
    database.py        # SQLAlchemy DB設定
    models.py          # ORM モデル (Analysis, Node)
    schemas.py         # Pydantic スキーマ
    crud.py            # DB操作関数
    services/          # AI プロバイダ、生成ワークフロー、品質チェック、出力、サンプル など
    templates/
      base.html               # 共通の枠（ヘッダー・通知・favicon）
      _macros.html            # 出力メニュー・評価の表示などの共通部品
      index.html              # 分析一覧（A案）
      analysis_form.html      # 新規分析作成（B案）
      analysis_detail.html    # 分析・編集（B案）
      edit/                   # 編集画面の部品（ヘッダー、作業ステップ、構造ナビ、作業エリア、ツリー、一覧表、インスペクタ）
    static/
      favicon.svg
      css/                    # tokens・base・components と画面ごとの list・new・edit
      js/common/              # 共通（通知、ダイアログ、メニュー、未保存の保護と保存調整、通信、保存領域、IME、文字の検査）
      js/pages/               # list.js・new.js・edit.js と edit/（生成、生成ログ、インスペクタ、部分更新 など）
  config/              # prompts.yaml（プロンプト）、sample_scenarios.yaml（サンプル）
  scripts/             # Windows の確認用スクリプト（run_browser_e2e.ps1 など）と比較試験の道具
  tests/               # 通常の pytest
    e2e/               # 実ブラウザのテスト（Playwright、スタブの AI、一時 DB）。手順は tests/e2e/README.md
  docs/                # 仕様・計画・手順書・証跡（docs/evidence/）
  requirements.txt     # 本番用の依存
  requirements-dev.txt # 開発用（requirements.txt ＋ Playwright・pytest-playwright）
  pytest.ini
  .env.example
  README.md
```

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成します。

```bash
cp .env.example .env
```

デフォルト設定（`AI_PROVIDER=mock`）のままでも動作します。

### 3. サーバーの起動

```bash
uvicorn app.main:app --reload
```

ブラウザで `http://localhost:8000` を開いてください。

## AI プロバイダの設定

`AI_PROVIDER` 環境変数でプロバイダを切り替えます。

### mock（デフォルト）

外部APIなしで動作します。開発・テスト用のサンプル要因を返します。

```
AI_PROVIDER=mock
```

### Ollama（ローカルLLM）

インターネット接続・APIキー不要でローカルLLMを使います。

```
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434   # デフォルト値
OLLAMA_MODEL=gemma3:4b                   # デフォルト値
```

#### Windows 11 での Ollama セットアップ手順

**1. Ollama をインストールする**

[https://ollama.com/download/windows](https://ollama.com/download/windows) からインストーラを
ダウンロードして実行してください。インストール後、Ollama はバックグラウンドで自動起動します。

**2. モデルを取得する**

PowerShell またはコマンドプロンプトで以下を実行します。

```powershell
ollama pull gemma3:4b
```

> 他のモデルを使う場合の例:
> ```powershell
> ollama pull llama3.2:3b   # 軽量・高速
> ollama pull qwen2.5:7b    # 日本語精度が高い
> ```

**3. Ollama が動いているか確認する**

```powershell
# タグ一覧で取得済みモデルを確認
curl http://localhost:11434/api/tags
```

ブラウザで `http://localhost:11434` を開き "Ollama is running" と表示されれば OK です。

**4. FTA ツールの .env を設定する**

実運用・品質確認には **`gemma3:4b`（推奨）** を使います。

```ini
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434

# --- 推奨設定（gemma3:4b） ---
OLLAMA_MODEL=gemma3:4b
OLLAMA_TIMEOUT_SECONDS=300
OLLAMA_KEEP_ALIVE=10m
OLLAMA_NUM_PREDICT=1024
OLLAMA_TEMPERATURE=0.2
OLLAMA_NUM_CTX=4096

# 生成件数
FTA_PRIMARY_FACTOR_COUNT=4
FTA_SECONDARY_FACTOR_COUNT=3
FTA_TERTIARY_FACTOR_COUNT=2
FTA_ADDITIONAL_FACTOR_COUNT=2
```

動作確認や速度優先の場合は `OLLAMA_MODEL=gemma3:1b`、`OLLAMA_TIMEOUT_SECONDS=1800` に変更してください。

> **速度チューニングの目安**
> 1. まず `FTA_*_FACTOR_COUNT` を減らす（件数を 1〜2 件減らすだけで大幅に速くなる）
> 2. それでも遅い場合は `OLLAMA_NUM_PREDICT=768` 程度へ下げる
> 3. `OLLAMA_NUM_CTX` を 2048 に下げることでさらに高速化できるが、長い要因パスの精度が下がる場合がある

**5. FTA ツールを起動する**

```powershell
cd fta_tool
uvicorn app.main:app --reload
```

ブラウザで `http://localhost:8000` を開き、分析・編集画面の「② 一次要因」で「一次要因を生成」を押してください。

**トラブルシューティング**

| 症状 | 対処 |
|------|------|
| "Ollamaに接続できません" | PowerShell で `ollama serve` を実行して Ollama を起動してください |
| 生成が遅い | モデルを `llama3.2:3b` などより小さいものに変更してください |
| JSONパースエラー | モデルを変更するか、`OLLAMA_MODEL=qwen2.5:7b` など日本語対応が強いモデルを試してください |
| OllamaがWi-Fi切断後に止まる | タスクトレイの Ollama アイコンを右クリックして「Restart」してください |

**モデル選択の目安（2025年時点）**

| モデル | VRAM目安 | 日本語精度 | 速度 | 推奨用途 |
|--------|----------|------------|------|---------|
| `gemma3:1b` | 1GB | 低め | とても速い | 動作確認・速度優先 |
| `gemma3:4b` | 4GB | 普通 | 速い | **品質優先（推奨）** |
| `qwen2.5:7b` | 6GB | 高い | 普通 | 日本語精度重視 |
| `llama3.2:3b` | 3GB | 低め | とても速い | 速度優先 |
| `phi4:14b` | 12GB | 高い | 遅い | 最高品質 |

> **`gemma3:1b` と `gemma3:4b` の使い分け**
>
> | | `gemma3:1b` | `gemma3:4b` |
> |--|-------------|-------------|
> | 生成速度 | 速い（1〜2分/階層） | やや遅い（1〜2分/階層） |
> | 要因の件数 | 指定件数より少ない場合がある | 指定件数・JSON形式が安定しやすい |
> | 要因の質 | 抽象的な要因が出やすい | 具体的な要因が出やすい |
> | 推奨場面 | 動作確認・簡易確認 | **実運用・品質確認（推奨）** |
>
> **実運用や品質確認では `gemma3:4b` を推奨します。**  
> `gemma3:4b` は指定件数・JSON形式・要因品質がいずれも安定しており、一次要因生成が 1〜2 分程度で完了します。  
> `gemma3:1b` は動作確認・簡易確認用です。指定件数より少ない件数しか返さない場合があり、品質も不安定なため本番の分析には不向きです。
>
> 件数が不足した場合、ツールは自動で1回リトライします（`FTA_RETRY_BELOW_MIN=true` で制御）。  
> `FTA_RETRY_BELOW_TARGET=true` を設定すると、目標件数未満の場合にも追加リトライします（処理時間が増える）。  
> それでも不足する場合は **追加生成**（「② 一次要因」の「一次要因を追加生成」、または親の見出し・インスペクタの「AIで追加生成」）を使って補完できます。

### Azure OpenAI

```
AI_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-01
```

### HTTP Copilot（Copilot Studio / Power Automate / Azure Function）

```
AI_PROVIDER=http_copilot
COPILOT_FACTOR_API_URL=https://your-endpoint/api/generate-factors
COPILOT_FACTOR_API_KEY=your-api-key   # オプション
```

エンドポイントは以下のリクエスト/レスポンス形式に対応している必要があります。

**リクエスト (POST)**:
```json
{
  "analysis_title": "string",
  "top_event": "string",
  "target_level": 1,
  "parent_path": ["string"],
  "parent_factor": "string or null",
  "context": {}
}
```

**レスポンス**:
```json
[
  {
    "title": "要因タイトル",
    "description": "説明",
    "rationale": "この要因を挙げた理由",
    "check_points": ["確認観点1", "確認観点2"]
  }
]
```

## 使い方

1. 分析一覧で「＋ 新規分析を作成」をクリック
2. 分析タイトル（必須）と頂上事象・AIへの参考情報（任意）を入力し、「作成して編集へ」（サンプルの転記も使えます。転記しただけでは保存されません）
3. 分析・編集画面の「① 頂上事象・参考情報」で内容を確認し、「② 一次要因」で「一次要因を生成」（生成の前に、入力中の頂上事象と参考情報が自動で保存されます）
4. 生成ログで結果を確認し、作業リストまたはインスペクタで Yes／No／未評価を付ける
5. 「③ 二次要因」で「Yesの一次要因から二次要因を生成」（Yes の親ごとに順に生成）。「④ 三次要因」も同じ。特定の親を補うときは「AIで追加生成」または「手動追加」
6. 要因を選び、インスペクタで直接要因評価・評価コメント・根拠・再発防止策・メモを入力して「保存」
7. 「⑤ 確認・出力」またはヘッダーの「出力▾」から JSON／CSV／Markdown を出力

初めて UI 再設計後の版を使うときは、3画面（一覧・新規作成・編集）でそれぞれ1回、強制の再読み込み（Ctrl+F5）をしてください（以前の版の CSS・JavaScript がブラウザに残っている場合があるため。[docs/static-assets-cache-control-plan.md](docs/static-assets-cache-control-plan.md)）。

### 既知の制約（2026-11-02 時点）

- 親子関係に不整合がある要因（別の分析の要因を親にしている、循環など。通常の操作では作られない）があると、一覧からの分析の削除で別の分析の要因も削除されることがあり、生成 API に循環上の親を指定すると要求が終わりません（単一ワーカーでは、その間ほかの要求にも応答しなくなります）（S-11・S-12。編集画面はこうした削除・生成を行いません）。基準ブランチへの統合の前に、別の PR でサーバー側の対策（削除は HTTP 409 で拒否、生成は循環を検出して失敗として返す）を行う方針です（未実施。[判断資料](docs/pr8-s11-s12-options.md) 第6節）。
- 生成中は、同じ画面の書き込み（評価・保存・追加・削除・出力）と画面の移動を止めます。別のタブや API の直接呼び出しは止めません。単一ワーカーでは生成中にほかの要求が待たされます。
- 表示領域が幅 1024px・高さ 500px を下回る組み合わせ（例：Edge の表示倍率 150%・拡大 150%）では、通知が作業エリアの一部を覆うことがあります。詳細は [現行画面・操作仕様](docs/ui-current-spec.md) 第3節・第8節。

## 設定ファイルの構成

FTA ツールの設定は 2 種類のファイルで管理します。

| ファイル | 用途 |
|---------|------|
| `.env` | 実行設定（AIプロバイダ、モデル名、タイムアウト、件数など） |
| `config/prompts.yaml` | プロンプト調整（要因生成の指示文、品質要件、出力例など） |

### `.env` — 実行設定

モデル名・件数・タイムアウトなどの実行パラメータを管理します。変更後は uvicorn の reload または再起動が必要です。

### `config/prompts.yaml` — プロンプト調整

要因生成に使うシステムプロンプトとユーザープロンプトを管理します。Pythonコードを修正せずに指示文・品質要件・出力例を変更できます。**変更後は uvicorn の reload または再起動が必要です。**

```yaml
factor_generation:
  system: |
    <Ollamaに渡すシステムロール>
  user: |
    <ユーザーターン（テンプレート変数を {variable} 形式で使用）>
```

**使用可能なテンプレート変数:**

| 変数 | 内容 |
|-----|------|
| `{top_event}` | 頂上事象のテキスト |
| `{parent_factor}` | 親要因名（一次要因生成時は頂上事象と同じ） |
| `{level}` | 階層名（例: 一次要因（大分類）） |
| `{path_str}` | 要因パス（例: 頂上事象 > 一次要因名） |
| `{desired_count}` | 生成件数（.env の `FTA_*_FACTOR_COUNT` で設定） |
| `{min_count}` | 最低件数（`desired_count - 1`） |
| `{existing_section}` | 既存要因リスト（追加生成時のみ挿入。空の場合は空文字） |

> **注意**: プロンプト内の JSON 例示（`{"name": "..."}` 形式）は変数として扱われません。`{` の直後に `"` がある場合、テンプレートエンジンがスキップします。

**カスタムプロンプトファイルの指定:**

`.env` に `FTA_PROMPT_FILE` を設定するとパスを変更できます。

```ini
FTA_PROMPT_FILE=config/prompts.yaml         # デフォルト（fta_tool/ からの相対パス）
FTA_PROMPT_FILE=/absolute/path/my_prompts.yaml  # 絶対パスも可
```

## LangGraph 検査付き生成ワークフロー（Step 3・既定OFF）

生成 → 構造検証 → 品質評価 → 判定（accept / regenerate / fail_soft）→ 必要な場合だけ再生成、
という LangGraph の状態管理・分岐制御を実装しています。既定ではすべて OFF で、従来の生成処理がそのまま動きます。

```ini
# LangGraphワークフロー（Step 2-1から継続、既定 false）
ENABLE_LANGGRAPH_GENERATION_WORKFLOW=false
# スコアベース品質ゲート（Step 3新設、既定 false）
ENABLE_LANGGRAPH_QUALITY_GATE=false
# 再生成回数の上限（既定 1）
LANGGRAPH_GENERATION_MAX_RETRIES=1
# accept閾値 0〜1（既定 0.7 = 平均FactorScore 70/100）
LANGGRAPH_QUALITY_THRESHOLD=0.7
```

ノード構成・分岐仕様・ログの見方・今後の拡張候補は [docs/langgraph_step3.md](docs/langgraph_step3.md) を、
品質ゲートの段階判定（accept / accept_with_warning / retry / reject）と部分再生成（Step 3.5で実装済み）は
[docs/langgraph_quality_gate_rules.md](docs/langgraph_quality_gate_rules.md) を参照してください。

### LangGraph / Quality Gate 比較試験支援キット

LangGraph・品質ゲートの ON/OFF 4設定（実効3モード）を同一条件で複数回実行し、
処理時間と生成品質を比較するためのスクリプトを用意しています。

```powershell
# 実行（Windows PowerShell。ログ・エクスポートを試験ID配下へ保存）
powershell -ExecutionPolicy Bypass -File scripts\run_langgraph_comparison.ps1 -TrialId trial_001

# 解析（runs.csv / factor_quality.csv / summary.md を生成）
python scripts\analyze_langgraph_comparison.py ..\comparison_results\trial_001
```

手順・推奨反復回数・出力の見方・人手評価項目は
[docs/langgraph_comparison_test.md](docs/langgraph_comparison_test.md) を参照してください。

## テストの実行

```bash
cd fta_tool
pip install -r requirements-dev.txt   # 開発用（本番用 requirements.txt ＋ Playwright・pytest-playwright）
pytest -m "not e2e"                   # 通常の pytest（実ブラウザのテストを除く）
pytest                                # 実ブラウザのテストも含む（ブラウザ・Playwright がなければ E2E はスキップ）
```

- `pytest.ini` が `fta_tool/` を基準にするため、`fta_tool/` で実行します。通常の pytest も、アプリの DB は一時ディレクトリに作ります（利用者の `fta_tool.db` は使いません）。
- PowerShell がない環境では、Windows 用スクリプトの確認がスキップになります（環境依存のスキップ）。
- **UI 改修の必須受入検証**（実ブラウザのテスト。スキップ・未実施は失敗）は `pytest -m e2e --e2e-required --e2e-env "<実行環境>" --e2e-report e2e-report.md` です。ブラウザの準備、Windows の Chrome・Edge での実行（`scripts/run_browser_e2e.ps1`）、記録の読み方は [tests/e2e/README.md](tests/e2e/README.md) を参照してください。実LLMは呼ばず、スタブの AI と一時 DB を使います。

## データベース

SQLite (`fta_tool.db`) をローカルに自動生成します。テーブルはアプリ起動時に自動作成されます。

## APIエンドポイント

| メソッド | パス | 説明 |
|--------|------|------|
| GET | `/` | 分析一覧 |
| GET | `/analyses/new` | 新規作成フォーム |
| POST | `/analyses` | 分析作成 |
| GET | `/analyses/{id}` | 分析詳細・編集 |
| POST | `/analyses/{id}/title` | 分析タイトル更新 |
| POST | `/analyses/{id}/context` | 分析コンテキスト更新 |
| POST | `/analyses/{id}/delete` | 分析削除（配下の要因も削除） |
| POST | `/analyses/{id}/top-event` | 頂上事象更新 |
| POST | `/analyses/{id}/generate/level/{level}` | AI要因生成（`{"additional": true}` で追加生成） |
| POST | `/analyses/{id}/nodes/add-level1` | 一次要因手動追加 |
| GET | `/nodes/{id}` | ノード詳細取得（編集画面のインスペクタの詳細の編集欄が使用） |
| POST | `/nodes/{id}/update` | ノード更新 |
| POST | `/nodes/{id}/delete` | ノード削除 |
| POST | `/nodes/{id}/children` | 子ノード追加 |
| GET | `/analyses/{id}/export/json` | JSONエクスポート |
| GET | `/analyses/{id}/export/csv` | CSVエクスポート |
| GET | `/analyses/{id}/export/markdown` | Markdownエクスポート |

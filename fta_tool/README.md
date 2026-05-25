# FTA分析支援ツール

FTA（フォルトツリー解析）を支援するWebアプリケーションです。AIによる要因候補の自動生成、ツリー構造の視覚的編集、JSON/CSV/Markdown形式でのエクスポートをサポートします。

## 機能

- **FTA分析の作成・管理**: 分析タイトルと頂上事象を設定して分析を作成
- **AIによる要因生成**: 一次・二次・三次要因をAIが自動提案
- **インタラクティブなツリー編集**: 横並びカラムでFTAツリーを直感的に編集
- **Yes/No評価**: 各要因に対してユーザが妥当性を評価
- **直接要因評価**: 要因ごとに根拠・防止策・コメントを記録
- **エクスポート**: JSON / CSV / Markdown形式で出力

## ディレクトリ構成

```
fta_tool/
  app/
    __init__.py
    main.py          # FastAPI アプリケーション本体
    database.py      # SQLAlchemy DB設定
    models.py        # ORM モデル (Analysis, Node)
    schemas.py       # Pydantic スキーマ
    crud.py          # DB操作関数
    services/
      __init__.py
      ai_provider.py     # AI プロバイダ抽象層
      export_service.py  # エクスポート処理
    templates/
      base.html
      index.html
      analysis_form.html
      analysis_detail.html
    static/
      style.css
      app.js
  tests/
    __init__.py
    test_ai_provider.py
    test_export_service.py
  requirements.txt
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

```ini
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:1b

# タイムアウト（gemma3:1b なら 1800 秒あれば余裕あり）
OLLAMA_TIMEOUT_SECONDS=1800
OLLAMA_KEEP_ALIVE=10m

# 生成件数（速度とのトレードオフ: 件数を減らすと速くなる）
FTA_PRIMARY_FACTOR_COUNT=4
FTA_SECONDARY_FACTOR_COUNT=3
FTA_TERTIARY_FACTOR_COUNT=2
FTA_ADDITIONAL_FACTOR_COUNT=2

# 推論オプション（品質を下げないため num_predict は 512 未満にしない）
OLLAMA_NUM_PREDICT=768
OLLAMA_TEMPERATURE=0.2
OLLAMA_NUM_CTX=4096
```

> **速度チューニングの目安**
> 1. まず `FTA_*_FACTOR_COUNT` を減らす（件数を 1〜2 件減らすだけで大幅に速くなる）
> 2. それでも遅い場合は `OLLAMA_NUM_PREDICT=512` 程度へ下げる
> 3. `OLLAMA_NUM_CTX` を 2048 に下げることでさらに高速化できるが、長い要因パスの精度が下がる場合がある

**5. FTA ツールを起動する**

```powershell
cd fta_tool
uvicorn app.main:app --reload
```

ブラウザで `http://localhost:8000` を開き、FTA 分析画面で「一次要因を生成」を押してください。

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
> | 生成速度 | 速い（1〜2分/階層） | やや遅い（2〜4分/階層） |
> | 要因の件数 | 指定件数に届かない場合がある | おおむね指定件数を生成できる |
> | 要因の質 | 抽象的な要因が出やすい | 具体的な要因が出やすい |
> | 推奨場面 | 動作確認・簡易レビュー | 本番の分析・品質優先 |
>
> **通常運用では `gemma3:4b` を推奨します。** `gemma3:4b` は生成件数・品質ともに安定しており、一次要因生成が約2分で完了します。  
> `gemma3:1b` は速度優先の簡易確認用です。指定件数に届かない場合が多く、品質も不安定なため本番の分析には不向きです。
>
> 件数が不足した場合、ツールは自動で1回リトライします（`FTA_RETRY_BELOW_MIN=true` で制御）。  
> `FTA_RETRY_BELOW_TARGET=true` を設定すると、目標件数未満の場合にも追加リトライします（処理時間が増える）。  
> それでも不足する場合は **「追加生成」ボタン** を使って補完できます。

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

1. トップページで「新規分析を作成」をクリック
2. 分析タイトルと頂上事象を入力して作成
3. 分析詳細画面で「一次要因を生成」ボタンをクリック
4. 生成された要因を確認し、Yes/Noで評価
5. Yes評価の要因から「二次要因を生成」でドリルダウン
6. 「詳細編集」で根拠・直接要因評価・再発防止策を記録
7. 完成したらJSON/CSV/MDでエクスポート

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

## テストの実行

```bash
# プロジェクトルートから実行
pytest fta_tool/tests/ -v

# または fta_tool ディレクトリ内から
cd fta_tool
pytest tests/ -v
```

## データベース

SQLite (`fta_tool.db`) をローカルに自動生成します。テーブルはアプリ起動時に自動作成されます。

## APIエンドポイント

| メソッド | パス | 説明 |
|--------|------|------|
| GET | `/` | 分析一覧 |
| GET | `/analyses/new` | 新規作成フォーム |
| POST | `/analyses` | 分析作成 |
| GET | `/analyses/{id}` | 分析詳細・編集 |
| POST | `/analyses/{id}/top-event` | 頂上事象更新 |
| POST | `/analyses/{id}/generate/level/{level}` | AI要因生成 |
| POST | `/analyses/{id}/nodes/add-level1` | 一次要因手動追加 |
| POST | `/nodes/{id}/update` | ノード更新 |
| POST | `/nodes/{id}/delete` | ノード削除 |
| POST | `/nodes/{id}/children` | 子ノード追加 |
| GET | `/analyses/{id}/export/json` | JSONエクスポート |
| GET | `/analyses/{id}/export/csv` | CSVエクスポート |
| GET | `/analyses/{id}/export/markdown` | Markdownエクスポート |

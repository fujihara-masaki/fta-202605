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

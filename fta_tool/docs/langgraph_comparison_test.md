# LangGraph / Quality Gate 比較試験の手順（比較試験支援キット）

LangGraph ワークフローと品質ゲートの ON/OFF が、処理時間と生成品質へ
どう影響するかを **同一条件・複数回** の実行で比較するための手順書です。

比較試験支援キットは以下の 2 スクリプトで構成されます。
**生成アルゴリズム・品質判定ルール・プロンプト・DB スキーマ・既存 API の
挙動には一切手を加えません**（実行と解析の支援のみ）。

| ファイル | 役割 |
|---------|------|
| `scripts/run_langgraph_comparison.ps1` | 設定を切り替えながらツールをローカル起動し、生成を反復実行してログ・エクスポートを試験ID配下へ保存（Windows PowerShell 用） |
| `scripts/analyze_langgraph_comparison.py` | 保存されたログ・エクスポートを解析し、`runs.csv` / `factor_quality.csv` / `summary.md` を生成 |

## 4設定・3実効モード

| # | 設定名 | ENABLE_LANGGRAPH_GENERATION_WORKFLOW | ENABLE_LANGGRAPH_QUALITY_GATE | 実効動作 |
|---|--------|--------------------------------------|-------------------------------|----------|
| 1 | `off-off` | false | false | legacy（従来の生成処理） |
| 2 | `off-on`  | false | true  | **legacy と同一**（下記参照） |
| 3 | `on-off`  | true  | false | LangGraph ワークフロー（Step 2-1 相当の分岐） |
| 4 | `on-on`   | true  | true  | LangGraph ＋ 品質ゲート（段階判定・部分再生成） |

Quality Gate は **LangGraph ON のときだけ作用** します（main.py が
`quality_gate_enabled = langgraph_enabled and …` で合成するため）。
したがって設定 1 と 2 は実効的に同じ legacy 動作であり、**4設定・3実効モード**
の試験になります。設定 2 は「Quality Gate フラグが LangGraph OFF 時に何も
影響しないこと」を確認するための **対照条件** として実行します
（設定 1 と 2 の結果が LLM の非決定性の範囲を超えて異なる場合は、
フラグの独立性が壊れたことを示すシグナルです）。

## 前提条件

- Windows 上の PowerShell（5.1 以降。PowerShell 7 でも動作）
- Python（`pip install -r requirements.txt` 済み）
- Ollama が起動済みで、`.env` の `AI_PROVIDER=ollama` / `OLLAMA_MODEL` が
  設定済みであること（モデルは事前に `ollama pull` しておく）
- ポート 8130（`-Port` で変更可）が空いていること
- パスに空白が含まれていても動作します

> **注意**: スクリプトは実行中に `fta_tool/.env` の LangGraph 関連 2 キーを
> 一時的に書き換えます（`.env` は python-dotenv が override=True で読むため、
> 環境変数では上書きできません）。元の `.env` は開始時に
> `.env.comparison_backup` へ退避し、終了時（途中停止時も含む）に復元します。
> 万一復元されずに残った場合も、次回実行時に自動復元されます。

## 実行方法

```powershell
cd fta_tool
powershell -ExecutionPolicy Bypass -File scripts\run_langgraph_comparison.ps1 `
    -TrialId trial_20260712_a `
    -Iterations 3 `
    -WarmupRuns 1 `
    -MaxLevel 2 `
    -ScenarioId internet_web_access_failure
```

主なパラメータ:

| パラメータ | 既定値 | 意味 |
|-----------|--------|------|
| `-TrialId` | `trial_yyyyMMdd_HHmmss` | 試験ID（出力ディレクトリ名） |
| `-Configs` | 4設定すべて | 実行する設定（`off-off` 等、または `1`〜`4`） |
| `-Iterations` | 3 | 設定ごとの評価対象（計測）実行回数 |
| `-WarmupRuns` | 1 | 設定ごとのウォームアップ実行回数 |
| `-OrderMode` | `interleave` | 実行順序（下記） |
| `-ScenarioId` | `internet_web_access_failure` | `config/sample_scenarios.yaml` のシナリオID |
| `-TopEvent` | （なし） | シナリオを使わず頂上事象を直接指定 |
| `-MaxLevel` | 2 | 生成する階層（1〜3） |
| `-RunDate` | 現在時刻 | 実施日時ラベル（スナップショットに記録） |
| `-SkipAnalyze` | — | 実行後の自動解析をスキップ |

1回の「実行」は次の一連の処理です:

1. 対象設定の `.env` を書き込み、**専用の作業ディレクトリで** uvicorn を起動
   （SQLite DB は実行ごとに新規 = 前の実行の要因が DB 重複除外に影響しない）
2. 同一シナリオ・同一頂上事象で分析を作成
3. レベル1を生成 → 生成要因を全件 Yes 評価 → レベル2を生成（`-MaxLevel 3` なら同様にレベル3まで）
4. JSON / CSV / Markdown エクスポートとサーバーログ・APIレスポンスを保存
5. サーバー停止・`runs_index.csv` へ逐次追記（**途中停止しても完了分は残る**）

## 同一条件の担保

- **同じ頂上事象・同じシナリオ・同じ設定**（フラグ以外）を全実行で使います。
  試験をまたいで比較する場合も、必ず同じ `-ScenarioId`・同じ `.env`
  （モデル・件数・温度など）で実行してください。
- 実行時の主要設定は `config_snapshots/<設定>.env.txt`（APIキー等の秘密情報は
  マスク）と `<設定>.snapshot.json`（フラグ・git commit・CPU数・OS など）に
  スナップショット保存されます。試験結果を比較する前に、この
  スナップショット同士が意図どおり「LangGraph 関連 2 キーのみの差」に
  なっていることを確認してください。

## ウォームアップの扱い

最初の生成はモデルのロード（Ollama の `load_duration`）やプロセス起動の
影響で遅くなります。`-WarmupRuns 1`（既定）で設定ごとに 1 回の
ウォームアップ実行を行い、**解析では自動的に集計から除外** されます
（`runs.csv` には `phase=warmup` として残るので、必要なら確認できます）。
`OLLAMA_KEEP_ALIVE` が短い設定や PC のスリープを挟んだ場合は、ウォーム
アップの効果が薄れる点に注意してください。

## 実行順序による偏りの低減

計測実行の並び順は `-OrderMode` で制御します:

- `interleave`（既定）: 反復1回目を全設定 → 2回目を全設定 → …の順で回すため、
  時間経過による PC 状態の変化（温度・他プロセス）が特定の設定へ偏りません。
- `sequential`: 設定ごとにまとめて実行（設定切替コストは最小）。
- `random`: 計測実行をシャッフル（`-RandomSeed` で再現可能）。

## 推奨反復回数

- **最低 3 回、可能なら 5 回**（`-Iterations 5`）を推奨します。
  LLM 生成は温度 > 0 で非決定的なため、1〜2 回の比較は偶然の影響が大きく、
  中央値・標準偏差を見るには 3 回以上が必要です。
- 品質ゲートの再生成回数・reject 数のような **離散的で発生頻度が低い指標**
  を比較したい場合は 5〜10 回を推奨します。
- 所要時間の目安: 1 実行 = レベル数 ×（親要因数 × 1 生成呼び出し）。
  CPU 実行の小型モデルでは 1 実行あたり数分かかるため、
  4 設定 ×（1 warmup + 3 計測）= 16 実行で 1〜2 時間程度を見込んでください。

## 制約（結果を読むときの注意）

- **PC 負荷の影響**: 測定はローカルPCの Ollama 推論時間が支配的です。
  試験中は他の重いアプリ・ブラウザの動画再生・Windows Update などを避け、
  電源設定を「高パフォーマンス」に固定してください。ノートPCでは
  サーマルスロットリングにより後半の実行ほど遅くなることがあります
  （`interleave` 順序はこの偏りを設定間で均すためのものです）。
- **モデルの非決定性**: 同一設定でも生成される要因は毎回変わり得ます。
  処理時間は生成トークン数に比例して揺れるため、時間比較は
  `summary.md` の中央値と、`runs.csv` の出力トークン数
  （`ollama_eval_tokens`）を併せて確認してください。
  品質比較（created / 除外数 / decision など）は回数を増やして傾向で
  判断し、1 回の差で結論を出さないでください。
- **設定間の時間差の解釈**: LangGraph ON はノード実行・再生成の分だけ
  遅くなるのが期待動作です（処理時間短縮は目的ではありません）。
  再生成が発生した実行は Ollama 呼び出し回数（`ollama_calls`）が増えるため、
  「1 呼び出しあたりの時間」と「呼び出し回数」を分けて見てください。
- 設定 1 と 2（実効 legacy）の差は LLM の非決定性の範囲内であるべきです。

## 出力ファイルの見方

```
comparison_results/<試験ID>/
├── runs_index.csv               実行一覧（逐次追記。中断時もここまでの記録が残る）
├── config_snapshots/
│   ├── <設定>.env.txt           実行時 .env（秘密情報マスク済み）
│   └── <設定>.snapshot.json     フラグ・git commit・CPU数などの環境記録
├── runs/<実行ID>/
│   ├── server.out.log / server.err.log   uvicorn / アプリのログ（生データ）
│   ├── gen_level1.json, gen_level2.json  generate API のレスポンス（quality_summary 含む）
│   ├── export.json / export.csv / export.md   FTAツリーのエクスポート
│   ├── run_meta.json            実行メタデータ（設定・階層別時間・状態）
│   └── work/fta_tool.db         この実行専用の SQLite DB
└── analysis/                    解析結果（analyze_langgraph_comparison.py が生成）
    ├── runs.csv
    ├── factor_quality.csv
    └── summary.md
```

- **`analysis/runs.csv`**: 1 行 = 1 生成リクエスト（`scope=request`、階層単位）
  ＋ 実行合計行（`scope=run_total`）。処理時間（`elapsed_ms`）、
  ai_returned / created、品質チェック除外（`excluded_quality`）、
  DB重複除外（`excluded_dedup`）、`rejected_by_gate` /
  `regenerated_created` / 再生成回数（`retries`）、decision、
  Ollama の推論時間（`ollama_total_ms` / `ollama_prompt_eval_ms` /
  `ollama_eval_ms`）とトークン数（`ollama_prompt_tokens` /
  `ollama_eval_tokens`）を含みます。Excel でそのまま開けます（UTF-8 BOM）。
- **`analysis/factor_quality.csv`**: 1 行 = 候補または保存済み要因。
  `source` 列が由来（`langgraph_candidate` = 候補ごとの評価ログ、
  `gate_reject` = ゲートで最終除外、`legacy_exclude` / `legacy_warning` /
  `dedup_skip` = legacy パスのログ、`export` = エクスポートCSVの保存済み要因）。
  スコア・severity・警告理由・critical理由・保存有無に加えて、
  **人手評価用の空欄列**（後述）があります。
- **`analysis/summary.md`**: 設定別の比較表。総処理時間（平均・中央値・
  標準偏差・最小・最大）、階層別・親要因別処理時間、Ollama 推論時間・
  トークン数、生成品質（ai_returned / created / 除外 / rejected_by_gate /
  regenerated_created / 再生成回数 / 平均品質スコア）、decision 別件数、
  warning・critical 理由別件数、解析ノート（欠損項目の記録）。
- 古い形式のログや欠損ファイルがあっても解析は例外終了せず、読めた範囲で
  集計し、読めなかった項目は `summary.md` の「解析ノート」に記録されます。

再解析だけを行う場合:

```powershell
cd fta_tool
python scripts\analyze_langgraph_comparison.py "..\comparison_results\<試験ID>"
```

## 人手による品質評価項目

自動集計（スコア・除外数など）はルールベースの目安に過ぎないため、
最終的な品質比較には人手評価を推奨します。`factor_quality.csv` の
末尾列に記入してください（保存済み要因 = `source=export` の行が対象）。

| 列 | 評価項目 | 記入例 |
|----|----------|--------|
| `human_validity` | **妥当性**: 頂上事象／親要因の原因として技術的に成り立つか | 1〜5 |
| `human_specificity` | **具体性**: 抽象的すぎず、調査・確認に落とせる粒度か | 1〜5 |
| `human_actionability` | **実用性**: 確認観点・対策の検討につながるか | 1〜5 |
| `human_duplication` | **重複感**: 同一分析内の他要因と実質重複していないか（1=重複、5=独立） | 1〜5 |
| `human_note` | 気づき（言い換え・階層逆転・シナリオ不整合など） | 自由記述 |

評価のガイドライン:

- 設定名を伏せて（ブラインドで）評価すると先入観を避けられます。
  `factor_quality.csv` を `title` 列でソートしてから評価するなどの工夫を
  推奨します。
- 品質ゲートの効果は「保存された要因の平均点」だけでなく、
  **「明らかに不適切な要因（親の言い換え・祖先戻り・重複）が保存されて
  しまった件数」** で比較するのが有効です（ゲートはそれらの除外が目的のため）。
- reject された候補（`source=gate_reject`）にも目を通し、
  **過剰除外（本来有効な要因が落とされた）** がないかを確認してください。

## テスト

解析処理は実 Ollama を呼ばずにテストできます（サンプルログ・サンプルCSVを
fixture として使用）:

```powershell
cd fta_tool
pytest tests\test_analyze_langgraph_comparison.py -v
```

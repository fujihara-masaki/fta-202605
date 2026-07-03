# Step 3: LangGraph 検査付き生成ワークフロー（品質ゲート）

> **Step 3.5 での更新**: ゲートON時の判定は
> accept / accept_with_warning / regenerate(retry) / reject の段階判定に
> 拡張され、問題候補のみの部分再生成が入りました。最新の判定仕様は
> [langgraph_quality_gate_rules.md](langgraph_quality_gate_rules.md) を
> 参照してください（本書のゲートON分岐表は Step 3 時点の記述です。
> ゲートOFF・フラグ体系・fail_soft/legacy fallback の契約は変わりません）。

## 目的

Step 2/2-1 では既存の生成処理を LangGraph ワークフロー経由でも動かせるようにしましたが、
再生成の条件は「全件除外（all_excluded）」「候補ゼロ（no_candidates）」のみで、
LangGraph 本来の価値である **生成 → 検査 → 判定 → 必要な場合だけ再生成** の
状態管理・分岐制御はまだ活きていませんでした。

Step 3 では、以下を実現する制御構造を作ります（処理時間短縮は目的にしません）。

- 構造検証（Pydantic）と品質評価（Step 2-0 の純粋関数）をワークフローの独立ノードに分離
- 品質スコア・警告数・重大警告・再生成回数に基づく **accept / regenerate / fail_soft** の三値判定
- 再生成上限に達した場合は例外で落とさず、**最良の試行を警告付き結果として返す（fail_soft）**

## Feature Flag（設定項目）

| 環境変数 | 既定値 | 意味 |
|---------|-------|------|
| `ENABLE_LANGGRAPH_GENERATION_WORKFLOW` | `false` | LangGraph ワークフロー自体の ON/OFF（Step 2-1 から継続）。OFF のとき langgraph は import されず、従来の生成処理がそのまま動く |
| `ENABLE_LANGGRAPH_QUALITY_GATE` | `false` | **Step 3 新設。** スコアベースの品質ゲート。OFF のときは Step 2-1 と同じ分岐（all_excluded / no_candidates のみ再生成） |
| `LANGGRAPH_GENERATION_MAX_RETRIES` | `1` | 再生成回数の上限（既存設定を流用。依頼文中の `LANGGRAPH_MAX_REGEN_ATTEMPTS` に相当） |
| `LANGGRAPH_QUALITY_THRESHOLD` | `0.7` | **Step 3 新設。** accept 閾値（0〜1）。保存対象候補の平均 FactorScore（0〜100）を 100 で割った値と比較する |

両フラグとも既定 OFF のため、**何も設定しなければ従来の生成処理が完全にそのまま動きます。**
DB スキーマ変更・UI 変更はありません。

## ワークフローのノード構成

対象は「親要因 1 件分」の生成です（`app/services/generation_workflow.py`）。

```
START
  → generate_candidates      既存の LLM 生成処理（注入された generate_fn）を呼ぶ
  → validate_structure       Pydantic（CandidateStructure）で要因名・説明などの構造を検証。
                             不正候補は警告付きで除外（例外にはしない）
  → evaluate_quality         Step 2-0 の純粋関数（evaluate_candidates）で重複・親の言い換え・
                             祖先戻り・No評価再出現などを評価し、平均品質スコア(0-1)・
                             警告一覧・outcome・重大警告有無を算出
  → decide_next_action       accept / regenerate / fail_soft を判定
      ├─ accept / fail_soft → finalize_result → END
      └─ regenerate → regenerate_candidates → validate_structure（ループ）
```

- `finalize_result` は fail_soft のとき、試行履歴から **最良の試行**
  （保存件数 → 品質スコア → 新しい試行の順で比較）の候補を採用します。
- 各ノードはロギング＋計測＋例外ガードでラップされており、ノード内の想定外例外は
  `error` 状態に変換され fail_soft で終端します（リクエスト全体は落ちません）。
- 再生成は現状「全体再生成」ですが、試行ごとの記録（`state["attempts"]`）に
  `kept_titles` / `excluded_titles` / `reasons`（除外理由ラベル）/ `warning_count` を
  保持しているため、低品質部分のみの部分再生成へグラフ形状を変えずに拡張できます
  （`regenerate_candidates` の docstring 参照）。

### エラーと legacy fallback の関係

`WorkflowResult.error`（= `quality_summary.workflow_error`）は
**どの試行からも採用可能な候補が 1 件も得られなかった場合のみ** セットされ、
main.py はこのときだけ従来パス（legacy fallback）で再生成します。

- provider の初回生成が失敗し、使える試行がゼロ → `error` あり → legacy fallback
- 再生成中に provider が失敗しても、それ以前の試行に採用可能な候補があれば
  `finalize_result` が `error` を解除し、その最良試行を **fail_soft の通常結果**
  として返します（ゼロからの再生成はしません）
- 品質ゲートによる fail_soft・再生成上限到達・構造検証での除外は、
  すべてワークフローの通常結果であり `workflow_error` にはなりません

### 分岐仕様（decide_next_action）

| 条件 | 判定 |
|------|------|
| 生成処理でエラー発生 | `fail_soft`（使える試行があればその最良試行を通常結果として返す。使える試行がゼロのときのみ error が結果に載り、main.py が従来パスへフォールバック） |
| **ゲートON**: 重大警告なし かつ 品質スコア ≥ 閾値 | `accept` |
| **ゲートON**: 上記以外 かつ 再生成回数 < 上限 | `regenerate` |
| **ゲートON**: 再生成上限に到達 | `fail_soft`（最良試行を警告付きで返す） |
| **ゲートOFF**: outcome が created / partial | `accept`（Step 2-1 と同一） |
| **ゲートOFF**: all_excluded / no_candidates かつ 上限未満 | `regenerate` |
| **ゲートOFF**: 上限到達 | `fail_soft` |

重大警告（critical）= その試行から使える候補が 1 件も出なかった状態
（全件が構造検証または品質チェックで除外、もしくは LLM が候補を返さなかった）。

## ON/OFF の確認方法

`.env`（`fta_tool/.env`）を編集して uvicorn を再起動します。

```ini
# パターンA: 従来動作（既定）
ENABLE_LANGGRAPH_GENERATION_WORKFLOW=false

# パターンB: LangGraphあり・品質ゲートなし（Step 2-1 相当）
ENABLE_LANGGRAPH_GENERATION_WORKFLOW=true
ENABLE_LANGGRAPH_QUALITY_GATE=false

# パターンC: LangGraphあり・品質ゲートあり（Step 3）
ENABLE_LANGGRAPH_GENERATION_WORKFLOW=true
ENABLE_LANGGRAPH_QUALITY_GATE=true
LANGGRAPH_GENERATION_MAX_RETRIES=1
LANGGRAPH_QUALITY_THRESHOLD=0.7
```

起動ログの `=== FTA Tool startup configuration ===` ブロックで両フラグの値を確認できます。
API レスポンスの `quality_summary` にも `workflow`（legacy / langgraph）、
`quality_gate`、`decisions`（親要因ごとの accept / fail_soft）が追加で載ります。

### 動作確認コマンド

```powershell
# テスト（全パターンのユニット/エンドポイントテストを含む）
cd fta_tool
pytest tests/ -v

# ワークフロー関連のみ
pytest tests/test_generation_workflow.py tests/test_quality_gate_workflow.py -v

# サーバー起動（.env のパターンを切り替えて比較）
uvicorn app.main:app --reload
# ブラウザで分析を開き「一次要因を生成」→ 下記ログ項目を確認
```

## ログで確認すべき項目

PowerShell 側から grep しやすいよう、`key=value` 形式で出力します。

| ログ行 | 内容 |
|--------|------|
| `generate_factors workflow \| … langgraph=… quality_gate=…` | リクエスト単位。LangGraph 使用有無・ゲート使用有無・decisions・再生成回数・outcome・所要時間（ON/OFF比較の起点） |
| `langgraph run start \| quality_gate=… threshold=… max_retries=…` | ワークフロー実行の開始（親要因単位） |
| `langgraph node start / end \| node=… attempt=… elapsed_ms=…` | 各ノードの開始・終了と処理時間 |
| `langgraph decide \| decision=… quality_score=… warnings=… critical=… retry_count=…` | 判定ごとの品質スコア・警告数・重大警告有無・再生成回数 |
| `langgraph structure invalid \| invalid=…/… errors=…` | 構造検証で除外された候補 |
| `langgraph fail_soft best attempt \| using attempt=…` | fail_soft 時にどの試行が採用されたか |
| `langgraph run summary \| decision=… outcome=… quality_score=… node_ms=…` | ワークフロー実行の最終サマリ（最終判定・ノード別処理時間の一覧） |

PowerShell での抽出例:

```powershell
uvicorn app.main:app 2>&1 | Tee-Object -FilePath fta.log
Select-String -Path fta.log -Pattern "langgraph run summary|generate_factors workflow"
```

## 実装ファイル

| ファイル | 変更内容 |
|---------|---------|
| `app/services/generation_workflow.py` | Step 3 グラフ本体（6ノード＋分岐、計測ラッパ、fail_soft 最良試行選択） |
| `app/services/llm_models.py` | `CandidateStructure`（構造検証の Pydantic 契約）と `validate_candidate_structure()` |
| `app/services/generation_config.py` | `langgraph_quality_gate_enabled()` / `langgraph_quality_threshold()` |
| `app/main.py` | フラグの受け渡し、リクエスト単位ログ、`quality_summary` への追加フィールド |
| `tests/test_quality_gate_workflow.py` | Step 3 ユニットテスト（ゲートON/OFF・fail_soft・構造検証・例外） |
| `tests/test_generate_endpoint.py` | Step 3 エンドポイントテスト（追記） |

## 今後の Step 4 候補

- **部分再生成**: 低品質と判定された候補のみを再生成し、高スコアの kept 候補を維持する
  （`state["attempts"]` に必要な情報は記録済み。`regenerate_candidates` の拡張のみで対応可能）
- **再生成プロンプトの品質フィードバック**: 除外理由・警告内容（親の言い換え、祖先戻り等）を
  再生成時のプロンプトへ具体的に注入し、同じ失敗の再発を抑える
- **閾値・重みのチューニング**: 実ログの quality_score 分布を集計し、
  `LANGGRAPH_QUALITY_THRESHOLD` と `FactorScore` の重みを実データで調整する
- **LLM-as-a-judge ノードの追加**: ルールベース評価に加え、判定用の軽量 LLM 呼び出しノードを
  `evaluate_quality` の後段にオプション追加する（グラフ形状は据え置き）
- **チェックポイント/可視化**: LangGraph の checkpointer を使った実行トレースの永続化と、
  ノード遷移の可視化（デモ・デバッグ用途）

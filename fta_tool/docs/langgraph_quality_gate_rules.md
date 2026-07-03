# Step 3.5: 品質ゲート判定ルールの段階化（accept / accept_with_warning / retry / reject）

## 目的

Step 3 の品質ゲートは「平均スコア < 閾値」のみが再生成条件だったため、
実運用ではほぼ全件 `accept` となり、警告記録・観察機能に留まっていました。
Step 3.5 では、明らかに品質上問題のある候補（親の言い換え・祖先逆戻り・
高類似重複・No評価済み類似）を **候補単位で critical と分類**し、
段階的な判定と **問題候補のみの部分再生成** を行います。

フラグ体系・既定値は Step 3 から変更ありません（両フラグ既定 OFF）。
`ENABLE_LANGGRAPH_GENERATION_WORKFLOW=false` の従来動作、および
`ENABLE_LANGGRAPH_QUALITY_GATE=false`（Step 2-1 相当）の分岐は不変です。

## 候補単位の severity 分類（app/services/factor_quality.py）

`evaluate_candidate` が各候補に `severity`（ok / warning / critical）と
`critical_reasons`（短いラベル）を付与します。**レガシーパスの
exclude / warning 挙動は変更していません**（severity は追加情報）。

| 判定 | 条件 | severity |
|------|------|----------|
| 親要因の言い換え | 正規化後類似度 ≥ 0.72（E1・従来から除外） | critical |
| 説明文が親と同一 | 完全一致（E2・従来から除外） | critical |
| No評価済み要因と高類似 | 類似度 ≥ 0.78（E3・従来から除外） | critical |
| **祖先要因への逆戻り** | ancestor_similarity ≥ 0.70（従来は警告のみ） | **critical（ゲートON時のみ作用）** |
| **既存要因と高類似** | 類似度 ≥ 0.82（従来は警告のみ） | **critical（ゲートON時のみ作用）** |
| No評価済みと汎用語（系統トークン）一致のみ | DNS / VPN / 認証基盤 等の語一致 | warning |
| 汎用的すぎる要因名・要因名が長すぎる | 従来どおり | warning |
| 問題なし | — | ok |

- 類似度は正規化後タイトル全体の意味比較（SequenceMatcher＋包含）で、
  **単語一致だけでは critical になりません**。DNS / VPN / 認証 /
  ファイアウォール / ネットワーク / サーバ / 通信 / 設定 / 障害 などの
  汎用語一致は warning 止まりです。
- 正規化サフィックスに否定形（「〜されない」「〜できない」等）を追加し、
  「DNS設定の配布漏れ」→「DNS設定が配布されない」のような言い換えを
  検出できるようにしました（閾値自体は 0.72 のまま）。

## 段階判定（ゲートON時の decide_next_action）

| 条件 | 判定 |
|------|------|
| critical 候補なし かつ 平均スコア ≥ 閾値 かつ 警告なし | `accept` |
| critical 候補なし かつ 平均スコア ≥ 閾値 かつ 軽微な警告あり | `accept_with_warning` |
| critical 候補あり または 平均スコア < 閾値、かつ 再生成回数 < 上限 | `regenerate`（= retry。問題候補のみ部分再生成） |
| 上限到達 かつ 採用可能（非critical）候補がいずれかの試行に存在 | `accept_with_warning`（critical 候補は除外され `rejected` に理由付きで記録） |
| 上限到達 かつ 採用可能候補なし | `reject`（全除外） |
| 生成処理エラー | `fail_soft`（Step 3 と同じ。使える試行があればそれを返す） |

再生成上限は従来どおり `LANGGRAPH_GENERATION_MAX_RETRIES`（既定 1、
推奨 1〜2）。閾値は `LANGGRAPH_QUALITY_THRESHOLD`（既定 0.7）のままです。

## 部分再生成（regenerate_candidates）

- 現試行のうち「非critical かつ 単体スコア ≥ 閾値」の候補はそのまま維持
- プロバイダには現試行の全タイトルを回避リストとして渡し、
  不足分（`factor_count - 維持数`）だけを新規候補から採用
- 例: 3件中1件だけ言い換え → その1件のみ差し替え、残り2件は再生成なし
- ゲートOFF時は従来どおり全件再生成

## ログ（PowerShell比較用）

| ログ行 | 追加内容 |
|--------|---------|
| `langgraph candidate \| parent_id=… level=… attempt=… title=… score=… severity=… excluded=… warnings=… critical_reasons=…` | **新設**: 候補1件ごとの評価 |
| `langgraph decide \| decision=… basis=… severity=… critical_count=…` | basis（pass / budget_spent）と critical 件数を追加 |
| `langgraph regen partial \| kept=… before=… after=…` | **新設**: 部分再生成の維持・除外・追加タイトル（before/after） |
| `langgraph reject candidate \| title=… reasons=…` | **新設**: 最終的に除外された候補と理由 |
| `langgraph run summary \| … severity=… rejected=… regen_titles=… elapsed_ms=…` | 最終判定・除外数・再生成由来タイトルを追加 |
| `generate_factors workflow \| … rejected_by_gate=… regenerated_created=…` | リクエスト単位の集計を追加 |

## CSV / API レスポンスへの反映

- CSV 末尾に「品質ステータス」列を追加（既存列の位置は不変）:
  `警告のみ` / `再生成` / `再生成（警告あり）` / 空欄（問題なし）
- 再生成で生成された要因の `warning_flags` に「再生成により生成」を追記
- 除外（reject）された候補はノードとして保存されないため CSV には
  出ません。件数・理由は generate レスポンスの
  `quality_summary.rejected_by_gate` / `reason_summary` とログで確認できます
- `quality_summary` に `rejected_by_gate` / `regenerated_created` を追加
  （既存キーは不変・追加のみ）

## テスト

- `tests/test_quality_gate_rules.py`（新規）: severity 分類、段階判定、
  部分再生成、reject、再生成上限、汎用語一致の非critical、ゲートOFF回帰
- `tests/test_quality_gate_workflow.py` / `tests/test_generate_endpoint.py`:
  仕様変更（budget_spent 時 fail_soft → accept_with_warning / reject）に
  合わせて更新、エンドポイント統合テストを追加
- `tests/test_export_service.py`: 品質ステータス列のテストを追加

```powershell
cd fta_tool
pytest tests/ -v
# ルール関連のみ
pytest tests/test_quality_gate_rules.py tests/test_quality_gate_workflow.py -v
```

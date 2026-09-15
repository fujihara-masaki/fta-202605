# Step 4: Quality Gate 高速化・判定ロジック改善計画

## 0. 文書の位置付け

本書は **現実装の静的調査と後続実装の計画** である。Step 4 のプログラム、テスト、プロンプト、設定、DB、UIにはまだ変更を加えない。速度・品質に関する数値は未計測であり、改善率や閾値を確定しない。

### 調査基準

|項目|値|
|---|---|
|採用ブランチ|`claude/fta-analysis-tool-Yg5yn`（依頼指定）|
|作業開始時のローカルブランチ|`work`|
|調査基準 SHA|`7595aaae57073fbb72d02f88a0859d578c5ef474`|
|基準確認日時|2026-09-15T01:49:44Z (UTC)|
|前回参考 SHA|`7595aaae57073fbb72d02f88a0859d578c5ef474`（基準 SHA と同一）|

コンテナには remote / 採用ブランチ ref がなく、`git branch -a` で確認できるのは `work` のみだった。このためネットワークから更新したという意味での「採用ブランチ最新」は確認できず、提供済み作業ツリーの HEAD を調査基準とした。巻き戻し、未コミット変更の破棄、採用ブランチへの切替・直接変更はしていない。同名文書およびその履歴は存在しなかった。参照不能な過去会話、添付、実運用ログは確認済みとして扱わない。

### 実施 / 未実施

* 実施: 指定ソース、設定、文書、比較キット、関連テストの静的調査、既存の非 LLM テスト実行、計画書作成。
* 未実施: 実 LLM、通常利用 DB、実画面、性能測定、閾値調整、新規モデル取得、外部 LLM、コード・プロンプト・設定の変更。

## 1. 目的、範囲、非対象

品質確保を維持しながら、不要な再生成、必要数を超える出力、重複評価を減らす。同時に「親の言い換え」「祖先への逆戻り」「重複」を排除しつつ、語句を共有する妥当な直接原因の具体化を誤棄却しない判定へ段階的に移行する。頂上事象、`system_context`、`incident_context` の分離保存・入力と、生成直前に DB から読み直した最新 `analysis_context` を渡す経路は維持する。

今回の成果物は本書だけである。実装、テスト追加、プロンプト、`.env*`、既定値、依存、スキーマ、DB、UI、比較スクリプトは非対象。マルチエージェント、追加 LLM 判定、並列化、モデル変更は初期改善の必須条件にしない。

## 2. 現在の処理経路

### 2.1 API から保存・出力まで

1. UI の `generateFactors` / `generateFactorsSequential` / `generateAdditional` が `POST /analyses/{id}/generate/level/{level}` を呼ぶ。追加生成は `additional:true`。
2. `main.generate_factors` が `_get_factor_count` で一次～三次または追加生成の目標件数を決め、一次は頂上事象を暗黙の親、二・三次は指定親または前階層の Yes ノードを親にする。したがって No の親は一括下位生成対象外。
3. 同関数はノードを読み、親パス、同一親・同一階層の既存名、全階層の No 評価名、頂上事象＋直近親を除くパスを祖先名として構成する。`_parse_analysis_context` で最新 DB 値を読み、`_call_ai(extra_existing)` がそれらと元の `factor_count` を全プロバイダ共通 `AIProvider.generate_factors` に渡す。
4. LangGraph OFF なら legacy 経路。`_call_ai([])` 後、件数不足条件に該当すれば一度だけ `_call_ai([既出タイトル])` を実行し、タイトル完全一致を除いて併合、最後に `factor_count` へ切り詰める。
5. LangGraph ON なら `run_generation_workflow` → `generate_candidates` → `validate_structure` (`validate_candidate_structure`) → `evaluate_quality` (`evaluate_candidates`) → `decide_next_action`。終端は `finalize_result`、再生成なら `regenerate_candidates` から構造検証へ戻る。
6. ワークフロー結果の各候補について保存前に `crud.node_title_exists`（分析・親・階層・タイトル）を確認し、再度 `evaluate_candidate` を実行する。除外でなければ `crud.create_node`。保存の最終条件は、DB 完全一致でなく、保存前 E1/E2/E3 に非該当であること。平均スコアや warning 単独は legacy では保存を止めない。Gate ON ではワークフローが critical を候補集合から先に落とす。
7. `quality_summary` とメッセージを API 返却し、ログには provider、候補、判定、親単位、リクエスト単位の行を出す。UI は全除外、通常の 0 件、警告を区別する。保存ノードは `export_json`、`export_csv`、`export_markdown` へ出力される。CSV の末尾には品質ステータスがあり、JSON は `warning_flags` と分析 context を維持するが、除外候補は保存されないのでエクスポートされない。

### 2.2 フラグ・階層・追加生成

|設定|実効経路|再生成|
|---|---|---|
|LangGraph OFF / Gate OFF|legacy|provider 内 retry ＋条件付き件数不足 retry|
|LangGraph OFF / Gate ON|**legacy**。`quality_gate_enabled = langgraph_enabled and ...` のため Gate フラグは無効|同上|
|LangGraph ON / Gate OFF|ワークフロー|`created/partial` は accept、全除外/0件だけ上限まで全体再生成。legacy 件数不足 retry は迂回|
|LangGraph ON / Gate ON|段階 Gate|critical または平均スコア不足で上限まで部分再生成|

一次～三次は同じ API / ワークフロー / 閾値を通る。違いは親・祖先・対象となる Yes 親、階層名、設定件数、プロンプト上の粒度指示である。追加生成も同じ品質経路で、件数だけ `FTA_ADDITIONAL_FACTOR_COUNT`、既存兄弟名も prompt/context に入る。一律に三次だけ緩和する分岐は現存しない。

### 2.3 呼び出し種別と上限

* **provider 内部 retry**: Ollama の通信、timeout、5xx、空応答、JSON/shape、0件等。初回＋`OLLAMA_GENERATION_MAX_RETRIES`（既定追加 1）。Azure / HTTP Copilot は独自の単発通信でこの retry を共有しない。Mock は通信しない。
* **Gate 再生成**: LangGraph 初回＋`LANGGRAPH_GENERATION_MAX_RETRIES`（既定追加 1）。各論理呼び出しの内側で Ollama retry が発生し得る。
* **legacy 件数不足 retry**: 初回後に最大 1 回。各回の内側に provider retry があり得る。
* **workflow failure の legacy fallback**: `WorkflowResult.error` または graph 呼出し例外時に legacy 一式を追加実行する。初回 workflow provider 呼出しが内部 retry を使い切った後、fallback が再び provider 内 retry と件数 retry を行い得る。

現状はリクエスト全体の総 LLM 回数・時間予算を統合管理しない。既定値なら、親 1 件で ON/Gate ON の通常最大は論理 2 呼出し×Ollama 最大2通信=4通信、初回 workflow が完全失敗して fallback へ入るとさらに legacy 最大2論理呼出し×各2通信が加わり得る（実際の分岐次第で最大値は異なる）。API の親が複数なら親数倍となる。

## 3. 現行の構造・品質判定

### 3.1 provider 前処理と構造検証

Ollama は `_normalize_factors` / Pydantic 検証後に `filter_generated_factors` で空・汎用名、親酷似、バッチ内**完全一致**、空/自明な説明を落とし、元の `context.factor_count` に切り詰める。Mock は件数のみ尊重する。Azure の prompt は固定 5 件で context（件数、既存、No、分離 context）を使わず、HTTP Copilot は context を外部へ透過する。よって「全プロバイダが同じ要求件数・理由を理解する」という契約はない。LangGraph の `validate_candidate_structure` は非空 title、文字列群、リスト形状を候補単位で検証する。

### 3.2 ルール、スコア、severity

`normalize_title` は NFKC、小文字化、空白・句読点除去後、欠如/不足/誤り/未実施/否定形等の接尾辞を反復除去する。`similarity` は `SequenceMatcher` と4文字以上の包含、`ancestor_similarity` は最長共通部分も使う。これらは表層文字列の近さであり、意味・因果の正しさではない。

|ID|現行条件|legacy|Gate severity / 作用|
|---|---|---|---|
|E1|親との類似 ≥ 0.72|除外|critical|
|E2|親 description と完全一致|除外|critical|
|E3|No 評価名との類似 ≥ 0.78|除外|critical|
|W1|分析内既存名との類似 ≥ 0.82|警告保存|critical、Gate ON では再生成/最終除外|
|W4|title-like 祖先との `ancestor_similarity` ≥ 0.70|警告保存|critical、Gate ON では再生成/最終除外|
|W5|No 評価名と distinctive token 共通|警告保存|warning|
|W2/W3|汎用名 / 30文字超|警告保存|warning|

`compute_factor_score` は直接原因20%、親子25%、重複15%、具体性15%、階層15%、表現10%の加重値。除外候補は最大30。候補単位 judgment は pass / warning / retry_recommended / fail。Gate の `quality_score` は **kept 全候補（critical warning を含む）** の overall 平均/100だが、`critical_count > 0` は平均より優先して再生成する。非critical かつ候補単位スコアが閾値以上だけが `regen_keep`。最終的な保存は severity/平均を直接再計算するのではなく、workflow の集合選択後に保存前 E/W 評価と DB 重複確認を行う。

### 3.3 文書・コメントとの差

* `langgraph_quality_gate_rules.md` は「不足分だけを新規候補から採用」と表現するが、実装は provider に元の `factor_count` を要求し、返答後 `max(1, factor_count-len(keep))` に切り詰める。部分保持は実装済みだが**部分件数要求は未実装**。
* `generation_config.langgraph_quality_gate_enabled` の docstring と Step 3 文書の旧分岐表は上限時 `fail_soft` と書くが、Step 3.5 実装は usable があれば `accept_with_warning`、なければ `reject`。新しい rules 文書とコードが基準。
* workflow 冒頭コメントは `fail_soft` を accept と同じ終端のように記すが、Gate ON の `finalize_result` の critical 除去処理は accept / accept_with_warning / reject にしか適用されない。
* `evaluate_candidates` は kept title を逐次追加するので同一バッチの近似重複を検知する。一方 main の保存前ループも保存ごとに `all_analysis_titles` を増やし同様に検知する。これはコメントと整合するが二重計算である。
* prompt_loader の説明は analysis context を「sample-scenario context」と呼ぶが、UI から手入力・更新も可能。機能上は最新値が渡る。

## 4. 確認済み課題、疑い、実測待ち

### 4.1 確認済み（コード経路で再現可能）

1. **余剰生成**: Gate ON の部分再生成で `regenerate_candidates` は `fn(avoid_titles)` のみを呼ぶ。`main._call_ai` は常に元の `factor_count`、Ollama prompt/provider 上限にも元件数を渡し、返答後だけ不足相当へ切る。正常2＋問題1、目標3なら1件必要なのに3件要求する。
2. **不足0でも最低1件採用し得る式**: 切詰めが `max(1, factor_count-len(keep))`。通常再生成判定時は問題があるため不足>0の想定だが、状態組合せ・将来変更に対する0件短絡がなく、不要呼出し防止契約もない。
3. **品質評価の重複**: workflow の全候補を評価後、main が保存候補を再評価する。DB/先行親/同一バッチで集合が更新された後の再検査は必要だが、親・No・祖先など不変部分も再計算する。
4. **provider 契約差**: 不足件数を追加しても Mock/Ollama/Azure/HTTP、テスト stub の全てへ同じ意味で届くとは限らない。特に Azure は固定5件・context未使用。
5. **理由不足**: 再生成に渡るのは現試行全 title を `existing_titles` に足す回避情報だけ。不足件数、候補別拒否理由、比較相手、severity、維持候補、試行番号、過去の全 NG は構造化して渡らない。
6. **Gate ON fail_soft の critical 復帰経路**: 再生成 provider が失敗し以前の attempt に `kept_count>0` があると `finalize_result` は error を消して `fail_soft` とし、best attempt の raw `candidates` を返す。Gate 用の非critical 集合採用は `fail_soft` を対象外とする。祖先/既存類似は保存前評価では warning に戻るため、通常 Gate なら落とす critical が保存され得る。これは静的に確認した安全性不具合候補であり、まず回帰テストで実証してから修正する（E1/E2/E3 は保存前にも除外されるため同じ漏れ方ではない）。
7. **一括時間予算なし**: retry 群は別々の上限で、総通信回数・wall-clock deadline・キャンセル停止条件がない。

### 4.2 疑い（テスト・データで確認する）

* suffix 除去が「未故障/正常」「部品A/B」「有効/無効」等の重要状態差や否定を潰し、誤った高類似を作る可能性。現リストが常にこれらを消すと断定はしない。
* SequenceMatcher/包含/最長共通部分は、親語句を保持した妥当な具体化を言い換え・逆戻りと誤認し得る一方、語彙の異なる真の言い換えを見逃し得る。
* W1 は全分析タイトル対象なので、別枝に正当に存在する類似事象も Gate ON で critical になる可能性。DB 重複は同一親・階層・完全タイトルで、W1 の目的と範囲が異なる。
* No 評価の理由/親/階層を持たず全階層タイトルだけ比較するため、同一仮説の再出力と、別親で同系統語を含む別仮説を十分区別できない。
* 全除外、とくに三次全除外が正しい除外か誤棄却かは、候補・親・祖先・比較対象・人手ラベルを含む実データがないため判断不能。全除外の事実だけを不具合としない。

### 4.3 実測待ち仮説

不足件数を provider/prompt まで渡せば生成 token と推論時間が減る、理由付き再生成で同じ失敗と再試行が減る、評価キャッシュで Gate CPU 時間が減る、という3点は仮説である。LLM latency が支配的か、短い要求でも同量を返すか、prompt 増分が相殺するかを測るまで改善率を断定しない。

## 5. 改善案の比較と採用順

|案|採否|根拠|副作用・見送り理由|
|---|---|---|---|
|要求件数を `requested_count=max(0,target-len(keep))` として provider/prompt まで伝播|**第一候補**|判定ルールを変えず最大の余剰生成源を直接削る|全 provider/stub の契約更新、過少返答時の扱いが必要|
|不足0で provider 呼出しを短絡|**採用**|不要通信を確実に0にする|既存候補が本当に保存可能か集合更新後検査は残す|
|評価結果を候補 fingerprint＋比較集合 version で再利用|**採用候補**|不変比較の重複を削る|DB保存後に W1/DB 結果が変わるため無条件キャッシュ不可|
|関係型の段階判定（exact identity / paraphrase / causal refinement / ancestor reversion / cross-branch similarity）|**採用候補**|表層類似を意味・因果の真偽にしない|初期は決定論的特徴＋境界を warning にし、人手データなしで閾値確定しない|
|三次だけ閾値緩和 / 全件通過|見送り|見かけの全除外率を下げるだけで品質保証を損なう|階層別データから必要性が示された場合のみ再検討|
|追加 LLM judge、モデル変更、並列生成|初期見送り|費用・非決定性・運用複雑性を増やす|ルール/件数/停止条件改善後の別評価|

### 5.1 要求件数 API 案

`generate_fn` を曖昧な `Callable[[avoid_titles], ...]` から、後方互換な request object（`requested_count`, `avoid_titles`, bounded `rejection_feedback`, `attempt`）へ段階移行する。移行中は adapter で旧 stub を支える。`main._call_ai` は request の件数で `context.factor_count` を上書きし、Ollama の `{desired_count}/{min_count}` と切詰め、Mock、Azure prompt、HTTP context に伝える。初回は target、再生成は shortfall。

* shortfall = `max(0, target_count - len(valid_keep))`。
* 0なら LLM を呼ばず keep を返す。target≤0も明示的に0。
* provider が過少なら返った一意候補だけを併合し、予算内でのみ次試行。過剰なら構造/品質評価前に闇雲に切らず、上限を設けた上で評価し、合格候補から不足分だけ採る方針を比較する。
* keep、fresh、最終集合を全て target 以下にする。fresh が avoid/keep/同一返答内と exact duplicate なら除外し、近似は関係型判定へ。
* 正常候補の object と順序を保持し、再生成由来フラグは fresh の採用分だけ。
* 全 provider が requested_count を尊重したか `requested/returned/accepted/truncated` を記録し、尊重不能な外部 provider は capability として明示する。

### 5.2 判定改善案

単一 similarity 値を verdict にせず、比較の**スコープ**と保持された意味差を入力にする。

1. 正規化は表示用、exact canonical、比較用 token の段階に分け、原文も保持する。否定、正常/故障、有効/無効、未/済、部品・系統 identifier を protected feature とし、差があれば同一視しない。正規化の before/after と寄与ルールをテスト可能にする。
2. 親比較は「共通核」だけでなく、子に追加された状態/機序/条件が `子→親` の原因として説明できるかを決定論的な cue と固定 fixture で分類する。確証できない境界は critical でなく `needs_review` warning を第一案とする。
3. 祖先は exact/canonical reversion、語句共通＋新しい下位 mechanism、単なる cross-level similarity を分離。ancestor title と system/incident context は今後も混ぜない。
4. 重複 scope を `same_batch`、`same_parent`、`cross_branch`、`database_exact` に分離。同一親・同一仮説は強く、別枝類似は原則 warning。DB exact 防止は常に保存直前に残す。
5. No は title だけでなく可能なら元 node id、親、階層、No 理由を参照し、同一仮説と同系統別仮説を分ける。既存データに理由がない場合は unknown とし、系統語一致だけは引き続き warning。
6. severity を `critical`（根拠が明確で保存不可）、`uncertain/needs_review`（再生成候補だが予算終了時の扱いを別定義）、`warning`、`ok` にする。候補単位 verdict を先に決め、平均スコアだけで critical を相殺しない。平均は観測指標、候補単位 score は優先順位補助に限定する案を比較する。

最終保存条件は `(structure valid) AND (criticalでない) AND (DB exact duplicateでない) AND (最新集合に対する必須再検査を通過)`。uncertain の保存可否は feature flag と人手データで決め、理由・severity を必ず保持する。

## 6. 再生成、停止、fallback 設計

### 6.1 理由付き再生成

各 NG について `candidate_title`, `rule_id`, `severity`, `reason_label`, `compared_scope`, `compared_title`（必要時だけ）、`attempt` を構造化する。prompt には今回置換する候補の短い理由、回避 title、維持 title、requested_count を上限付きで渡す。過去 NG は canonical fingerprint で重複排除し、直近 N 試行/文字数上限を設ける。説明全文・全分析履歴・秘密情報は無制限に入れない。

追跡レコードには candidate id/fingerprint、origin attempt、requested/returned、判定履歴、最終保存有無と node id（保存時）、regen origin を持たせる。既存 API キーと CSV 列は削除・改名せず追加項目/末尾列に限定する。UI の「再生成由来」と「品質警告」を別フィールドにし、当面 `warning_flags` の既存表示との adapter を保つ。

### 6.2 予算と停止条件

親単位の `max_logical_generation_calls`、`max_provider_attempts`、wall-clock deadline、target_count を一つの budget object で管理する。既定値の変更は計測後。停止は、(a) target の保存可能候補確保、(b) shortfall=0、(c) retry/通信/時間予算到達、(d)同一 NG fingerprint の連続再出力、(e)非retryable error。回数は initial、Gate regen、provider retry、legacy fallback を別カウンタと総数の両方で記録する。

### 6.3 fail-soft / fallback 安全性

* Gate ON はどの終端（provider error を含む）でも `final_candidates = noncritical usable subset` という一つの sanitizer を必ず通す。raw/best attempt を直接保存層へ返さない。
* 再生成失敗時は正常 keep のみを warning 付きで返し、critical は `rejected` に残す。正常候補ゼロなら reject。fallback は「生成インフラ全体が初回から失敗し候補ゼロ」等に限定する。
* fallback しても Gate policy を外して critical を復活させない。legacy 生成結果にも、Gate ON リクエストなら最終 sanitizer を適用する。
* 既存集合の更新後に、DB exact、同一バッチ/親 duplicate、保存必須 rule だけ再検査する。不変なスコア計算は再利用し、比較集合 version が変わる W1 等だけ差分再評価する。

## 7. 互換性、ログ・集計・出力

保持するもの: API URL/既存 response key、`GeneratedFactor`、通常 DB schema、既存 CSV 列順、JSON/Markdown、warning表示、分離 context、追加生成、OFF/OFF と OFF/ON の legacy 実効性。

追加候補: `generation_id`, 親/階層、attempt、call_kind、provider_attempt、requested_count、returned_count、kept/rejected/saved、shortfall、token 数、initial/regen/gate/total elapsed、stop_reason、fallback_reason、rule_id/severity/scope、final_saved。ログに prompt 本文、秘密、業務実データを残さない。時間単位は wall-clock `ms`、Ollama duration は元値 ns と変換後 ms を明記する。API/CSV に新情報を出す場合は追加のみとし、旧 consumer fixture を回帰試験する。

現比較 analyzer はログと export から時間、decision、品質等を集約する基盤として再利用する。要求数、呼出種別/総数、token、全除外の分母、誤棄却/見逃し、人手ラベル列だけを後続 PR で拡張する。

## 8. 試験計画

### 8.1 現状固定（characterization）

既存期待値を書き換える前に、現 SHA で以下を別 suite に記録する: 部分保持するが provider 要求は元件数、0短絡なし、OFF/ON=legacy、Gate OFF 全除外 retry、legacy不足 retry、provider retry、workflow fallback、保存前再評価、三次全除外 response。fail_soft critical 復帰は専用 regression で「現状の危険な結果」を実証し、改善後 suite と混同しない。

### 8.2 固定候補の純粋判定試験

* 対: 拒否すべき親の語尾言い換え / 採用すべき具体的機序、祖先 exact reversion / 祖先語を含む妥当な下位原因。
* NFKC、句読点、suffix、否定、正常対故障、有効対無効、部品A対B、閾値直下/一致/直上。
* 一次～三次と追加生成の同一 fixture、同一親重複、同一 batch exact/near duplicate、別枝類似。
* No の同一仮説、同じ系統語だけの別仮説、異なる親/階層。
* critical / uncertain / warning / ok、候補 score、平均 score、最終保存 predicate を個別に検証。

期待動作 suite は、具体化を保持、表層語句だけで因果を断定しない、三次一律緩和なし、critical を平均で救済しないことを定義する。

### 8.3 stub ワークフロー / API

全 provider adapter と旧 callable stub の契約を対象にする。

* shortfall 0（呼出0）、正常2＋問題1（要求1、正常object維持）、過少0/要求未満、過剰、avoid候補再出力、同一 batch 重複、target上限。
* 全除外、全構造不正、再生成例外、初回例外、fallback、retry budget/deadline、同一NG停止。
* fail_soft/fallback の全終端で critical 非復帰、usable 正常候補は保持。
* OFF/OFF、OFF/ON、ON/OFF、ON/ON、一次～三次、追加生成、複数親。
* context 更新 API 後の最新 `system_context` / `incident_context` が次生成に渡り、top_event と別フィールドのままであること。
* API 既存 key、全除外 message、ログ、JSON/CSV/Markdown列、regen表示とwarning表示の互換。

### 8.4 実 LLM 比較（別 PR、承認環境のみ）

主比較は同一基準入力による **改修前 ON/Gate ON 対 改修後 ON/Gate ON**。OFF/OFF、OFF/ON（実効legacy）、ON/OFF は回帰・対照。既存 `run_langgraph_comparison.ps1` と `analyze_langgraph_comparison.py` を再利用する。

二・三次の局所比較は同じ親 title、親 description、祖先、既存候補、No、system/incident context、目標件数を固定する。別の上位生成結果から得た親を「同一入力」にしない。これと、一次から三次まで進む全階層 E2E を別集計する。自動 Yes は進行操作であり正解ラベルではない。

記録するメタデータ: before/after commit、branch、日時、OS/CPU/RAM、Python/Ollama/model名・digest、温度/context/predict、全関連 env（秘密はmask）、scenario/input hash、DB識別子、実行順、seed、warmup、反復数、欠測理由。PowerShell 5.1 のスクリプトは UTF-8 BOM と CRLF を保持し、`.env` を例外時も退避復元、実行ごとの専用作業 dir/SQLite DB を使う。モデル取得・切替はしない。

指標は Gate CPU、initial LLM、regen LLM、provider retry、全体 wall time (ms)、論理/物理呼出数、requested/returned、prompt/output token、保存数、全除外率（親を分母）、誤棄却、見逃し、人手品質。全除外で次階層の親が減ったための E2E 短縮を高速化に数えず、固定親局所値と生成対象親数を併記する。全除外例は専門家が候補ごとに correct reject / false reject / undecidable を付ける。少数反復から p95 や統計的有意差を主張せず、生値・中央値/範囲と欠測を示す。

### 8.5 実画面

実装最終段階で、分離 context 編集→未保存時の自動保存→一次/二次/三次/追加生成、全除外通知、再生成由来表示、品質警告詳細、export download を専用 DB・非機密ダミーデータで確認し、変更が知覚可能ならスクリーンショットを証跡化する。

## 9. 実装 PR 分割

実在しない番号は付けない。

1. **計測・再現**: characterization、fail_soft安全性再現、requested/returned/call-kind/時間/token計測と analyzer 最小拡張。非対象=判定・prompt変更。完了=現状が再現でき欠測定義と before 基準が取れる。
2. **判定ルールを変えない生成コスト改善**: request object/adapter、shortfall伝播、0短絡、上限・過少/過剰、全 provider/stub。非対象=severity/閾値変更。完了=既存判定結果同等、正常候補保持、呼出/要求数テスト合格。
3. **判定改善**: protected semantics、scope別duplicate、親具体化/祖先/No分類、severity。非対象=理由prompt/fallback変更。完了=固定 gold fixture、人手レビュー、旧新判定差分説明。
4. **理由付き再生成・異常系**: bounded feedback、停止budget、統一final sanitizer、fail_soft/fallback安全化、追跡ログ/API additive metadata。非対象=モデル/DB schema/UI刷新。完了=全異常終端でcritical非保存、互換試験合格。
5. **実 LLM 比較**: 比較キット必要最小拡張、主比較・対照・固定親・E2E、人手評価報告。非対象=測定中の閾値後付け調整、モデル変更。完了=再現メタデータ、生値、欠測、品質/速度双方の判断と採否提案。

依存は 1→2、1→3、2+3→4、全て→5。2と3は基準 fixture を固定後なら並行可能だが、同一 PR に混ぜず効果帰属を保つ。

## 10. 受入基準、ロールバック、未決事項

### 10.1 受入基準

* target N、keep K に対し要求が `max(0,N-K)`、0時通信なし、保存候補≤N。全 provider/旧stub互換。
* 正常候補を再生成せず、avoid再出力/過少/過剰/失敗でも重複・critical を保存しない。
* 固定 fixture で言い換えと具体化、逆戻りと語句共有具体化、scope別重複、No同一仮説と別仮説、protected状態差を区別する。境界は明示的 uncertain。
* DB exact と最新集合に依存する保存前検査は維持し、不変評価だけを安全に再利用。
* API/export/context/OFF系が回帰せず、総呼出数と停止理由が監査可能。
* 実測で品質非劣化を人手確認し、速度効果は固定親・同一条件で報告。数値合格線は PR1 の baseline と必要データから承認して確定する。

### 10.2 ロールバック

PR ごとの feature flag / adapter で旧 requested-count、旧 rules、理由feedbackを独立に戻せるようにする。ただし critical 復帰防止 sanitizer は安全修正として、ロールバックより hotfix を優先する。DB migrationを初期案に含めず、API追加キーとログは旧 consumerが無視可能にする。rollback時も分離 context と保存前DB重複防止を外さない。

### 10.3 未決事項・必要データ

* 実環境の provider とモデル、件数設定、親数、retry発生率、token/latency分布。
* 一～三次ごとの候補、親説明、祖先、比較scope、No理由を含む匿名化 gold set。特に三次全除外例。
* false reject / miss の業務許容度と uncertain の保存/表示方針。
* protected語彙、形態素処理の必要性、cross-branch類似の扱い、No評価の有効範囲。
* requested_countを尊重できない外部 HTTP provider の capability/バージョニング。
* 総呼出/時間budgetと数値受入線。根拠データなしに現時点で確定しない。

三次要因の全除外について、現リポジトリには正しい除外と誤棄却を判定できる実候補・人手正解がない。まず必要データを採取・匿名化し、全除外率だけでなく候補単位 confusion と undecidable を報告する。

## 11. 参照ファイル・関数・資料

|領域|参照|
|---|---|
|品質ルール|`app/services/factor_quality.py`: `normalize_title`, `similarity`, `ancestor_similarity`, `evaluate_factor`, `compute_factor_score`, `classify_warning_severity`, `evaluate_candidate(s)`, `classify_outcome`|
|workflow|`app/services/generation_workflow.py`: `generate_candidates`, `validate_structure`, `evaluate_quality`, `decide_next_action`, `regenerate_candidates`, `finalize_result`, `run_generation_workflow`|
|設定|`app/services/generation_config.py`|
|provider|`app/services/ai_provider.py`: `AIProvider.generate_factors`, 各 provider、Ollama `_build_prompt`/`_generate_once`/retry/`filter_generated_factors`|
|構造|`app/services/llm_models.py`: `CandidateStructure`, `validate_candidate_structure`, `GenerationMetrics`|
|prompt|`app/services/prompt_loader.py`, `config/prompts.yaml`|
|API/保存/context|`app/main.py`: context endpoints、`generate_factors`; `app/crud.py`: `node_title_exists`, `create_node`|
|UI/出力|`app/static/app.js`; `app/services/export_service.py`|
|既存資料|`docs/langgraph_step3.md`, `docs/langgraph_quality_gate_rules.md`, `docs/langgraph_comparison_test.md`|
|比較キット|`scripts/run_langgraph_comparison.ps1`, `scripts/analyze_langgraph_comparison.py`|
|関連試験|`tests/test_factor_quality.py`, `test_candidate_evaluation.py`, `test_generation_workflow.py`, `test_quality_gate_rules.py`, `test_quality_gate_workflow.py`, `test_generate_endpoint.py`, `test_ai_provider.py`, `test_ollama_generation.py`, `test_prompt_loader.py`, `test_analysis_context.py`, `test_export_service.py`, `test_analyze_langgraph_comparison.py`, `test_run_langgraph_comparison_script.py`, `test_ui_endpoints.py`|

---

本計画の次工程は PR 1 の計測・再現であり、本書作成に続けて実装、閾値、prompt、mergeを行わない。

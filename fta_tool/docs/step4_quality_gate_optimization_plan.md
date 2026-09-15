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
|PR #12 初回レビュー時の指定 HEAD|`e15f97434d051b6baa624aede2f8434be19f65ea`|
|PR #12 再レビュー時の指定 HEAD|`54133234ad8731ad49c0cbdadc6169ecae99854b`|
|再レビュー反映時のローカル HEAD|`140e6bd8e8a7dccf42be81b4ce72a13f888fedef`|
|再レビュー反映確認日時|2026-09-15T05:42:33Z (UTC)|

コンテナには remote / 採用ブランチ ref がなく、`git branch -a` で確認できるのは `work` のみだった。このためネットワークから更新したという意味での「採用ブランチ最新」は確認できず、提供済み作業ツリーの HEAD を調査基準とした。再レビュー時も指定 PR HEAD はローカル object に存在せず、GitHub は認証/ネットワーク制約で参照できなかったため、依頼文に転載されたコメント ID `4012232549`（“Capture the pre-A baseline within Step4-A”）を正本として扱った。巻き戻し、未コミット変更の破棄、採用ブランチへの切替・直接変更はしていない。参照不能な過去会話、添付、ログを確認済みとして扱わない。

### 実施 / 未実施

* 実施: 指定ソース、設定、文書、比較キット、関連テストの静的調査、既存の非 LLM テスト実行、計画書作成、PR #12 の R1～R3 および追加レビュー `4012232549` の計画への反映。
* 未実施: A0 baselineの採取、A1安全修正、実 LLM、通常利用 DB、実画面、性能測定、閾値調整、新規モデル取得、外部 LLM、コード・プロンプト・設定の変更。

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
|Gate ON 部分再生成の要求件数を `requested_count=max(0,target-len(keep))` として provider/prompt まで伝播|**安全修正後の第一候補**|判定ルールを変えず余剰出力源を直接削る|まず Gate ON/Ollama 境界に限定し、OFF系を一括変更しない。過少・過剰返答の扱いが必要|
|不足0で provider 呼出しを短絡|**採用**|不要通信を確実に0にする|既存候補が本当に保存可能か集合更新後検査は残す|
|評価結果を候補 fingerprint＋比較集合 version で再利用|**採用候補**|不変比較の重複を削る|DB保存後に W1/DB 結果が変わるため無条件キャッシュ不可|
|関係型の段階判定（exact identity / paraphrase / causal refinement / ancestor reversion / cross-branch similarity）|**採用候補**|表層類似を意味・因果の真偽にしない|初期は決定論的特徴＋境界を warning にし、人手データなしで閾値確定しない|
|三次だけ閾値緩和 / 全件通過|見送り|見かけの全除外率を下げるだけで品質保証を損なう|階層別データから必要性が示された場合のみ再検討|
|追加 LLM judge、モデル変更、並列生成|初期見送り|費用・非決定性・運用複雑性を増やす|ルール/件数/停止条件改善後の別評価|

### 5.1 要求件数 API 案

`generate_fn` を曖昧な `Callable[[avoid_titles], ...]` から、後方互換な request object（`requested_count`, `processing_limit`, `target_count`, `avoid_titles`, `attempt`）へ段階移行する。理由 feedback は Step4-E まで入れない。移行中は adapter で旧 stub を支える。次の3値を混同しない。

1. **LLM要求件数 (`requested_count`)**: 初回は target、Gate ON 部分再生成は shortfall = `max(0, target_count-len(valid_keep))`。prompt の `{desired_count}` はこれを表す。これはモデルへの依頼であり、返却処理上限や採用保証ではない。
2. **過剰返答の有限安全上限 (`processing_limit`)**: 応答サイズ/候補数にハード上限を設けるが、通常は `requested_count` より大きい小さな余裕枠を持たせ、品質評価**前**に requested_count へ切らない。値は計測・脅威評価後に確定する。HTTP body、JSON配列、候補文字数にも上限を検討し、無制限処理を許さない。
3. **品質評価後の最終採用件数 (`target_count`)**: keep と合格 fresh から最大 target 件を決定する。fresh が avoid/keep/同一返答内と exact duplicate なら除外し、近似は品質判定へ渡す。

不足1件の返答 `[先頭=critical, 後続=合格]` は、両方が processing_limit 内なら両方を構造・品質評価し、先頭を落として後続を1件採る。provider内部で requested_count=1 に早期切詰めしてはならない。正常候補の object と順序を保持し、再生成由来フラグは採用 fresh のみへ付ける。shortfall=0 / target≤0 は LLM を呼ばず keep を返す。過少なら合格した分だけ併合し、追加試行は既存予算内に限定する。

#### 経路別の変更契約

|経路|LLM要求|provider返却・処理|最終選択|Step4-Cで変更するか|
|---|---|---|---|---|
|初回生成（Gate ON）|従来どおり target|processing_limit 内を評価層へ渡す。Ollamaの現行 `factor_count` 早期切詰め責任を分離|品質後に target 以下|必要な共通境界だけ。生成意味は維持|
|Gate ON 部分再生成|**targetからshortfallへ変更**|requested_countでは切らず有限余裕枠まで返す|keep＋合格freshをtarget以下|**主対象**|
|LangGraph ON / Gate OFF|従来どおり target|現行の全体再生成と切詰めを維持|現行契約|対象外|
|legacy（OFF/OFF・OFF/ON・fallbackのlegacy部）|従来どおり target、件数不足retryも現状維持|現行provider挙動|現行契約|対象外|

Ollama の `filter_generated_factors` は構文正規化後の軽量 provider 品質filterを担うが、Gate severityを決めない。現行の末尾 `factor_count` 切詰めは、Gate ON 部分再生成に限って `processing_limit` へ置換/迂回し、workflowが候補を評価後に不足数を選ぶ。Mock/Azure/HTTPは、Step4-Cでは Gate ON request adapter の互換試験を行うが、OFF系の出力契約まで一括変更しない。尊重不能な外部providerは capability と requested/returned差を記録する。

要求件数削減で期待するのは主に**出力token・単一推論時間の削減**である。一方、理由付き再生成や停止条件による**論理/物理通信回数の削減**は別仮説であり Step4-E の評価対象。短い要求でも余剰出力するモデルや再試行増加もあり得るため、いずれも実測前に効果を確定しない。

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

### 6.1 最初に行う critical 復帰防止（Step4-A）

Step4-A は同一の実装用PR内で **A0→A1** の順に進める（A0/A1はGitHub PR番号ではない）。A0で修正前baselineを確定してから、**最初の振る舞い変更**であるA1へ進む。Step4-Bの本格的な計測・ログ整備、実LLM長時間測定、理由prompt、件数最適化、総時間予算をA0へ前倒ししない。

#### A0 — 修正前の再現・最小計測・基準データ取得

固定候補、決定論的stub、ダミー入力、実行ごとの専用テストDBを使い、Gate ONのcritical復帰とGate OFFの現状をcharacterization testで固定する。既存ログと、テストstub/spyがメモリ内に記録する呼出しを優先する。不足する場合に加える観測処理はテスト専用hookまたは内容非依存の最小イベントに限り、生成要求、判定、候補選択、保存条件、再試行条件を変えない。A0の結果artifactを保存・レビューしてからA1コミットを作る。

**baseline識別子とSHA:**

* `pre_a_code_sha`: A0開始時の修正前コードSHA。計画作成時点ではPR HEADとして指定された `54133234ad8731ad49c0cbdadc6169ecae99854b` を候補とするが、実施時にPR最新HEADを取得して確定し、manifestへフルSHAを記録する。
* `a0_observation_sha`: テスト/最小観測処理を追加したA0コミットSHA。コード変更なしで既存ログ・テストspyだけで足りる項目は `pre_a_code_sha` と同一でもよい。異なる場合は、観測処理が振る舞いを変えないことをcharacterizationで証明する。
* `a1_fix_sha`: final sanitizerを修正したA1コミットSHA。将来の実施時に記録し、未作成の現時点では `not_created` とする。0や推測SHAで埋めない。
* `fixture_version`: 例 `step4-a-critical-reentry-v1`。固定候補、stub応答列/例外列、flag/env、API request、期待する親・祖先・既存/No集合をmanifestに列挙し、A0/A1で同一版を使う。

**A0最小共通指標:**

|対象|取得項目|計測箇所・方法|単位・集計対象|
|---|---|---|---|
|候補集合|attemptごとの入力title識別子、kept/critical/excluded、final candidates|workflow resultとstub/fixtureの対応表。内容はダミー、artifactでは安定ID化|候補件数。1親・1workflow run単位|
|判定|attempt severity、decision、reason rule、outcome|既存`langgraph candidate/decide/run summary`またはテストobject|判定別件数。最終と途中を分離|
|保存結果|created、saved candidate ID、excluded quality/dedup、all-excluded|API response、専用test DB query|ノード件数。親・階層・request単位|
|エラー情報|provider/workflow/fallbackの発生箇所、error kind、API success/message分類|例外stub、既存ログ、API response|イベント件数。raw秘密文字列は保存しない|
|呼出し数|workflow initial、Gate regeneration、legacy fallback、各stub invocation|stub/spyのcall listを正本とし既存retryログで照合|論理呼出し回数。provider内部物理通信は取得できた時だけ別欄|

A0では実elapsed/token、`requested/processed/call_kind`など現行から確実に取れない項目を無理に追加しない。取得不能値はmanifestで `not_collected` とし、0・空文字・推測値にしない。stub所要時間は環境参考値または非収集とし、実LLM性能値に使わない。既存ログ由来、stub由来、DB/API由来、実測値を各列の`source`で区別する。

**保存と再実行:** `fta_tool/test_results/step4_a/<fixture_version>/<pre_a_code_sha>/` 相当のGit管理外ディレクトリに、秘密を含まない`manifest.json`、JUnit、構造化した期待/実結果、sanitized logを保存する。CI artifactを使う場合も保持期限とアクセス制御を設定し、GitHubリポジトリへ結果をcommitしない。再実行コマンド、Python/依存版、env flag、fixture hash、DBパスをmanifestへ記録する。A0/A1で一時ディレクトリと新規SQLite DBを毎回作り、通常利用DBへ接続しない。

修正前コミットを後日再実行する場合は、採用ブランチをreset/revertせず、`git worktree add <temp> <pre_a_code_sha>`等で別作業ディレクトリを作り、その配下の専用DBと仮想環境/固定依存を使う。観測処理が必要なら同じ`a0_observation_sha`のpatchを一時worktreeへ適用した比較用SHAをmanifestに記録する。未コミットpatchの結果を正本にしない。

#### A1 — critical復帰防止

A0と同じ`fixture_version`、stub列、専用DB、コマンド、集計方法でA1を再実行し、候補集合、判定、保存結果、エラー、論理呼出し数をdiffする。期待差分は正常候補保持とcritical非保存、およびAPI/エラー意味の安全な整理だけである。呼出し回数、Gate OFF、生成要求、再試行条件に意図しない差がないことを確認する。A0観測コミットとA1安全修正は同じStep4-A用PRの別コミットとし、レビューで差分を独立確認できるようにする。

次表はA1後の仕様である。現行 E/W判定、閾値、prompt、要求件数、総時間予算は変えない。

|事象|Gate ONの最小修正後|API上の意味|
|---|---|---|
|初回provider失敗、usable attemptなし|生成エラーとして workflow errorを保持し、legacy fallbackを試す。fallbackも失敗ならerror|`success:false`。候補0と品質全除外にしない|
|再生成provider失敗、正常keepあり|正常な非critical keepだけ保持。W1/W4 criticalとE1/E2/E3はrejectedに残す|成功だがpartial/警告。生成エラーを品質rejectに読み替えない|
|再生成provider失敗、正常keepなし|criticalを復帰せずreject|provider error情報と品質全除外を別フィールド/ログで保持。0件（LLM無返却）と区別|
|workflow node/graph例外|例外前の評価済み正常keepだけsanitizer経由で利用。安全に分類不能ならfallbackも同じGate policyで検査|workflow error/fallback reasonを残す|
|legacy fallbackが候補を返す|Gate ON要求である限り現行Gateルールのfinal sanitizerを通す|criticalを保存せず、生成回復と品質結果を別表示|
|品質評価で全件critical|provider errorではなく品質reject|`success:true`, created=0, `all_candidates_excluded:true` と理由|
|LLMが0件返却|品質rejectではなくno_candidates|既存の0件メッセージを維持|

sanitizer は評価済み `kept_noncritical` を入力にし、W1/W4 criticalを排除する。E1/E2/E3は従来どおり除外され、raw candidateやbest attemptを直接保存へ渡さない。正常候補はobject・順序・warningを保持する。初回失敗、再生成失敗、workflow例外、fallbackそれぞれを独立テストし、生成エラー情報と品質結果の両方を失わない。

**Gate OFF条件**: `quality_gate=false` の `fail_soft`、全体再生成、best attempt選択、legacy fallback、E1/E2/E3保存前除外、W1/W4警告保存、APIメッセージを変更しない。共通関数化しても Gate ON branchだけで sanitizerを有効化し、OFF/OFF、OFF/ON、ON/OFFのcharacterizationを受入条件にする。

### 6.2 理由付き再生成（Step4-E）

各 NG について `candidate_title`, `rule_id`, `severity`, `reason_label`, `compared_scope`, `compared_title`（必要時だけ）、`attempt` を構造化する。prompt には今回置換する候補の短い理由、回避 title、維持 title、requested_count を上限付きで渡す。過去 NG は canonical fingerprint で重複排除し、直近 N 試行/文字数上限を設ける。説明全文・全分析履歴・秘密情報は無制限に入れない。

追跡レコードには candidate id/fingerprint、origin attempt、requested/returned、判定履歴、最終保存有無と node id（保存時）、regen origin を持たせる。既存 API キーと CSV 列は削除・改名せず追加項目/末尾列に限定する。UI の「再生成由来」と「品質警告」を別フィールドにし、当面 `warning_flags` の既存表示との adapter を保つ。

### 6.3 予算と停止条件（Step4-E）

親単位の `max_logical_generation_calls`、`max_provider_attempts`、wall-clock deadline、target_count を一つの budget object で管理する。既定値の変更は計測後。停止は、(a) target の保存可能候補確保、(b) shortfall=0、(c) retry/通信/時間予算到達、(d)同一 NG fingerprint の連続再出力、(e)非retryable error。回数は initial、Gate regen、provider retry、legacy fallback を別カウンタと総数の両方で記録する。

### 6.4 fail-soft / fallback の最終形

* Gate ON はどの終端（provider error を含む）でも `final_candidates = noncritical usable subset` という一つの sanitizer を必ず通す。raw/best attempt を直接保存層へ返さない。
* 再生成失敗時は正常 keep のみを warning 付きで返し、critical は `rejected` に残す。正常候補ゼロなら reject。fallback は「生成インフラ全体が初回から失敗し候補ゼロ」等に限定する。
* fallback しても Gate policy を外して critical を復活させない。legacy 生成結果にも、Gate ON リクエストなら最終 sanitizer を適用する。
* 既存集合の更新後に、DB exact、同一バッチ/親 duplicate、保存必須 rule だけ再検査する。不変なスコア計算は再利用し、比較集合 version が変わる W1 等だけ差分再評価する。

## 7. 互換性、ログ・集計・出力

保持するもの: API URL/既存 response key、`GeneratedFactor`、通常 DB schema、既存 CSV 列順、JSON/Markdown、warning表示、分離 context、追加生成、OFF/OFF と OFF/ON の legacy 実効性。

追加候補: `generation_id`, 親/階層、attempt、call_kind、provider_attempt、requested_count、returned_count、kept/rejected/saved、shortfall、token 数、initial/regen/gate/total elapsed、stop_reason、fallback_reason、rule_id/severity/scope、final_saved。時間単位は wall-clock `ms`、Ollama duration は元値 ns と変換後 ms を明記する。API/CSV に新情報を出す場合は追加のみとし、旧 consumer fixture を回帰試験する。

### 7.1 ログ情報保護（Step4-B、緊急性があればStep4-Aへ前倒し）

現行実装は「入力内容を通常計測ログへ残さない」という目標と未整合である。`OllamaProvider.generate_factors` は完成promptを `logger.debug` へ出し、`FTA_DEBUG_PROMPT=true` ならINFOへ全文出力する。また provider/workflow/main の多数のログが `parent`, `title`, warningの比較相手・理由を `%r/%s` で出し、HTTPエラー本文や例外文字列にも外部レスポンス/入力が混入し得る。これは調査・後続修正対象であり、既に安全とみなさない。

方針は次のとおり。

* 全文promptログを既定/DEBUG/`FTA_DEBUG_PROMPT=true` の全てで削除するか、明示的なローカル診断sink（Git管理外、短期保存、強い警告）へ隔離する。INFOへの昇格機能は廃止候補。
* parent/title/比較相手は `analysis_id`, `parent_id`, `candidate_index`, session内salt付きhash等へID化する。理由は自由文でなく `rule_id` / severity / scopeへ置換する。件数、decision、attempt、時間、token、stop/error kindは維持する。
* 例外は許可リスト化した `error_kind`, HTTP status, retryableだけを通常ログへ出し、response body、URL query、header、exception raw textを出さない。秘密キーは従来どおりsnapshotでmaskし、ログにも同じredactionを共通適用する。
* analyzerは新しい構造化keyを優先し、移行期間だけ旧ログを読めるようにする。content非依存の件数・時間・decision集計を欠落させず、format versionを記録する。
* 人手品質評価に必要な候補内容は通常計測ログから分離し、明示同意された匿名化evaluation artifactへ最小限保存する。アクセス・保存期限・削除手順を定め、実業務データ、秘密、未匿名化内容をGit/GitHub/PR artifactへ登録しない。

Step4-Bで全ログsiteと例外経路をinventoryしredaction testを固定する。ただし全文promptが実運用で有効な場合は、critical復帰防止と同じStep4-A内の独立コミットへ前倒しできる。いずれも生成ロジック変更とは分けて比較可能にする。

現比較 analyzer はログと export から時間、decision、品質等を集約する基盤として再利用する。要求数、呼出種別/総数、token、全除外の分母、誤棄却/見逃し、人手ラベル列だけを後続 PR で拡張する。

## 8. 試験計画

### 8.1 現状固定（characterization）

A0として、既存期待値を書き換える前に、§6.1の`pre_a_code_sha` / `a0_observation_sha`と`fixture_version`を固定し、次を別suiteに記録する: 部分保持するが provider 要求は元件数、0短絡なし、OFF/ON=legacy、Gate OFF 全除外 retry、legacy不足 retry、provider retry、workflow fallback、保存前再評価、三次全除外 response。fail_soft critical 復帰は専用 regression で「修正前の危険な結果」を実証し、A1後の期待動作suiteと混同しない。A0/A1の比較は候補集合・判定・保存・エラー・stub呼出し数を必須とし、実LLM時間/tokenを必須にしない。

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
* 不足1に `[先頭critical, 後続合格]` を返し、有限processing_limit内の後続を評価・採用する。上限超過分は処理せず、requested=1、processed件数、採用=1を別々にassertする。
* 全除外、全構造不正、再生成例外、初回例外、fallback、retry budget/deadline、同一NG停止。
* fail_soft/fallback の全終端で critical 非復帰、usable 正常候補は保持。
* OFF/OFF、OFF/ON、ON/OFF、ON/ON、一次～三次、追加生成、複数親。
* context 更新 API 後の最新 `system_context` / `incident_context` が次生成に渡り、top_event と別フィールドのままであること。
* API 既存 key、全除外 message、ログ、JSON/CSV/Markdown列、regen表示とwarning表示の互換。
* ダミー機密文字列（擬似API key、顧客名、parent/title/context、悪意あるerror body）を入れ、通常INFO、DEBUG、`FTA_DEBUG_PROMPT=true`、timeout/HTTP/JSON/workflow例外の各ログに原文がないことをassertする。一方、event、ID、error kind、件数、時間、tokenが残りanalyzerで集計できることもassertする。

### 8.4 実 LLM 比較（別 PR、承認環境のみ）

主比較は同一基準入力による **改修前 ON/Gate ON 対 改修後 ON/Gate ON**。OFF/OFF、OFF/ON（実効legacy）、ON/OFF は回帰・対照。既存 `run_langgraph_comparison.ps1` と `analyze_langgraph_comparison.py` を再利用する。

二・三次の局所比較は同じ親 title、親 description、祖先、既存候補、No、system/incident context、目標件数を固定する。別の上位生成結果から得た親を「同一入力」にしない。これと、一次から三次まで進む全階層 E2E を別集計する。自動 Yes は進行操作であり正解ラベルではない。

記録するメタデータ: before/after commit、branch、日時、OS/CPU/RAM、Python/Ollama/model名・digest、温度/context/predict、全関連 env（秘密はmask）、scenario/input hash、DB識別子、実行順、seed、warmup、反復数、欠測理由。PowerShell 5.1 のスクリプトは UTF-8 BOM と CRLF を保持し、`.env` を例外時も退避復元、実行ごとの専用作業 dir/SQLite DB を使う。モデル取得・切替はしない。

指標は Gate CPU、initial LLM、regen LLM、provider retry、全体 wall time (ms)、論理/物理呼出数、requested/returned、prompt/output token、保存数、全除外率（親を分母）、誤棄却、見逃し、人手品質。全除外で次階層の親が減ったための E2E 短縮を高速化に数えず、固定親局所値と生成対象親数を併記する。全除外例は専門家が候補ごとに correct reject / false reject / undecidable を付ける。少数反復から p95 や統計的有意差を主張せず、生値・中央値/範囲と欠測を示す。

### 8.5 実画面

実装最終段階で、分離 context 編集→未保存時の自動保存→一次/二次/三次/追加生成、全除外通知、再生成由来表示、品質警告詳細、export download を専用 DB・非機密ダミーデータで確認し、変更が知覚可能ならスクリーンショットを証跡化する。

## 9. 実装 PR 分割

実在しない番号は付けない。

1. **Step4-A — A0修正前baseline → A1 critical復帰防止**: 同じPRの第一コミットA0で固定fixture/stub/専用DB、既存ログ・test spy中心の最小共通指標を取得し、artifactとSHAを固定する。第二コミットA1でGate ON全終端のfinal sanitizerだけを修正して同条件比較する。W1/W4、E1/E2/E3、正常keep、4種の異常を分離。非対象=本格計測、実LLM性能測定、理由prompt、件数最適化、時間budget、判定変更。完了=A0結果をA1前にレビュー済み、Gate ONでcritical非保存、正常keep保持、生成error/0件/全除外が区別され、呼出し数とGate OFFに意図しない差がない。
2. **Step4-B — 本格的な計測・ログ整備**: A1後を高速化比較用baselineとして、requested/processed/returned/accepted、call-kind、時間/tokenを追加。全文prompt・入力由来文字列・raw errorを削除/ID化/redactし、analyzerをformat version対応。非対象=生成・判定変更。完了=機密ダミーテストと旧/新analyzer互換、欠測定義、**A1安全修正後**baseline。
3. **Step4-C — 判定ルールを変えない生成コスト改善**: Gate ON部分再生成だけにrequest object/adapter、shortfall伝播、0短絡、processing_limit、品質後target選択を導入。非対象=OFF系契約、severity/閾値、理由prompt。完了=正常保持、先頭NG/後続OK、過少/過剰、全provider/stub、呼出/要求数テスト合格。
4. **Step4-D — 判定改善**: protected semantics、scope別duplicate、親具体化/祖先/No分類、severity。非対象=理由prompt/総budget。完了=固定gold fixture、人手レビュー、旧新差分説明。Step4-A sanitizerを迂回しない。
5. **Step4-E — 理由付き再生成・予算管理**: bounded feedback、統合call/time budget、停止条件、追跡metadata。非対象=モデル/DB schema/UI刷新。完了=同一NG停止、全異常終端、互換試験合格。
6. **Step4-F — 実LLM比較**: 比較キット必要最小拡張、改修前/後ON-ON主比較、対照、固定親、E2E、人手評価。非対象=測定中の閾値後付け調整、モデル変更。完了=再現metadata、生値、欠測、品質/速度双方の採否提案。

依存は **A0→A1→B→C→D→E→F** を基本とする。少なくともA1より先にB/C/Dをmergeしない。A0がA修正前baseline、A1再実行が安全修正の比較、B完了時点がC以降の高速化比較用baselineであり、3者を別manifest/SHAで識別する。各段階で直前commit対当該commitを同じ固定fixture/stubで比較し、Fでは元の改修前ON-ONも主比較基準として保持する。A0/A1等は計画識別子でありGitHub PR番号ではない。

Bで初めて得られるrequested/processed/call-kindや詳細時間/tokenは、A0で取得済みとは扱わない。旧版との比較が必要なら、(a) `pre_a_code_sha`の別worktreeへBの観測だけを適用し振る舞い不変を確認した比較用SHAを作る、または(b)旧版を当該指標の比較対象外とする。どちらを採ったかmanifestに記録し、欠測を0で補完しない。

### 9.1 この文書作成時のテスト記録

前回作成時（旧計画コミット）の結果と、レビュー反映時の結果を混同しない。

|時点|コマンド|結果|
|---|---|---|
|前回|`cd fta_tool && pytest tests/ -q`|11 collection errors。`httpx`, `fastapi`, `sqlalchemy`, `pydantic`不足。未実行部分を合格扱いしない|
|前回|`cd fta_tool && pytest -q tests/test_factor_quality.py tests/test_factor_score.py tests/test_analyze_langgraph_comparison.py tests/test_run_langgraph_comparison_script.py`|69 passed, 3 failed, 1 skipped。3 failedはPyYAML不足|
|今回|`cd fta_tool && pytest tests/ -q`|再実行: 11 collection errors。`httpx`, `fastapi`, `sqlalchemy`, `pydantic`不足。依存は変更せず、未収集テストを合格扱いしない|
|今回|`cd fta_tool && pytest -q tests/test_factor_quality.py tests/test_factor_score.py tests/test_analyze_langgraph_comparison.py tests/test_run_langgraph_comparison_script.py`|再実行: 69 passed, 3 failed, 1 skipped。3 failedはPyYAML不足|
|追加再レビュー反映時|`cd fta_tool && pytest tests/ -q`|再実行: 11 collection errors。上記と同じ4依存不足。未収集テストを合格扱いしない|
|追加再レビュー反映時|`cd fta_tool && pytest -q tests/test_factor_quality.py tests/test_factor_score.py tests/test_analyze_langgraph_comparison.py tests/test_run_langgraph_comparison_script.py`|再実行: 69 passed, 3 failed, 1 skipped。3 failedはPyYAML不足|

## 10. 受入基準、ロールバック、未決事項

### 10.1 受入基準

* Step4-AはA0/A1の別コミットで、A0 artifactの`pre_a_code_sha`、必要時の`a0_observation_sha`、A1の`a1_fix_sha`、fixture version/hash、専用DB、再実行コマンド、値のsource/欠測を記録する。A1着手前にA0結果を確定する。
* **最優先**: Gate ONの初回失敗、再生成失敗、workflow例外、legacy fallbackの全てでW1/W4 criticalとE1/E2/E3が保存対象へ戻らず、正常keepは保持される。生成error、no_candidates、品質all_excludedをAPI/ログで区別する。Gate OFFの既存挙動は不変。
* target N、keep K に対し要求が `max(0,N-K)`、0時通信なし、保存候補≤N。全 provider/旧stub互換。
* requested_count、有限processing_limit、品質後target_countが独立し、不足1・先頭NG・後続OKを救済する。OFF系の契約はStep4-Cで変えない。
* 正常候補を再生成せず、avoid再出力/過少/過剰/失敗でも重複・critical を保存しない。
* 固定 fixture で言い換えと具体化、逆戻りと語句共有具体化、scope別重複、No同一仮説と別仮説、protected状態差を区別する。境界は明示的 uncertain。
* DB exact と最新集合に依存する保存前検査は維持し、不変評価だけを安全に再利用。
* API/export/context/OFF系が回帰せず、総呼出数と停止理由が監査可能。全ログlevel/診断flag/error経路で機密ダミー原文が出ず、内容非依存の計測値はanalyzerで読める。
* A修正前baselineは安全性比較、A1後かつB計測整備後のbaselineはC以降の高速化比較に使い分ける。実測で品質非劣化を人手確認し、速度効果は固定親・同一条件で報告。数値合格線は Step4-B の baseline と必要データから承認して確定する。

### 10.2 ロールバック

段階ごとの feature flag / adapter で新ログ形式、requested-count、rules、理由feedbackを独立に戻せるようにする。ただし Step4-A critical復帰防止 sanitizer とログ秘密漏えい防止は安全修正として、旧挙動へのrollbackよりforward fixを優先する。Aを戻さずC/D/Eだけを戻せる境界にする。DB migrationを初期案に含めず、API追加キーとログは旧 consumerが無視可能にする。rollback時も分離 context、Gate ON sanitizer、保存前DB重複防止を外さない。

### 10.3 未決事項・必要データ

* 実環境の provider とモデル、件数設定、親数、retry発生率、token/latency分布。
* 一～三次ごとの候補、親説明、祖先、比較scope、No理由を含む匿名化 gold set。特に三次全除外例。
* false reject / miss の業務許容度と uncertain の保存/表示方針。
* protected語彙、形態素処理の必要性、cross-branch類似の扱い、No評価の有効範囲。
* requested_countを尊重できない外部 HTTP provider の capability/バージョニング。
* processing_limitの余裕幅、response byte/候補文字数上限、候補選択の安定順序。
* DEBUG診断情報の保管先・権限・保持期限と、人手評価artifactの承認/匿名化手順。
* A0 artifactのCI保存先・保持期限、fixtureの正確な版管理方式、物理provider retry回数を最小観測で取得できるか。
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

本計画の次工程は **Step4-A0で修正前baselineを取得・確定し、その後A1でcritical復帰防止の最小安全修正を行うこと**である。A0/A1は同じ実装用PRの別コミットとし、Step4-B以降より先に実施する。今回baselineは採取しておらず、本書のレビュー反映はA0/A1や将来のプログラム修正完了を意味しない。ここから続けて実装、計測、閾値、prompt、mergeを行わない。

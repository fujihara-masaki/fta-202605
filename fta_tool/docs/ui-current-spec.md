# FTA分析支援ツール 現行画面・操作仕様

## 1. 文書情報

| 項目 | 値 |
|---|---|
| 調査対象ブランチ | `work` |
| 調査開始時の commit SHA | `f575e05be2ae0da5728999a402b6c1285b7158c1` |
| 調査日 | 2026-09-25 (UTC) |
| 対象 | 分析一覧、新規分析作成、分析・編集、関連モーダル・メニュー・通知・確認表示 |

ブランチとSHAは `git status --short --branch` と `git rev-parse HEAD` で確認した。利用者が実際に使うローカル環境のブランチ、SHA、`.env`、DBとの同一性は、環境が未提供のため**未確認**である。

### 確認方法と区分

- **コード確認**: Jinja2テンプレート、`app.js`、CSS、FastAPIルート、ORM/CRUD、出力サービス、生成設定、関連テストを照合した。
- **テスト仕様確認**: 関連自動テストのコードを読み、期待されるHTTP・保存契約を照合した。調査環境では依存パッケージ不足によりテストを実行できず、実ブラウザの目視、レスポンシブ表示、実LLM、実データを含め、今回の**動作確認は未実施**。
- **未確認**: 実装から確定できない利用者期待、運用環境、表示品質、外部AIの応答。

## 2. 画面と遷移

| 画面 | URL / テンプレート | 目的・遷移 |
|---|---|---|
| 分析一覧 | `GET /` / `index.html` | 分析の参照、改名、編集開始、出力、削除。新規作成または編集へ遷移 |
| 新規分析作成 | `GET /analyses/new` / `analysis_form.html` | 初期情報を登録。`POST /analyses` 成功後、対象編集画面へ303 redirect |
| 分析・編集 | `GET /analyses/{id}` / `analysis_detail.html` | 頂上事象から一〜三次要因を生成・追加・編集・評価し出力。一覧へ戻る |

全画面のヘッダーに「分析一覧」「新規作成」がある。共通トーストはsuccess/errorが3秒、warningが6秒で消える。

## 3. 機能棚卸し

| ID | 画面・領域 | 操作と目的 | 入力・表示／条件 | 保存・状態・失敗時 | 根拠 | 確認 |
|---|---|---|---|---|---|---|
| UI-01 | 一覧 | 更新日時降順の分析を開く | title、頂上事象、作成/更新日時 | 0件は空状態と作成CTA | `app/main.py:index`, `app/crud.py:get_analyses`, `app/templates/index.html` | コード確認 |
| UI-02 | 一覧 | titleをインライン改名 | 必須、255文字以内。Enter/保存、Esc/取消 | `Analysis.title`, `updated_at`。成功/失敗トースト | `app/static/app.js:startTitleRename/saveAnalysisTitle`, `app/main.py:update_title` | コード確認 |
| UI-03 | 一覧 | 分析を削除 | 名前、全要因・評価・メモも消える旨をconfirm | Analysisと全Nodeをcascade削除。成功後reload | `app/static/app.js:deleteAnalysis`, `app/main.py:delete_analysis`, `app/models.py:Analysis.nodes` | コード確認 |
| UI-04 | 一覧/編集 | JSON/CSV/MD出力 | 分析存在時。項目差は§6 | 正常時はファイル出力。対象分析が不存在でもHTTP 200で、JSONはエラーオブジェクト、CSVは空本文、Markdownはエラー文書を返す（詳細は§6） | `app/main.py:export_analysis_json/export_analysis_csv/export_analysis_markdown`, `app/services/export_service.py` | コード確認 |
| UI-05 | 新規 | 分析を作成 | title必須。頂上事象、2種contextは任意 | Analysis作成。contextはJSON。成功後編集へ。サーバ側title長上限なし | `app/templates/analysis_form.html`, `app/main.py:create_analysis`, `app/models.py:Analysis` | コード確認 |
| UI-06 | 新規 | デモsampleをpreviewし入力欄へ転記 | category、頂上事象、context、demo points | 適用時は未保存、form送信で保存 | `app/services/sample_scenarios.py:get_sample_scenarios`, `app/templates/analysis_form.html:onSampleSelect/applySample` | コード確認 |
| UI-07 | 編集 | 分析title/頂上事象を更新 | title必須・255文字、頂上事象は空保存可 | titleはblur/Enter、頂上事象はボタン。**未保存の頂上事象を生成前に保存するのは一次の通常生成・一次の追加生成だけ** | `app/templates/analysis_detail.html`, `app/static/app.js:saveAnalysisTitle/saveTopEvent/ensureTopEventReady/generateFactors/generateAdditional` | コード確認 |
| UI-08 | 編集/context | 2種の生成参考情報を保存 | システム構成・対象範囲、障害時状況・観測事実。任意 | JSONへmergeし未知key/demo_pointsを維持。生成前に未保存値を自動保存 | `app/main.py:update_analysis_context`, `app/static/app.js:saveAnalysisContext/ensureAnalysisContextReady/generateFactors/generateAdditional` | コード確認 |
| UI-09 | 編集/通常生成 | 一次、またはYes評価した全親の子をAI生成 | 一次は頂上事象必須。二/三次はYes親必須。処理中は全生成ボタン無効 | AI Node。既定目標4/3/2件。一次はoverlay、二/三次は親ごと順次badge | `app/static/app.js:generateFactors/generateFactorsSequential`, `app/main.py:generate_factors` | コード確認（動作未確認） |
| UI-10 | 編集/追加生成 | 既存兄弟と異なる要因をAI追加 | 一次は一括、二/三次は特定親。特定親はNo/未評価でも可 | `additional=true`、既定2件。指定親badge | `app/static/app.js:generateAdditional`, `app/main.py:_get_factor_count/generate_factors` | コード確認 |
| UI-11 | 手動追加modal | AIなしで一次または指定親の子を追加 | title必須、説明任意。兄弟同階層同名は409 | `ai_generated=false`, `unknown`。成功reload、失敗toast | `app/main.py:add_child_node/add_level1_node`, `app/templates/analysis_detail.html`, `app/static/app.js:submitAddNode` | コード確認 |
| UI-12 | カード | Yes/No/未評価を保存 | 3値。常時操作可 | `user_judgement`。カード・表へ即時反映。Yesだけ通常の次階層生成対象 | `app/static/app.js:setJudgement`, `app/main.py:update_node`, `app/models.py:Node.user_judgement` | コード確認 |
| UI-13 | 詳細modal | 要因と直接要因評価を編集 | title、説明、memo、直接要因5値、comment、根拠、再発防止策 | 開く時APIで保存値取得。Yes/Noとは別データ。成功reload | `app/main.py:get_node_detail/update_node`, `app/templates/analysis_detail.html`, `app/static/app.js:openNodeDetail/saveNodeDetail` | コード確認 |
| UI-14 | カード | title直接編集、要因ツリー削除 | 空titleは保存しない。削除は子孫も消すconfirm | title保存は通知なし。削除成功reload | `app/static/app.js:saveNodeTitle/deleteNode`, `app/main.py:update_node/delete_node`, `app/models.py:Node.children` | コード確認 |
| UI-15 | 検索 | 名前/説明と評価/要確認をAND絞込 | Yes/No/未評価/要確認 | **カードと一覧表のみ**。階層ツリーは対象外。件数はカード基準 | `app/static/app.js:applyNodeFilter`, `app/templates/analysis_detail.html` filter bar | コード確認 |
| UI-16 | 表示 | カード列、階層tree、表で参照 | 親、評価、直接要因、警告等 | tree/表の開閉はanalysis別localStorage、reload時scrollはsessionStorage | `app/templates/analysis_detail.html`, `app/static/app.js:reloadPreservingScroll` and DOMContentLoaded handlers | コード確認 |
| UI-17 | 品質表示 | 警告理由を確認 | AI tag、要確認badge/reason | `warning_flags`を保存。hover/click toast、modal、表、出力へ反映 | `app/services/factor_quality.py:evaluate_candidate`, `app/static/app.js:showWarningDetail`, `app/templates/analysis_detail.html` | コード確認 |

## 4. 代表操作フロー

1. 一覧から新規作成へ行き、必須title、任意の頂上事象と2種contextを入力する。sample適用は入力補助で、その時点では未保存。
2. 作成後、編集画面へ遷移する。一次の通常生成・一次の追加生成では、頂上事象が空なら停止し、入力中の頂上事象が保存値と異なれば先に自動保存する。二次・三次の通常生成および追加生成は `ensureTopEventReady()` を呼ばないため、未保存の頂上事象を保存しない。
3. 2種類のcontextは階層・通常/追加を問わず全生成経路で `ensureAnalysisContextReady()` を通り、未保存なら先に自動保存する。AI一次候補または手動一次要因を追加し、利用者がYes/No/未評価を選ぶ。
4. 「Yesの一次要因から二次要因を生成」は全Yes親をブラウザが順次処理し、三次も同様。
5. 「子を追加生成」は特定親だけをAIで補完し、親のYes/Noによる制限はない。「子追加」はAIを呼ばない。
6. 詳細modalで直接要因評価、comment、根拠、再発防止策、memoを記録し、3表示またはexportで確認する。

**Yes/No/未評価** (`user_judgement`) は要因の該当判断と通常生成対象を表す。**直接要因評価** (`direct_cause_status`) は別軸で、未評価／可能性高／可能性低／直接要因／直接要因でないの5値である。

## 5. 生成時の経路別・状態別挙動

サーバーの `app/main.py:generate_factors` は単一親の呼出しごとに `success`, `message`, `created`, `skipped`, `parent_id`, `quality_summary` を返す。以下は、その応答を各ブラウザ経路がどう表示するかを分離した記録である。

| 経路 | 呼出しと生成中表示 | `created > 0` | 0候補 | 全候補除外 | 処理/通信失敗 |
|---|---|---|---|---|---|
| 一次・通常 (`generateFactors(..., 1)`) | API 1回。全画面overlay、全生成trigger無効 | APIの`message`をtoast後reload | `success=true`ならAPIの`message`（LLMが返さなかった旨）をwarning | APIの`message`（件数・主理由）をwarning | APIの`message`をerror。fetch例外は通信error |
| 二/三次・一括 (`generateFactorsSequential`) | DOM上の全Yes親へAPIを1回ずつ順次実行。各親に一時badge | 全親の`created`を合計し、`合計N件...`という**ブラウザ集計文言**を表示後reload | 作成・除外・errorが全て0ならブラウザ固定文言「新規要因はありませんでした」 | 除外数・理由をブラウザで集計してwarning | 親にerror badge。ただし作成合計が1件以上なら最終通知は成功合計が優先され、**error件数を含めない** |
| 追加 (`generateAdditional`) | 一次はAPI 1回＋overlay、子は指定親へAPI 1回＋一時badge | APIの`message`をtoast後reload | `success=true`ならAPIの`message`をwarning | APIの`message`をwarning、指定親は除外badge | APIの`message`をerror、指定親はerror badge。fetch例外は通信error |

### サーバー応答の意味

- `created > 0`: 保存された新規Nodeがある。サーバーのmessageは作成件数とskip情報を含み得る。
- LLM応答0件: `success=true`, `created=0`, `quality_summary.all_candidates_excluded=false`。API messageは「生成候補がありませんでした（LLMが要因を返しませんでした）。」。
- 全候補除外: `success=true`, `created=0`, `all_candidates_excluded=true`。API messageは候補数、品質チェックによる全除外、主理由を含む。
- 一部の親処理で例外: そのAPI呼出しは`success=false`でも、それ以前の成功Nodeが保存済みの場合がある。

### 一括生成に固有の現行制約

`generateFactorsSequential()` は最終分岐で `totalCreated > 0` を最優先する。このため成功親と失敗親が混在すると、画面には「合計N件を生成」の成功toastが出てerror件数は通知されない。親ごとのerror badgeはDOMへ一時追加されるだけで永続化されず、成功が1件でもあれば直後のreloadで消える。これは**現行挙動**であり、成功と失敗の混在を永続的・集約的に区別できているという意味ではない。

再設計では、部分成功時に成功件数と失敗親/件数を同時に示すか、reload後も結果を参照可能にするかを別途判断する。これは表示改善候補であり、現行API/保存仕様を変更する確定要件ではない。

## 6. 保存・出力データ

- **Analysis**: title、top_event、JSON文字列のanalysis_context、作成/更新日時。公開keyは`system_context`/`incident_context`、sample由来の非表示keyは`demo_points`。
- **Node**: 親子とlevel 1〜3、title/description、AI/手動、利用者評価、直接要因評価一式、memo、warning、表示順。頂上事象はNode(level 0)でなくAnalysisの値。
- **JSON**: Analysisメタ情報、context、Nodeの全主要項目。
- **CSV**: Nodeを1行ずつ、評価、詳細、warning、品質statusを出す。Analysis contextは含まない。
- **Markdown**: 頂上事象、context、tree、利用者評価、直接要因status/comment/再発防止策。Node description、根拠、memo、warningは出さない。

### 対象分析が存在しない場合

現行のエクスポート用ルートは、分析の不存在に対して404を返さない。出力サービスの戻り値を既定のHTTP 200で返す。

- JSON: `{"error": "Analysis not found"}`
- CSV: 空の本文
- Markdown: `# エラー` と `分析が見つかりません。` を含む文書

これはコード確認による現行挙動であり、実機での再現確認は未実施。404化や画面上のエラー通知の改善は、別途判断する仕様変更とする。

根拠は、`app/main.py` の `export_analysis_json()`、`export_analysis_csv()`、`export_analysis_markdown()` と、`app/services/export_service.py` の `export_json()`、`export_csv()`、`export_markdown()` である。

## 7. READMEとの照合

| 区分 | 結果・対応 |
|---|---|
| 一致 | 作成/削除、一〜三次AI生成、追加生成、3表示、Yes/No、直接要因評価、3形式出力は一致 |
| 実装にあり不足 | READMEには2種contextと手動追加・品質warningの概要を追記した。demo sampleと「全候補除外」の状態詳細はREADMEへ重複記載せず本仕様書に記載し、READMEから本書へリンクした |
| 古い可能性 | directory例はサービス/テスト全数を列挙しない概略。画面仕様の誤りとは断定せず全面改稿しない |
| READMEにあるが未確認 | 画面機能は該当なし。モデル性能/時間は環境依存で、実LLM再検証は未実施 |
| 判断保留 | READMEの検索・filterはカードと表だけに適用されtreeは対象外。意図通りか未確認 |

## 8. 現行挙動（維持要件ではない）

1. Node titleのinline保存はHTTP成否を確認せず、空にした場合もDOMは空のまま（DBは未更新）。reloadで保存値に戻る。**不具合の疑い**。
2. 一覧改名失敗時、具体的API理由の後に一般的な「保存に失敗」で上書きする可能性がある。**不具合の疑い**。
3. filterで非表示のYesカードも通常の一括生成対象になる。filterが生成対象へ影響しない意図かは未確認。
4. Node更新/削除はAnalysisの`updated_at`を明示更新しない一方、Node作成は更新する。一覧日時/並び順の期待と合うか未確認。

## 9. 未確認事項と実機確認手順

1. **版**: 利用環境で `git branch --show-current` と `git rev-parse HEAD` を取り§1と比較。秘密値を開示せず`.env`のprovider/flagも比較する。
2. **表示**: 検証DB/mockでdesktopと想定最小幅の3画面、長文、0/多件、modal、横scroll、focus復帰を目視する。
3. **生成状態**: mock/stubで遅延、0件、全除外、一部親失敗、通信断を再現し、無効化、badge、toast、部分保存を確認する。実LLMは別承認で行う。
4. **頂上事象の保存範囲**: 二次・三次生成でも編集中の頂上事象を保存すべきかを利用者・productに確認する。現行は一次の通常/追加だけが保存確認し、contextは全生成経路で保存確認する。
5. **業務定義**: 2種類の評価基準、No後の子保持、No親への個別追加生成可否を利用者に確認する。
6. **出力契約**: 形式ごとの項目差、後続用途、Markdownに根拠がないことが期待通りか確認する。
7. **アクセシビリティ**: Tab順、modal focus trap、screen reader、contrastは未検証。


## 10. テストコードとの対応（実行確認ではない）

依存不足により今回は実行していない。別途読んだテスト仕様は、主に `tests/test_ui_endpoints.py:test_get_node_returns_all_detail_fields/test_delete_level1_node_cascades_to_level2_and_level3/test_delete_analysis_removes_analysis_and_nodes`、`tests/test_analysis_context.py:test_create_analysis_saves_context/test_update_context_trims_and_persists/test_updated_context_is_passed_to_ai_provider/test_exports_reflect_updated_context`、`tests/test_generate_endpoint.py:test_generate_level1_response_shape/test_all_candidates_excluded_parent_paraphrase/test_no_candidates_returned`、`tests/test_export_service.py` の期待値を読んだことを示す。ブラウザ内だけで集計する `generateFactorsSequential()` の最終toastや一時badgeは、対応する自動テストを確認できていないためコード確認のみである。

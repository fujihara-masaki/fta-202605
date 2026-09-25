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
| UI-01 | 一覧 | 更新日時降順の分析を開く | title、頂上事象、作成/更新日時 | 0件は空状態と作成CTA | `main.index`, `crud.get_analyses`, `index.html` | コード＋テスト仕様 |
| UI-02 | 一覧 | titleをインライン改名 | 必須、255文字以内。Enter/保存、Esc/取消 | `Analysis.title`, `updated_at`。成功/失敗トースト | `startTitleRename`, `saveAnalysisTitle`, `update_title` | コード＋テスト仕様 |
| UI-03 | 一覧 | 分析を削除 | 名前、全要因・評価・メモも消える旨をconfirm | Analysisと全Nodeをcascade削除。成功後reload | `deleteAnalysis`, delete route, `Analysis.nodes` | コード＋テスト仕様 |
| UI-04 | 一覧/編集 | JSON/CSV/MD出力 | 分析存在時。項目差は§6 | ダウンロード。不存在は404 | export 3 routes, `export_service.py` | コード＋テスト仕様 |
| UI-05 | 新規 | 分析を作成 | title必須。頂上事象、2種contextは任意 | Analysis作成。contextはJSON。成功後編集へ。サーバ側title長上限なし | form, `create_analysis`, `Analysis` | コード＋テスト仕様 |
| UI-06 | 新規 | デモsampleをpreviewし入力欄へ転記 | category、頂上事象、context、demo points | 適用時は未保存、form送信で保存 | `sample_scenarios.py`, form内JS | コード＋テスト仕様 |
| UI-07 | 編集 | 分析title/頂上事象を更新 | title必須・255文字、頂上事象は空保存可 | titleはblur/Enter、頂上事象はボタン。生成前に未保存値を自動保存 | detail template, `ensureTopEventReady` | コード＋テスト仕様 |
| UI-08 | 編集/context | 2種の生成参考情報を保存 | システム構成・対象範囲、障害時状況・観測事実。任意 | JSONへmergeし未知key/demo_pointsを維持。生成前に未保存値を自動保存 | context route, `save/ensureAnalysisContextReady` | コード＋テスト仕様 |
| UI-09 | 編集/通常生成 | 一次、またはYes評価した全親の子をAI生成 | 一次は頂上事象必須。二/三次はYes親必須。処理中は全生成ボタン無効 | AI Node。既定目標4/3/2件。一次はoverlay、二/三次は親ごと順次badge | `generateFactors`, `generateFactorsSequential`, generate route | コード＋テスト仕様（動作未確認） |
| UI-10 | 編集/追加生成 | 既存兄弟と異なる要因をAI追加 | 一次は一括、二/三次は特定親。特定親はNo/未評価でも可 | `additional=true`、既定2件。指定親badge | `generateAdditional`, `_get_factor_count`, generate route | コード＋テスト仕様 |
| UI-11 | 手動追加modal | AIなしで一次または指定親の子を追加 | title必須、説明任意。兄弟同階層同名は409 | `ai_generated=false`, `unknown`。成功reload、失敗toast | add routes, modal, `submitAddNode` | コード＋テスト仕様 |
| UI-12 | カード | Yes/No/未評価を保存 | 3値。常時操作可 | `user_judgement`。カード・表へ即時反映。Yesだけ通常の次階層生成対象 | `setJudgement`, model | コード＋テスト仕様 |
| UI-13 | 詳細modal | 要因と直接要因評価を編集 | title、説明、memo、直接要因5値、comment、根拠、再発防止策 | 開く時APIで保存値取得。Yes/Noとは別データ。成功reload | node detail/update routes, modal | コード＋テスト仕様 |
| UI-14 | カード | title直接編集、要因ツリー削除 | 空titleは保存しない。削除は子孫も消すconfirm | title保存は通知なし。削除成功reload | `saveNodeTitle`, `deleteNode`, Node cascade | コード＋テスト仕様 |
| UI-15 | 検索 | 名前/説明と評価/要確認をAND絞込 | Yes/No/未評価/要確認 | **カードと一覧表のみ**。階層ツリーは対象外。件数はカード基準 | `applyNodeFilter`, filter bar | コード＋テスト仕様 |
| UI-16 | 表示 | カード列、階層tree、表で参照 | 親、評価、直接要因、警告等 | tree/表の開閉はanalysis別localStorage、reload時scrollはsessionStorage | detail template, app.js | コード＋テスト仕様 |
| UI-17 | 品質表示 | 警告理由を確認 | AI tag、要確認badge/reason | `warning_flags`を保存。hover/click toast、modal、表、出力へ反映 | `factor_quality.py`, `showWarningDetail` | コード＋テスト仕様 |

## 4. 代表操作フロー

1. 一覧から新規作成へ行き、必須title、任意の頂上事象と2種contextを入力する。sample適用は入力補助で、その時点では未保存。
2. 作成後、編集画面へ遷移する。一次生成前に頂上事象が空なら停止する。入力中の頂上事象/contextが保存値と異なれば先に自動保存する。
3. AI一次候補または手動一次要因を追加し、利用者がYes/No/未評価を選ぶ。
4. 「Yesの一次要因から二次要因を生成」は全Yes親をブラウザが順次処理し、三次も同様。
5. 「子を追加生成」は特定親だけをAIで補完し、親のYes/Noによる制限はない。「子追加」はAIを呼ばない。
6. 詳細modalで直接要因評価、comment、根拠、再発防止策、memoを記録し、3表示またはexportで確認する。

**Yes/No/未評価** (`user_judgement`) は要因の該当判断と通常生成対象を表す。**直接要因評価** (`direct_cause_status`) は別軸で、未評価／可能性高／可能性低／直接要因／直接要因でないの5値である。

## 5. 生成時の状態別挙動

| 状態 | サーバ区分 | UI挙動 |
|---|---|---|
| 生成中 | request中 | 全生成triggerを無効化。一次はoverlay、親単位は「生成中…」badge |
| 正常・作成あり | `created > 0` | 件数toast後、scrollを保持してreload |
| 新規候補なし | LLM応答0件 | 「生成候補がありません」warning。保存なし |
| 全候補除外 | `all_candidates_excluded=true` | 品質チェックの件数/理由warning。親badgeは「0件(除外)」 |
| 警告付き保存 | 許容された品質指摘 | Nodeへwarningを保存し「要確認」badge |
| 一部失敗 | 親単位errorあり | APIはfailureでも成功分が保存済みの場合あり。各親にerror badge |
| 通信失敗 | fetch exception | 通信/error toast。finallyでボタン再有効化 |

品質確認は親の言い換え、祖先への逆行、類似/重複、No評価要因との類似等を扱う。アルゴリズム詳細は対象外で、`langgraph_quality_gate_rules.md`等を参照する。

## 6. 保存・出力データ

- **Analysis**: title、top_event、JSON文字列のanalysis_context、作成/更新日時。公開keyは`system_context`/`incident_context`、sample由来の非表示keyは`demo_points`。
- **Node**: 親子とlevel 1〜3、title/description、AI/手動、利用者評価、直接要因評価一式、memo、warning、表示順。頂上事象はNode(level 0)でなくAnalysisの値。
- **JSON**: Analysisメタ情報、context、Nodeの全主要項目。
- **CSV**: Nodeを1行ずつ、評価、詳細、warning、品質statusを出す。Analysis contextは含まない。
- **Markdown**: 頂上事象、context、tree、利用者評価、直接要因status/comment/再発防止策。Node description、根拠、memo、warningは出さない。

## 7. READMEとの照合

| 区分 | 結果・対応 |
|---|---|
| 一致 | 作成/削除、一〜三次AI生成、追加生成、3表示、Yes/No、直接要因評価、3形式出力は一致 |
| 実装にあり不足 | 2種context、demo sample、手動追加、品質warning/全除外の概要をREADMEへ追記。詳細は本書へ分離 |
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
4. **業務定義**: 2種類の評価基準、No後の子保持、No親への個別追加生成可否を利用者に確認する。
5. **出力契約**: 形式ごとの項目差、後続用途、Markdownに根拠がないことが期待通りか確認する。
6. **アクセシビリティ**: Tab順、modal focus trap、screen reader、contrastは未検証。

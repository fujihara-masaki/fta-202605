## 実ブラウザテスト（E2E）の記録

| 項目 | 値 |
|---|---|
| 実行日時（UTC） | 2026-10-30 10:44:10 |
| 開始・終了（ローカル時刻） | 2026-10-30 10:21:33 +0000 〜 2026-10-30 10:44:10 +0000（所要 22分37秒） |
| 実行環境の区分 | 開発環境（Linux、headless、Chromium 153 を明示） |
| OS | Linux-6.18.44-fc-v185-x86_64-with-glibc2.39 |
| Python | 3.12.3 |
| Playwright / pytest-playwright | 1.56.0 / 0.7.1 |
| ブラウザ | chromium 153.0.8010.12（headless） |
| ブラウザの channel（指定） | なし。--e2e-browser-executable で指定した実行ファイル（Playwright の固定版が使うブラウザではない）：/opt/pw-browsers/chromium |
| 起動したブラウザ | 指定した実行ファイルの Chromium（--e2e-browser-executable）：Google LLC 153.0.8010.12 (Official Build) (x86_64) |
| ブラウザの実行ファイル | /opt/pw-browsers/chromium-1243/chrome-linux64/chrome |
| ブラウザのプロフィール | /tmp/playwright_chromiumdev_profile-3L1F57/Default |
| 起動の設定 | headless、slowmo なし |
| 対象コミット | `b35504f826f53359d665a79ae099b5479d6d0b0a`（未コミットの変更なし） |
| ブランチ | `HEAD` |
| 実行コマンド | `pytest -q -p no:cacheprovider -m e2e --e2e-browser-executable=/opt/pw-browsers/chromium --e2e-required --e2e-env '開発環境（Linux、headless、Chromium 153 を明示）' --e2e-report /tmp/claude-0/-home-user-fta-202605/8138f360-15d8-55c1-a05d-56c0995df387/scratchpad/runs-b35504f/e2e-report-full.md --output /tmp/claude-0/-home-user-fta-202605/8138f360-15d8-55c1-a05d-56c0995df387/scratchpad/runs-b35504f/full-out` |
| 必須受入検証として実行 | はい（スキップ・未実施は失敗） |
| コード側の .env | なし（/tmp/claude-0/-home-user-fta-202605/8138f360-15d8-55c1-a05d-56c0995df387/scratchpad/wt-b35504f/fta_tool/.env） |
| テスト用サーバー | AI: e2e-stub（tests/e2e/stub_server.py。実LLMの取得と外部への HTTP は遮断し、試みがあればテストを失敗にする）、http://127.0.0.1:43781、作業フォルダ（一時 DB）/tmp/pytest-of-root/pytest-202/e2e-server0、ログ /tmp/pytest-of-root/pytest-202/e2e-server0/server.log |
| 失敗時の証跡の設定（pytest-playwright） | スクリーンショット off、trace off、保存先 /tmp/claude-0/-home-user-fta-202605/8138f360-15d8-55c1-a05d-56c0995df387/scratchpad/runs-b35504f/full-out（設定です。実際に残ったファイルは下の「失敗したテストの証跡（実際にあるファイル）」） |
| 画面寸法（CSS ピクセル） | 1280×800、1440×900、1905×945、1912×914、1920×1080、1536×730、1280×620、1366×650、1093×500、1024×683、900×600、1920×945（DPR 1）、1536×756（DPR 1.25）、1280×630（DPR 1.5）、1530×731（DPR 1.25）、1275×609（DPR 1.5） |
| 寸法の組（--e2e-viewport-set） | base：寸法を自分で選ばないテストは基本寸法（1280×800・1440×900）だけ。PR-7 の寸法は E-V01〜E-V03・E-F01 などが自分で選んで実行。計画 第8.7節の全テストの全寸法での実行は、この記録では未実施（--e2e-viewport-set pr7） |
| 画面寸法の要求と実測（PR3-LAYOUT） | 一致 3・許容した差 0・許容しない差 0（下の「画面寸法の要求と実測（PR3-LAYOUT）」） |
| 結果（テスト単位） | 成功 595・失敗 0・スキップ 0・未実施 0 |
| コンソールのエラーの例外 | なし（PR-7 で favicon を実装し、favicon の 404 の既知の例外を廃止。すべてのコンソールのエラー・ページの例外・外部への要求を失敗にする） |
| 判定 | 合格 |

### 受入項目ごとの結果

| ID | 内容 | 結果 | 成功 | 失敗 | スキップ | 未実施 |
|---|---|---|---|---|---|---|
| E-L01 | 一覧から分析を開く（タイトル・「編集」）、並び順 | 成功 | 2 | 0 | 0 | 0 |
| E-L02 | 改名：Enter で保存、Esc・取消、変換中の Enter では保存しない | 成功 | 4 | 0 | 0 | 0 |
| E-L03 | 改名の検査（空・256文字）と、サーバーのエラー理由の表示 | 成功 | 4 | 0 | 0 | 0 |
| E-L04 | 改名してもブラウザのタブ名が変わらない | 成功 | 2 | 0 | 0 | 0 |
| E-L05 | 改名中の移動：3択、保存して移動の成功・失敗、破棄、継続、変更なしなら確認なし、別の行の ✎ | 成功 | 16 | 0 | 0 | 0 |
| E-L06 | 分析の削除ダイアログ：件数、キャンセル・Esc、確定、失敗時の表示 | 成功 | 4 | 0 | 0 | 0 |
| E-L07 | 出力メニュー：キーボード操作、URL と download、改名中でも離脱確認が出ない | 成功 | 6 | 0 | 0 | 0 |
| E-L08 | 空の一覧 | 成功 | 2 | 0 | 0 | 0 |
| E-X01 | 全画面で、外部へのリクエストがない。PR-7：全画面がアプリの favicon（/static/favicon.svg）を宣言し、同じサーバーから 200 で取得でき、/favicon.ico を要求しない（favicon の 404 の既知の例外は廃止） | 成功 | 4 | 0 | 0 | 0 |
| E-N01 | 新規作成：2列の配置、4項目の保存（現行と同じ形）と編集画面への移動 | 成功 | 2 | 0 | 0 | 0 |
| E-N02 | 新規作成：タイトルの検査（空白のみ・256文字）、エラーとフォーカス、送信しない | 成功 | 2 | 0 | 0 | 0 |
| E-N03 | 新規作成：サンプルのプレビュー・転記・未保存表示、demo_points の保存、タイトルは転記しない | 成功 | 4 | 0 | 0 | 0 |
| E-N04 | 新規作成：キャンセル・ヘッダーのリンク（入力あり・なし）、入力を続ける／破棄して移動 | 成功 | 6 | 0 | 0 | 0 |
| E-N05 | 新規作成：二重送信で分析が2件できない、送信時に離脱確認が出ない | 成功 | 6 | 0 | 0 | 0 |
| E-N06 | 新規作成：入力があるときだけブラウザの離脱確認 | 成功 | 2 | 0 | 0 | 0 |
| PR1-BASE-NOTIFY | 通知：成功・警告は自動で閉じ、エラーは閉じるまで残る（J-24）。読み上げ領域 | 成功 | 4 | 0 | 0 | 0 |
| PR1-BASE-STORAGE | 保存領域が使えない環境でも一覧が動き、保存領域の処理が例外を出さない | 成功 | 4 | 0 | 0 | 0 |
| PR1-BASE-A11Y | スキップリンク、ヘッダーの aria-current、ダイアログのフォーカスの戻り先 | 成功 | 2 | 0 | 0 | 0 |
| PR1-STUB | E2E 用スタブ：作成・候補0件・処理失敗、実LLMと外部通信の遮断 | 成功 | 2 | 0 | 0 | 0 |
| PR2-IME | 新規作成：タイトルの Enter は検査を経て送信、変換確定の Enter では送信しない（合成キー操作。実機は手動） | 成功 | 2 | 0 | 0 | 0 |
| PR2-NO-SAMPLES | 新規作成：サンプルの設定ファイルがなくても、サンプル欄なしで作成できる | 成功 | 2 | 0 | 0 | 0 |
| E-E01 | 編集：既定の表示（要因なし→①と頂上事象、要因あり→②と最初の一次要因） | 成功 | 4 | 0 | 0 | 0 |
| E-E02 | 編集：R-01 の全経路での選択と、全表示・インスペクタの一致。要確認で品質警告の全文 | 成功 | 4 | 0 | 0 | 0 |
| E-E03 | 編集：評価の保存と全表示への反映（ツリーを含む）、未評価に戻す、失敗時、連続クリック | 成功 | 6 | 0 | 0 | 0 |
| E-E04 | 編集：絞り込み（作業リスト・一覧表は非表示、構造ナビ・ツリーは強調。文字、評価の Yes・No・未評価・要確認）、件数、生成対象が変わらない | 成功 | 4 | 0 | 0 | 0 |
| E-E05 | 編集：表示タブのキー操作、選択の保持 | 成功 | 2 | 0 | 0 | 0 |
| E-E06 | 編集：再読み込み後の復元（選択・ステップ・タブ・スクロール・絞り込み）、不正なハッシュ、保存領域なし | 成功 | 6 | 0 | 0 | 0 |
| E-E07 | 編集：部分更新の後もフォーカス・スクロール・入力中の値が残る、分析が削除されていた場合、取得の失敗、生成中は取得しない。ダイアログ（PR-5 から手動追加・削除のダイアログ。PR-3 は旧ダイアログ）を開いている間に更新されても閉じるとフォーカスが戻る、生成中に手動追加した要因が後から選んだ要因を置き換えない。一次要因を削除すると確認に要因名が出て、頂上事象が選ばれる | 成功 | 18 | 0 | 0 | 0 |
| E-E08 | 編集：不正な親子関係の区分ごとの表示、走査が止まる、頂上事象として出ない、削除・追加・生成の可否と理由（すべての区分で追加生成・手動追加が無効になり、理由が見える） | 成功 | 4 | 0 | 0 | 0 |
| E-E09 | 編集：demo_points を表示しない、マークアップを含む要因の文字列がそのまま文字として出る | 成功 | 2 | 0 | 0 | 0 |
| E-E19 | 編集：部分更新の古い応答で表示が巻き戻らない（評価・頂上事象の保存の前に発行した取得、確定済みの評価と食い違う応答）、続けて保存される評価の間も取得しない。別のタブで後から評価が変わっても、以後の部分更新は止まらない（実際の2つのタブでも確認） | 成功 | 12 | 0 | 0 | 0 |
| PR3-LAYOUT | 編集：暫定の3ペイン（1280px 以上）が 1280×800 と利用者環境の実測値（clientWidth×clientHeight：Chrome 1905×945・Edge 1912×914）で横に並び、ページ全体の横スクロールがなく、主要な操作が見えて隠れない。1280×800・1440×900 で各ペインが個別にスクロールする（最終確認は PR-7 の E-V01〜E-V03）。表示領域は要求と実測を記録し、Chrome 1905×945 だけはアプリの表示前からある各軸 +1 CSS px までの差（レイアウトの境界を跨がないもの）を許容して実測の寸法で検査する（2026-10-06） | 成功 | 15 | 0 | 0 | 0 |
| PR3-DELETE-SCOPE | 編集：別分析の要因が子孫にある要因とその祖先・走査を完了できない・確認用の情報を取得できない場合は削除できず、削除要求が送られない。親不在・上位に不整合ありはその部分木（階層不一致の子孫を含む）だけが消え、階層不一致の要因そのものは削除できない（判断2とその追加判断） | 成功 | 8 | 0 | 0 | 0 |
| PR3-GEN-PARENTS | 編集：生成・追加生成・手動追加の親に不整合のある要因を使わない。対象0件なら要求を送らない、親指定なしの要求を送らない、対象件数と除外件数の表示（判断3） | 成功 | 6 | 0 | 0 | 0 |
| PR3-LEGACY-NOTIFY | 編集：通知（保存・生成・ダイアログ・削除・通信エラー）が共通の通知に種別どおり1回ずつ出る（旧処理の生成は同じ文言）、エラーは閉じるまで残る、旧 #toast がない（判断4）。PR-5 の要因の保存・手動追加・削除の通知と、タイトル必須の欄・ダイアログ内の表示。開いている画面内ダイアログのどの部分にも通知が重ならず、閉じると通常の位置に戻る | 成功 | 4 | 0 | 0 | 0 |
| PR3-LEGACY-OPS | 編集：暫定の旧処理（生成。PR-6 まで）と、作り直した操作（PR-4 のタイトル・①の保存・出力・一覧へ、PR-5 のインスペクタの保存・手動追加・削除）が新しい画面から再読み込みなしで使え、旧処理が保証していた内容（メモの保存と評価を変えない、品質警告の全文、追加後の選択、No の親への追加生成、削除後の親の選択、出力）を保つ。二次・三次の生成中は親ごとに「生成中…」「+N件」が出て、部分更新で消える（PR-3 の暫定） | 成功 | 6 | 0 | 0 | 0 |
| E-E10 | 編集（PR-4）：①の保存と保存状態（入力中（未保存）／保存済み）。DB に直接入れた CRLF・前後の空白で未保存にならない、元に戻すと保存済み、送信後の入力は保存済みにしない、失敗時は入力と理由が残る、demo_points と未知のキーを保持し表示しない。生成前の自動保存（一次：頂上事象と参考情報、二次・三次：参考情報のみ）は保存ボタンと同じ保存・保存状態で、失敗・頂上事象が空なら生成しない | 成功 | 12 | 0 | 0 | 0 |
| E-E11 | 編集（PR-4）：ヘッダーの分析タイトルの行内編集。Enter で保存、Esc・取消、フォーカスが外れたら保存（保存・取消への移動では保存しない、二重送信しない）、変換中の Enter・Esc では何もしない（合成イベント。実機の Microsoft IME は手動）、必須・255文字（コードポイント）、移動時は確認なしで保存を待って移動し、空・文字数違反・保存失敗では移動しない。①と両方の変更、部分更新の失敗で入力が残る、分析が削除されたら編集・保存を止める | 成功 | 20 | 0 | 0 | 0 |
| E-E12 | 編集（PR-4）：画面を離れるときの3択（編集を続ける・Esc・破棄して移動・保存して移動）、保存して移動の順番・一部失敗・保存元ごとの結果・失敗分だけの再試行・部分成功後の破棄の説明、ブラウザ操作は標準の確認だけ（取り消すと入力が残る） | 成功 | 16 | 0 | 0 | 0 |
| E-E13 | 編集（PR-4）：⑤の件数（共通データから。評価の変更・部分更新で更新、不整合の要因は別の行、直接要因は Yes と別）、出力の項目差の表、出力リンクとヘッダーの出力メニュー（一覧と同じ URL・download・キーボード操作）、未保存の入力があってもダウンロードで確認が出ない | 成功 | 6 | 0 | 0 | 0 |
| E-E20 | 編集（PR-4）：保存調整処理の契約。全保存元の事前検査（不備があれば送信0件）、要因→頂上事象→参考情報の順、編集開始時の分析・要因へ保存（選択が変わっても）、一部失敗でも別の保存元を続ける、再試行は失敗分だけ、分析が見つからない場合は未送信、送信中の保存を待つ（10秒を超えたら理由を表示）、生成の準備・生成中・反映中は受け付けない | 成功 | 20 | 0 | 0 | 0 |
| PR4-LAYOUT | 編集（PR-4）：タイトルの行内編集・出力メニュー・①の保存状態と保存ボタン・⑤の表と出力リンク・離脱確認のダイアログ（一部失敗の結果を含む）が、1280×800 と利用者環境の実測値の寸法で見えて隠れず、文字が 12px 以上、ページ全体の横スクロールがない（実機での読みやすさの確認は手動） | 成功 | 3 | 0 | 0 | 0 |
| E-E14 | 編集（PR-5）：実インスペクタの7項目（タイトル・説明・メモ・直接要因評価・評価コメント・根拠・再発防止策）を POST /nodes/{id}/update 1回で保存し評価を送らない。保存後に全表示（構造ナビ・作業リスト・親グループ見出し・ツリー・一覧表・パンくず・インスペクタ）・タグ・絞り込み・⑤が整合。正規化での保存状態（CRLF・空白、元に戻す、取消）、保存中の入力は保存済みにしない・保存と取消の二重操作なし、空タイトル・失敗で入力と理由が残る、保存成功と表示更新の失敗を区別し再送しない、詳細の読込み前・失敗時は入力・保存できない | 成功 | 10 | 0 | 0 | 0 |
| E-E15 | 編集（PR-5）：R-01 の全経路（構造ナビ・作業リストの行・親グループ見出しの親名・ツリー・一覧表・要確認・パンくず・子要因リンク・頂上事象）で未保存なら3択、編集を続ける・Esc で選択・ステップ・ハッシュ・入力を保持しフォーカスを戻す。保存して移動は編集中の要因へ保存（移動先ではない）、①を含む一覧と要因→頂上事象→参考情報の順、事前検査（空タイトルは送信0件・移動しない）、一部失敗・再試行（部分更新で置き換わった操作元の後継へ、編集を続ける・Esc でフォーカスを戻す）、元に戻した場合・同一要因の再選択・同一要因の要確認・①だけの未保存では確認しない、A→B→A で保存元は1つ | 成功 | 16 | 0 | 0 | 0 |
| E-E16 | 編集（PR-5）：要因の削除ダイアログ。対象名、サーバーの削除範囲計算による子孫件数と合計（絞り込み・表示の深さに依存しない）、画面表示時点の件数である旨。キャンセル・Esc・失敗で下書きを保持、編集中の要因・祖先の削除では「編集中の変更も破棄されます」と成功時にその下書きだけ解除、別の要因の削除では下書きを保持、削除後は親（なければ頂上事象）を選ぶ、確定時に削除可否を再確認、編集中の要因（祖先を含む）の保存中は削除しない | 成功 | 12 | 0 | 0 | 0 |
| E-E17 | 編集（PR-5）：手動追加ダイアログ。追加先の表示と開始時の固定、重複の理由をダイアログ内に表示し入力を保持、Enter で追加・変換中の Enter では追加しない、追加後の自動選択は R-01 を通す（編集を続けるで元の選択と下書きを保持、追加済みの要因は残り、追加を再送しない）、遅れて届いた更新が後の選択を上書きしない（A→B と A→B→A、取り直し・生成中の保留を含む）、続けて追加した場合と未保存の確認中に後の追加が完了した場合（後の追加の更新の取得中に「破棄して移動」を選んだ場合を含む）は最後に追加した要因を選ぶ、「編集を続ける」の後はそれまでに送った追加で再び確認しない | 成功 | 22 | 0 | 0 | 0 |
| E-E18 | 編集（PR-5）：保存中・詳細読込み中の切替（保存結果は別の要因に反映されない、A→B→A で最初の古い応答を採用しない、保存前に発行した部分更新で巻き戻らない）、別の要因の追加・削除・生成結果の反映で下書きが残る、編集中の要因の外部削除で入力と理由が残り他へ送らない（要因の404と分析の404を区別）。生成中の選択保護（J-01 の一部の前倒し）：要因の保存要求を送らない、未保存なら2択（理由を表示、破棄はインスペクタの変更だけ）、未保存がなければ切替を拒否しない、生成後は3択 | 成功 | 16 | 0 | 0 | 0 |
| PR5-LAYOUT | 編集（PR-5）：インスペクタの編集欄（7項目・保存状態・保存・取消・失敗の表示）、要因切替の3択、削除と手動追加のダイアログが、1280×800 と利用者環境の実測値の寸法で見えて隠れず、文字が 12px 以上、ページ全体の横スクロールがない（実機での読みやすさの確認は手動） | 成功 | 3 | 0 | 0 | 0 |
| E-G01 | 生成（PR-6）：一次生成は頂上事象が空なら止め（要求0件）、未保存の頂上事象・参考情報を保存してから生成する | 成功 | 4 | 0 | 0 | 0 |
| E-G02 | 生成（PR-6）：二次・三次の通常生成の対象（親名と件数、絞り込みで非表示の Yes 親を含む、不整合の親は除外して別に数える）、親ごとに parent_id を付けて順に要求、頂上事象の扱い（J-09） | 成功 | 4 | 0 | 0 | 0 |
| E-G03 | 生成（PR-6）：結果区分8種（作成・候補0件・全候補除外・処理失敗・通信失敗・親なし・分析なし・サーバーエラー）を生成ログと親別バッジで区別、品質警告付きの作成、全候補除外の理由、一部作成の処理失敗、HTTP 異常と JSON でない応答と通信の例外の区別、応答の件数と更新後の件数の不一致の注記、要約の通知（部分失敗は警告） | 成功 | 6 | 0 | 0 | 0 |
| E-G04 | 生成（PR-6）：生成中の操作制限（評価・保存・手動追加・削除・別の生成・出力・画面内リンク。ボタンの無効化と処理の入口・確定直前の確認、削除はボタン・開く・確定の3か所）、閲覧・選択・タブ・絞り込み・下書き入力は可、オーバーレイがない、終了後に戻る | 成功 | 5 | 0 | 0 | 0 |
| E-G05 | 生成（PR-6）：生成後の部分更新で新しい子要因が要求時の親の下に出る、選択・フォーカス・スクロール・下書き・ログが残る | 成功 | 2 | 0 | 0 | 0 |
| E-G06 | 生成（PR-6）：生成ログの保持（sessionStorage fta:genlog:v1:<分析ID>、分析ごと直近1回）。対象分析・実行時刻・再読み込み前の表示、現在見つからない親の注記、閉じる、別の分析・新しいタブ（開き方ごと）では出ない、本文・下書きを保存しない、保存領域の使用不可・容量不足・破損でも基本操作が続く、古い実行の制限を復活させない | 成功 | 11 | 0 | 0 | 0 |
| E-G07 | 生成（PR-6）：追加生成（一次・特定の親。Yes・No・未評価の親、三次の下には追加しない）と、操作バーの件数が設定値に従う | 成功 | 4 | 0 | 0 | 0 |
| E-G08 | 生成（PR-6）：生成中は下書きがなくてもブラウザ操作に標準の離脱確認、終了後は出ない。離れて戻った（バックフォワードキャッシュ）場合は生成を再開・再送せずに終了し、受信済みの結果を保ち、未判定は結果不明・未送信は送信していません、準備中なら取りやめ（模擬と実ブラウザの復元）、戻った後も離脱確認が出る | 成功 | 10 | 0 | 0 | 0 |
| E-G09 | 生成（PR-6）：生成準備。送信中の保存（評価・インスペクタ・頂上事象・参考情報・分析タイトル）を待ち、名前を表示、同じ要因の評価の連続保存は後続まで待つ、先行保存・自動保存の失敗では生成要求0件で理由と入力を残す、取りやめ（後で待機が終わっても生成しない、後の生成に影響しない）、10秒超の説明（時間切れにしない） | 成功 | 13 | 0 | 0 | 0 |
| E-G10 | 生成（PR-6）：生成中の詳細の取得待ち（新しく選んだ要因の GET を送らない、前の要因の詳細を出さない、取得済みの要因は保存済みの内容と取得時刻）、終了後に最後に選んだ要因だけ取得、古い応答の破棄、再取得で下書きを保持し変わった保存値を知らせる、初回の失敗と再取得の失敗を区別 | 成功 | 12 | 0 | 0 | 0 |
| E-G11 | 生成（PR-6）：生成中の保存の抑止（タイトルの Enter・フォーカス移動、インスペクタの保存は送らず下書きと理由が残る）、未保存の要因の切替は2択（理由）、変更なしなら確認なし、終了後は3択 | 成功 | 3 | 0 | 0 | 0 |
| E-G12 | 生成（PR-6）：制限の解除。成功・部分失敗・通信失敗・HTTP 異常・スタブの例外・画面の JavaScript の例外・部分更新の失敗のいずれでも終了処理の後に操作が戻る、反映が遅い間は制限が続く、分析の削除や不整合による無効化は残る。離れて戻った後も制限・状態表示・生成中の行が残らない | 成功 | 15 | 0 | 0 | 0 |
| C-00 | 静的ファイルのキャッシュ（PR-C）：キャッシュの試験が成立条件を守る（通信の差し替え・記録の再生・キャッシュの無効化・別のコンテキスト・消去・値の読み取りのための fetch／import を使わない。強制の再読み込みは移行の手順だけ） | 成功 | 1 | 0 | 0 | 0 |
| C-01 | 静的ファイルのキャッシュ（PR-C）：CSS だけの更新。一覧・新規作成・編集で、リンク・goto・F5 の各操作の直前に未取得の版へ変え、旧 ETag・200・新しい本文・適用された版、変えていないファイルの 304 | 成功 | 4 | 0 | 0 | 0 |
| C-02 | 静的ファイルのキャッシュ（PR-C）：入口が同じで下位のモジュール（深さ3・共通・評価）だけの更新。各操作で新しい版が実行され、評価の保存と詳細の表示が動く | 成功 | 1 | 0 | 0 | 0 |
| C-03 | 静的ファイルのキャッシュ（PR-C）：3画面の各操作（初回・再訪・リンク・goto・F5・強制の再読み込み）で HTML の要求がサーバーに届く（HTML の応答を変えない案の前提） | 成功 | 5 | 0 | 0 | 0 |
| C-04 | 静的ファイルのキャッシュ（PR-C）：従来の配信で保存された状態から、3画面の強制の再読み込み1回ずつで38件が no-cache になり、その後の各操作で新しい版を取得・適用する | 成功 | 1 | 0 | 0 | 0 |
| C-05 | 静的ファイルのキャッシュ（PR-C）：検出力。従来の配信と案A（no-cache だけ、同じ秒の更新）では、同じ手順が古い版の使用を検出する | 成功 | 2 | 0 | 0 | 0 |
| C-06 | 静的ファイルのキャッシュ（PR-C）：同じ秒の更新と古い時刻への置換も、各操作で新しい版を取得・適用する | 成功 | 2 | 0 | 0 | 0 |
| C-07 | 静的ファイルのキャッシュ（PR-C）：CSS の更新の後、通常の画面遷移で開いた編集画面で、生成中の評価のボタンが淡色・禁止のカーソルになり、押しても変わらず、終了後に戻る | 成功 | 1 | 0 | 0 | 0 |
| E-K01 | 仕上げ（PR-7）：キーボードだけ（Tab・Shift+Tab・Enter・Space・矢印・Esc）で付録Dの代表シナリオ（作成、未保存の頂上事象からの一次生成と自動保存、評価と二次生成、インスペクタの保存、手動追加、削除、出力メニュー、未保存の離脱の3択、折りたたんだ構造ナビ）を完了し、生成中の操作制限をキーボードで回避できない。通知（消えないエラーを含む複数）が出ている間も、Tab・Shift+Tab・矢印で移った先の操作とフォーカスの表示が、テストがスクロールせずに見えて通知に覆われず、フォーカスの後に通知が出ても隠れない（入力・選択・未保存の状態は変わらない） | 成功 | 28 | 0 | 0 | 0 |
| E-K02 | 仕上げ（PR-7）：ダイアログ（要因の切替・画面の移動の未保存確認、要因の削除、手動追加、一覧の削除、新規作成の離脱確認）の初期フォーカス、Tab・Shift+Tab で背後の画面へ出ない、Esc は取消、閉じた後の戻り先（消えていれば近くの要素）。折りたたんだ構造ナビの Esc と戻り先 | 成功 | 8 | 0 | 0 | 0 |
| E-K03 | 仕上げ（PR-7）：読み上げ領域（role=status polite・role=alert assertive）に、生成の開始・親ごとの結果・要約、生成の失敗、保存の失敗が書かれる（DOM の確認。スクリーンリーダーの読み上げは手動） | 成功 | 4 | 0 | 0 | 0 |
| E-V01 | 仕上げ（PR-7）：想定寸法と 2026-10-28 の実測値の寸法（DPR を含む）で、1280px 以上は3ペイン・未満は構造ナビの折りたたみ（開閉ボタンで重ねて表示）、主要な操作（作業ステップ・タブ・絞り込み・作業リスト・評価・保存・取消・削除・ヘッダー・操作バー・生成中の状態表示・生成ログ・通知・保存失敗の表示・各ダイアログ、一覧・新規作成）が表示領域の中に見え、中心と4点の最前面がその要素（通知などに覆われない。通知は作業エリアの下の専用の行で、覆った時点で失敗）。インスペクタの保存・取消は要因の編集欄が出た時点から（入力の前・入力中・保存の成功と失敗の後・要因の切替と部分更新の後も）スクロールなしで見える。実ブラウザの拡大・表示倍率の確認とは別に記録 | 成功 | 80 | 0 | 0 | 0 |
| E-V02 | 仕上げ（PR-7）：幅 1024px 以上で、ページ全体の横スクロールが出ない（構造ナビを開いた状態・生成中・ダイアログ表示中を含む）。構造ナビ・インスペクタは横にスクロールせず、1024px 未満では作業エリアだけが横にスクロールする | 成功 | 56 | 0 | 0 | 0 |
| E-V03 | 仕上げ（PR-7）：表示領域 900×600 と 1093×500 で、インスペクタの保存・取消とダイアログのボタンに、ページを横スクロールせずに届く（保存・取消は入力の前から追加のスクロールなしで見える） | 成功 | 8 | 0 | 0 | 0 |
| E-F01 | 仕上げ（PR-7）：BIZ UDPGothic を除いた代替フォント（Windows の代替・sans-serif・serif）で、一覧・新規作成・編集画面・ダイアログの見出し・ボタンが欠けず（省略記号の作業ステップ名を除く）、操作の並びが重ならず、主要な操作に届く。描画に使われたフォントを記録 | 成功 | 8 | 0 | 0 | 0 |

### テストごとの結果

| テスト | 結果 | 備考 |
|---|---|---|
| `tests/e2e/test_cache_manual_check.py::test_the_w02_tool_judges_a_correct_run_ok[chromium]` | 成功 |  |
| `tests/e2e/test_cache_manual_check.py::test_the_w02_tool_starts_from_files_cached_without_its_markers[chromium]` | 成功 |  |
| `tests/e2e/test_cache_manual_check.py::test_the_w02_tool_twice_in_the_same_profile[chromium]` | 成功 |  |
| `tests/e2e/test_cache_manual_check.py::test_the_w02_tool_refuses_a_reload_that_bypasses_the_cache[chromium]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_left_while_running_and_back_real_bfcache[chromium-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_the_browser_asks_again_after_the_return_real_bfcache[chromium-1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N03_sample_and_input_text_stay_text[1280x800-chromium]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N03_sample_and_input_text_stay_text[1440x900-chromium]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_without_sample_scenarios_the_form_still_creates[1280x800-chromium]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_without_sample_scenarios_the_form_still_creates[1440x900-chromium]` | 成功 |  |
| `tests/e2e/test_console_check.py::test_every_404_fails_the_favicon_ico_included[1280x800]` | 成功 |  |
| `tests/e2e/test_console_check.py::test_every_404_fails_the_favicon_ico_included[1440x900]` | 成功 |  |
| `tests/e2e/test_console_check.py::test_the_apps_icon_loads_without_an_error[1280x800]` | 成功 |  |
| `tests/e2e/test_console_check.py::test_the_apps_icon_loads_without_an_error[1440x900]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_the_display_check_tool_runs_its_checks_and_records_them` | 成功 |  |
| `tests/e2e/test_display_check.py::test_a_display_area_below_the_plan_is_flagged_for_the_users_decision` | 成功 |  |
| `tests/e2e/test_display_check.py::test_the_test_server_releases_its_folder_when_closed` | 成功 | 停止：自分で終了（終了コード 0）／一時フォルダの削除：1 回目 |
| `tests/e2e/test_display_check.py::test_a_python_child_starts_under_the_stand_in_launcher[direct]` | 成功 | 子は起動した（0.05 秒） |
| `tests/e2e/test_display_check.py::test_a_python_child_starts_under_the_stand_in_launcher[share-stdin-wait]` | 成功 | 子は起動した（0.1 秒） |
| `tests/e2e/test_display_check.py::test_a_python_child_starts_under_the_stand_in_launcher[own-stdin]` | 成功 | 子は起動した（0.1 秒） |
| `tests/e2e/test_display_check.py::test_a_python_child_starts_under_the_stand_in_launcher[null-handles]` | 成功 | 子は起動した（0.1 秒） |
| `tests/e2e/test_display_check.py::test_close_waits_for_the_apps_own_process` | 成功 | 停止：自分で終了（終了コード 0）。起動したプロセスの終了時にアプリはまだ動作中。アプリのプロセス（PID 1748）の終了を確認 |
| `tests/e2e/test_display_check.py::test_the_server_starts_again_in_the_same_folder` | 成功 |  |
| `tests/e2e/test_display_check.py::test_an_app_started_without_standard_handles_is_reported_at_once` | 成功 |  |
| `tests/e2e/test_display_check.py::test_a_child_that_ends_before_the_app_starts_is_reported_at_once` | 成功 |  |
| `tests/e2e/test_display_check.py::test_a_server_that_does_not_answer_is_reported_then_stopped` | 成功 |  |
| `tests/e2e/test_display_check.py::test_a_python_process_s_output_is_read_in_utf8` | 成功 |  |
| `tests/e2e/test_display_check.py::test_the_tool_removes_its_work_folder` | 成功 |  |
| `tests/e2e/test_display_check.py::test_a_work_folder_that_cannot_be_removed_is_not_ok` | 成功 |  |
| `tests/e2e/test_display_check.py::test_only_the_record_folders_work_is_removed` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_confirm_sends_nothing_and_the_next_enter_saves[\u4e00\u89a7\u306e\u6539\u540d-1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_confirm_sends_nothing_and_the_next_enter_saves[\u65b0\u898f\u4f5c\u6210\u306e\u30bf\u30a4\u30c8\u30eb-1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_confirm_sends_nothing_and_the_next_enter_saves[\u7de8\u96c6\u753b\u9762\u306e\u5206\u6790\u30bf\u30a4\u30c8\u30eb-1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_confirm_sends_nothing_and_the_next_enter_saves[\u624b\u52d5\u8ffd\u52a0\u306e\u30bf\u30a4\u30c8\u30eb-1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_a_save_on_the_confirming_enter_is_ng_whenever_it_comes[before-1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_a_save_on_the_confirming_enter_is_ng_whenever_it_comes[with-1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_a_save_on_the_confirming_enter_is_ng_whenever_it_comes[after-1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_no_save_on_the_next_enter_is_ng[1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_sent_but_not_saved_is_ng[1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_the_filter_follows_the_confirmed_text[1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_a_filter_that_does_not_follow_is_ng[1280x800]` | 成功 |  |
| `tests/e2e/test_display_check.py::test_judge_ime_a_request_while_filtering_is_ng[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G01_an_empty_top_event_stops_the_primary_generation[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G01_an_empty_top_event_stops_the_primary_generation[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G01_unsaved_top_event_and_reference_information_are_saved_first[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G01_unsaved_top_event_and_reference_information_are_saved_first[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G02_every_eligible_yes_parent_hidden_or_not_one_request_each[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G02_every_eligible_yes_parent_hidden_or_not_one_request_each[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G02_tertiary_generation_names_each_parent[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G02_tertiary_generation_names_each_parent[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G03_every_category_in_the_log_and_on_the_badges[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G03_a_parent_deleted_meanwhile_is_told_after_the_update[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G03_an_analysis_deleted_meanwhile_stops_the_rest[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G03_the_summary_when_nothing_was_created[no_candidates-warning-\u4e8c\u6b21\u8981\u56e0\u306e\u901a\u5e38\u751f\u6210\uff1a\u751f\u6210\u5019\u88dc\u304c\u3042\u308a\u307e\u305b\u3093\u3067\u3057\u305f\uff08LLM\u304c\u8981\u56e0\u3092\u8fd4\u3057\u307e\u305b\u3093\u3067\u3057\u305f\uff09-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G03_the_summary_when_nothing_was_created[all_excluded-warning-\u4e8c\u6b21\u8981\u56e0\u306e\u901a\u5e38\u751f\u6210\uff1a\u751f\u6210\u5019\u88dc\u306f\u3059\u3079\u3066\u54c1\u8cea\u30c1\u30a7\u30c3\u30af\u306a\u3069\u3067\u9664\u5916\u3055\u308c\u307e\u3057\u305f\uff08\u4e3b\u306a\u7406\u7531\uff1a\u89aa\u8981\u56e0\u306e\u8a00\u3044\u63db\u3048\uff09-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G03_the_summary_when_nothing_was_created[error-error-\u4e8c\u6b21\u8981\u56e0\u306e\u901a\u5e38\u751f\u6210\uff1a\u4f5c\u6210\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\uff08\u8a73\u7d30\u306f\u751f\u6210\u30ed\u30b0\uff09-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G05_new_factors_under_their_parents_and_the_page_state_kept[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G05_new_factors_under_their_parents_and_the_page_state_kept[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G07_additional_generation_of_primary_factors[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G07_additional_generation_of_primary_factors[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G07_additional_generation_below_a_no_an_unknown_and_a_secondary_parent[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation.py::test_E_G07_additional_generation_below_a_no_an_unknown_and_a_secondary_parent[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_left_while_running_and_back_simulated[answer-while-hidden-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_left_while_running_and_back_simulated[answer-after-return-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_left_while_preparing_and_back_simulated[save-ends-while-hidden-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_left_while_preparing_and_back_simulated[save-ends-after-return-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_left_while_finishing_and_back_simulated[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_a_page_that_was_not_generating_comes_back_unchanged_simulated[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_leave.py::test_E_G08_the_browser_asks_again_after_the_return_simulated[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_reload_restores_the_result_without_any_text_or_draft[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_reload_restores_the_result_without_any_text_or_draft[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_a_reload_during_a_generation_restores_no_running_state[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_other_analyses_and_other_tabs[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_other_analyses_and_other_tabs[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_a_parent_no_longer_there_is_noted_and_close_removes_it[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_storage_that_cannot_be_used_keeps_the_page_working[quota-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_storage_that_cannot_be_used_keeps_the_page_working[blocked-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_storage_that_cannot_be_used_keeps_the_page_working[broken-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_a_failed_write_never_brings_back_the_previous_log[write-fails-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_log.py::test_E_G06_a_failed_write_never_brings_back_the_previous_log[write-and-remove-fail-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G04_writes_and_moves_are_held_back_browsing_is_free[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G04_writes_and_moves_are_held_back_browsing_is_free[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G04_delete_and_add_are_refused_when_confirmed_during_a_generation[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G04_an_inconsistent_parents_buttons_stay_disabled_after_the_end[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G08_the_browser_asks_while_a_generation_runs_without_any_draft[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_a_save_in_flight_is_awaited_named_and_a_failure_stops_it[judgement-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_a_save_in_flight_is_awaited_named_and_a_failure_stops_it[factor-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_a_save_in_flight_is_awaited_named_and_a_failure_stops_it[top-event-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_a_save_in_flight_is_awaited_named_and_a_failure_stops_it[context-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_a_save_in_flight_is_awaited_named_and_a_failure_stops_it[title-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_a_save_in_flight_that_succeeds_lets_the_generation_go_on[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_the_judgement_queue_of_a_factor_is_awaited_to_its_end[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_cancelling_sends_nothing_later_and_leaves_a_later_generation_alone[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_cancelling_during_the_automatic_save[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_after_10_seconds_a_note_and_no_time_limit[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_no_detail_request_waiting_and_read_before_and_only_the_last_choice[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_no_detail_request_waiting_and_read_before_and_only_the_last_choice[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_a_second_read_keeps_the_draft_and_tells_a_changed_saved_value[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_cancel_after_a_second_read_restores_the_values_read[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_an_older_answer_after_the_generation_is_dropped[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_a_failed_second_read_is_not_a_failed_first_read[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G11_title_and_inspector_saves_are_held_back_and_the_two_choices[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G11_title_and_inspector_saves_are_held_back_and_the_two_choices[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G11_no_draft_no_question[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_every_ending_lifts_the_restrictions[success-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_every_ending_lifts_the_restrictions[partial-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_every_ending_lifts_the_restrictions[network-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_every_ending_lifts_the_restrictions[http-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_every_ending_lifts_the_restrictions[stub-error-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_every_ending_lifts_the_restrictions[js-error-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_a_slow_update_keeps_the_restrictions_until_it_has_ended[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_a_failed_update_ends_it_too[with-input-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G12_a_failed_update_ends_it_too[without-input-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_a_save_is_never_rolled_back_by_an_older_second_read[answer-after-the-save-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_a_save_is_never_rolled_back_by_an_older_second_read[answer-while-saving-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G10_save_and_go_does_not_cross_a_second_read_either[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G04_exports_are_refused_with_modifier_keys_and_the_middle_button[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_details_held_back_by_a_preparation_are_read_when_it_ends[cancel-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_details_held_back_by_a_preparation_are_read_when_it_ends[save-failure-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_run.py::test_E_G09_details_held_back_by_a_preparation_are_read_when_it_ends[page-error-before-the-log-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_saves.py::test_E_E20_preparation_waits_for_a_queued_judgement_of_the_same_factor[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_saves.py::test_E_E20_preparation_waits_for_a_queued_judgement_of_the_same_factor[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation_saves.py::test_E_E20_a_generation_started_while_leaving_waits_is_not_overridden[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_saves.py::test_E_E20_a_generation_started_while_leaving_waits_is_not_overridden[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_generation_saves.py::test_E_E20_finishing_lasts_until_the_partial_update_has_ended[success-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_saves.py::test_E_E20_finishing_lasts_until_the_partial_update_has_ended[failure-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_saves.py::test_E_E20_discard_is_refused_while_a_save_is_in_flight[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_generation_saves.py::test_E_E20_discard_is_refused_while_a_save_is_in_flight[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_seven_fields_one_request_without_the_judgement_shown_everywhere[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_seven_fields_one_request_without_the_judgement_shown_everywhere[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_saved_status_compares_after_normalisation_and_cancel_restores[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_saved_status_compares_after_normalisation_and_cancel_restores[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_input_typed_during_the_save_stays_unsaved[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_input_typed_during_the_save_stays_unsaved[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_empty_title_failure_and_a_failed_display_update_are_told_apart[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_empty_title_failure_and_a_failed_display_update_are_told_apart[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_nothing_can_be_typed_or_saved_before_the_details_arrived[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E14_nothing_can_be_typed_or_saved_before_the_details_arrived[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_counts_from_the_server_cancel_escape_and_failure_keep_the_draft[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_counts_from_the_server_cancel_escape_and_failure_keep_the_draft[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_deleting_the_edited_factors_ancestor_drops_that_draft_and_selects_the_parent[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_deleting_the_edited_factors_ancestor_drops_that_draft_and_selects_the_parent[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_deleting_another_factor_keeps_the_draft[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_deleting_another_factor_keeps_the_draft[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_confirming_asks_again_and_a_top_level_delete_selects_the_top_event[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_confirming_asks_again_and_a_top_level_delete_selects_the_top_event[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_place_shown_and_fixed_duplicate_refused_in_the_dialog[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_place_shown_and_fixed_duplicate_refused_in_the_dialog[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_auto_selection_asks_about_the_draft_and_never_sends_the_add_again[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_auto_selection_asks_about_the_draft_and_never_sends_the_add_again[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_a_later_choice_is_never_replaced_by_the_selection[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_a_later_choice_is_never_replaced_by_the_selection[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_choosing_a_b_a_while_the_update_is_held_keeps_the_users_choice[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_choosing_a_b_a_while_the_update_is_held_keeps_the_users_choice[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_a_b_a_during_a_generation_keeps_the_users_choice[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_a_b_a_during_a_generation_keeps_the_users_choice[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_two_adds_while_the_update_is_held_select_the_last_one[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_two_adds_while_the_update_is_held_select_the_last_one[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_no_delete_while_the_edited_factors_save_is_in_flight[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_no_delete_while_the_edited_factors_save_is_in_flight[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_confirming_is_refused_when_a_save_started_meanwhile[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E16_confirming_is_refused_when_a_save_started_meanwhile[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_a_later_add_completed_while_asking_is_the_one_selected[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_a_later_add_completed_while_asking_is_the_one_selected[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_continue_keeps_a_and_its_draft_when_a_later_add_completed_while_asking[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_continue_keeps_a_and_its_draft_when_a_later_add_completed_while_asking[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_a_later_add_whose_update_is_in_flight_while_asking_is_the_one_selected[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_a_later_add_whose_update_is_in_flight_while_asking_is_the_one_selected[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_continue_keeps_a_and_its_draft_when_a_later_adds_update_was_in_flight[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_continue_keeps_a_and_its_draft_when_a_later_adds_update_was_in_flight[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_continue_also_covers_an_add_sent_before_the_answer_and_completed_after[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_inspector.py::test_E_E17_continue_also_covers_an_add_sent_before_the_answer_and_completed_after[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_E_E08_every_category_is_named_in_its_group[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_E_E08_every_category_is_named_in_its_group[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_other_analysis_below_blocks_the_factor_and_every_ancestor[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_other_analysis_below_blocks_the_factor_and_every_ancestor[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_a_walk_that_cannot_be_completed_blocks_deletion[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_a_walk_that_cannot_be_completed_blocks_deletion[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_failed_lookups_block_every_deletion_and_the_page_still_opens[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_failed_lookups_block_every_deletion_and_the_page_still_opens[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_missing_parent_and_upper_factors_are_deleted_with_exactly_their_subtree[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_missing_parent_and_upper_factors_are_deleted_with_exactly_their_subtree[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_normal_generation_uses_consistent_yes_parents_only[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_normal_generation_uses_consistent_yes_parents_only[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_no_request_when_every_yes_parent_is_inconsistent[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_no_request_when_every_yes_parent_is_inconsistent[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_additional_generation_and_manual_add_below_inconsistent_parents_are_refused[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_integrity.py::test_additional_generation_and_manual_add_below_inconsistent_parents_are_refused[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_nothing_unsaved_leaves_without_a_question[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_nothing_unsaved_leaves_without_a_question[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_continue_and_escape_keep_the_input_and_the_focus[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_continue_and_escape_keep_the_input_and_the_focus[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_discard_and_go[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_discard_and_go[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_save_and_go_saves_in_order_then_leaves[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_save_and_go_saves_in_order_then_leaves[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_partial_failure_retry_sends_the_failed_one_only[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_partial_failure_retry_sends_the_failed_one_only[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_discard_after_a_partial_success[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_discard_after_a_partial_success[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_browser_navigation_gets_the_browsers_confirmation_only[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_browser_navigation_gets_the_browsers_confirmation_only[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_title_being_saved_asks_the_browser_too[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E12_title_being_saved_asks_the_browser_too[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_every_source_is_validated_before_anything_is_sent[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_every_source_is_validated_before_anything_is_sent[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_order_and_the_target_fixed_when_editing_started[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_order_and_the_target_fixed_when_editing_started[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_a_failure_does_not_stop_the_others_and_retry_sends_it_only[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_a_failure_does_not_stop_the_others_and_retry_sends_it_only[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_sources_of_a_gone_analysis_are_not_sent[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_sources_of_a_gone_analysis_are_not_sent[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_saves_in_flight_are_awaited_and_a_slow_one_is_explained[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_saves_in_flight_are_awaited_and_a_slow_one_is_explained[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_nothing_is_accepted_while_a_generation_runs[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_leave.py::test_E_E20_nothing_is_accepted_while_a_generation_runs[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E19_two_tabs_a_judgement_changed_in_the_other_tab[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E19_two_tabs_a_judgement_changed_in_the_other_tab[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E03_back_to_unknown_from_the_inspector[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E03_back_to_unknown_from_the_inspector[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E04_no_and_unknown_filters[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E04_no_and_unknown_filters[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E07_deleting_a_primary_factor_selects_the_top_event[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E07_deleting_a_primary_factor_selects_the_top_event[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E08_child_actions_are_refused_for_every_inconsistent_category[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_E_E08_child_actions_are_refused_for_every_inconsistent_category[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_each_pane_scrolls_on_its_own[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_each_pane_scrolls_on_its_own[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_generation_marks_each_parent_and_keeps_it_after_the_update[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_manual_items.py::test_generation_marks_each_parent_and_keeps_it_after_the_update[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E01_without_factors_step_1_and_the_top_event[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E01_without_factors_step_1_and_the_top_event[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E01_with_factors_step_2_and_the_first_primary_factor[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E01_with_factors_step_2_and_the_first_primary_factor[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E02_every_route_selects_and_all_views_agree[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E02_every_route_selects_and_all_views_agree[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E02_the_inspector_shows_the_saved_details_of_the_latest_choice[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E02_the_inspector_shows_the_saved_details_of_the_latest_choice[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E03_judgement_is_saved_and_shown_everywhere[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E03_judgement_is_saved_and_shown_everywhere[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E03_failure_leaves_the_judgement_and_rapid_clicks_end_on_the_last[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E03_failure_leaves_the_judgement_and_rapid_clicks_end_on_the_last[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E04_filter_hides_rows_highlights_the_tree_and_keeps_the_targets[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E04_filter_hides_rows_highlights_the_tree_and_keeps_the_targets[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E05_tabs_by_keyboard_keep_the_selection[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E05_tabs_by_keyboard_keep_the_selection[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E06_reload_restores_selection_step_tab_scroll_and_filter[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E06_reload_restores_selection_step_tab_scroll_and_filter[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E06_invalid_hash_gives_the_default_display[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E06_invalid_hash_gives_the_default_display[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E06_without_web_storage_the_screen_still_works[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E06_without_web_storage_the_screen_still_works[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E09_demo_points_hidden_and_markup_stays_text[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_E_E09_demo_points_hidden_and_markup_stays_text[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[chrome-1905x945]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[edge-1912x914]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_size_check_refuses_what_it_must_not_tolerate[changed-after-the-app-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_size_check_refuses_what_it_must_not_tolerate[over-the-tolerance-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_size_check_refuses_what_it_must_not_tolerate[across-1280-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_size_check_refuses_what_it_must_not_tolerate[a-case-without-tolerance-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_layout_check_catches_what_does_not_fit[inspector-past-the-right-edge-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_layout_check_catches_what_does_not_fit[inspector-2px-past-the-right-edge-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_layout_check_catches_what_does_not_fit[page-scrolls-sideways-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_layout_check_catches_what_does_not_fit[panes-below-the-bottom-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_layout_check_catches_what_does_not_fit[control-covered-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_page.py::test_the_layout_check_catches_what_does_not_fit[control-hidden-1280x800]` | 成功 |  |
| `tests/e2e/test_edit_pr4_layout.py::test_PR4_new_controls_are_visible_and_not_covered[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_pr4_layout.py::test_PR4_new_controls_are_visible_and_not_covered[chrome-1905x945]` | 成功 |  |
| `tests/e2e/test_edit_pr4_layout.py::test_PR4_new_controls_are_visible_and_not_covered[edge-1912x914]` | 成功 |  |
| `tests/e2e/test_edit_pr5_layout.py::test_PR5_inspector_editor_and_dialogs_are_visible_and_not_covered[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_pr5_layout.py::test_PR5_inspector_editor_and_dialogs_are_visible_and_not_covered[chrome-1905x945]` | 成功 |  |
| `tests/e2e/test_edit_pr5_layout.py::test_PR5_inspector_editor_and_dialogs_are_visible_and_not_covered[edge-1912x914]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_detail_save_keeps_focus_scroll_and_typed_input[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_detail_save_keeps_focus_scroll_and_typed_input[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_manual_add_and_delete_select_and_keep_the_focus[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_manual_add_and_delete_select_and_keep_the_focus[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_factor_removed_elsewhere_moves_selection_and_focus_up[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_factor_removed_elsewhere_moves_selection_and_focus_up[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_analysis_deleted_elsewhere_stops_the_operations[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_analysis_deleted_elsewhere_stops_the_operations[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_failed_fetch_keeps_typed_input_or_reloads[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_failed_fetch_keeps_typed_input_or_reloads[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_no_fetch_while_a_generation_runs_one_after[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_no_fetch_while_a_generation_runs_one_after[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_dialog_gives_the_focus_back_after_an_update[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_dialog_gives_the_focus_back_after_an_update[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_a_factor_added_before_a_generation_leaves_a_newer_selection[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E07_a_factor_added_before_a_generation_leaves_a_newer_selection[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_answer_fetched_before_a_judgement_is_discarded[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_answer_fetched_before_a_judgement_is_discarded[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_answer_without_the_confirmed_judgement_is_not_applied[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_answer_without_the_confirmed_judgement_is_not_applied[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_judgement_changed_elsewhere_does_not_stop_later_updates[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_judgement_changed_elsewhere_does_not_stop_later_updates[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_no_fetch_while_the_next_queued_judgement_is_saved[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_no_fetch_while_the_next_queued_judgement_is_saved[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_answer_fetched_before_a_top_event_save_is_discarded[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_refresh.py::test_E_E19_answer_fetched_before_a_top_event_save_is_discarded[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_stored_crlf_and_spaces_are_saved_and_restoring_is_saved_again[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_stored_crlf_and_spaces_are_saved_and_restoring_is_saved_again[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_save_buttons_send_one_request_and_keep_demo_points[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_save_buttons_send_one_request_and_keep_demo_points[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_input_typed_during_a_save_stays_unsaved[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_input_typed_during_a_save_stays_unsaved[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_a_failed_save_keeps_the_input_and_the_reason[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_a_failed_save_keeps_the_input_and_the_reason[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_automatic_save_before_generation_is_the_same_save[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_automatic_save_before_generation_is_the_same_save[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_a_failed_automatic_save_or_an_empty_top_event_starts_nothing[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_step1.py::test_E_E10_a_failed_automatic_save_or_an_empty_top_event_starts_nothing[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_summary.py::test_E_E13_counts_come_from_the_data_and_follow_judgements_and_updates[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_summary.py::test_E_E13_counts_come_from_the_data_and_follow_judgements_and_updates[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_summary.py::test_E_E13_export_table_and_links_download_the_exports[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_summary.py::test_E_E13_export_table_and_links_download_the_exports[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_summary.py::test_E_E13_header_menu_is_the_lists_and_downloads_ask_nothing[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_summary.py::test_E_E13_header_menu_is_the_lists_and_downloads_ask_nothing[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_every_route_asks_and_continue_or_escape_keeps_everything[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_every_route_asks_and_continue_or_escape_keeps_everything[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_save_and_go_saves_to_the_edited_factor_not_the_chosen_one[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_save_and_go_saves_to_the_edited_factor_not_the_chosen_one[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_empty_title_sends_nothing_and_switches_nothing[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_empty_title_sends_nothing_and_switches_nothing[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_restored_input_same_factor_and_step1_alone_do_not_ask[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_restored_input_same_factor_and_step1_alone_do_not_ask[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_the_list_saves_factor_top_event_context_in_order_partial_failure_retry[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_the_list_saves_factor_top_event_context_in_order_partial_failure_retry[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_a_b_a_leaves_one_source_and_one_save[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_a_b_a_leaves_one_source_and_one_save[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_a_switch_waits_for_the_save_and_its_answer_stays_with_its_factor[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_a_switch_waits_for_the_save_and_its_answer_stays_with_its_factor[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_details_loading_and_the_first_answer_of_a_b_a[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_details_loading_and_the_first_answer_of_a_b_a[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_an_update_fetched_before_the_save_does_not_roll_it_back[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_an_update_fetched_before_the_save_does_not_roll_it_back[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_draft_survives_another_add_and_a_generations_result[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_draft_survives_another_add_and_a_generations_result[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_the_edited_factor_removed_elsewhere_keeps_the_input_and_sends_nowhere[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_the_edited_factor_removed_elsewhere_keeps_the_input_and_sends_nowhere[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_the_analysis_removed_keeps_the_input_and_stops[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_the_analysis_removed_keeps_the_input_and_stops[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_generation_two_choices_no_factor_save_and_browsing_stays_free[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_generation_two_choices_no_factor_save_and_browsing_stays_free[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_a_generation_that_ended_while_the_two_choices_were_open_asks_again[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E18_a_generation_that_ended_while_the_two_choices_were_open_asks_again[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_after_a_partial_success_the_focus_returns_to_the_replaced_control[1280x800-continue]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_after_a_partial_success_the_focus_returns_to_the_replaced_control[1280x800-escape]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_after_a_partial_success_the_focus_returns_to_the_replaced_control[1440x900-continue]` | 成功 |  |
| `tests/e2e/test_edit_switch.py::test_E_E15_after_a_partial_success_the_focus_returns_to_the_replaced_control[1440x900-escape]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_enter_saves_escape_and_cancel_restore[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_enter_saves_escape_and_cancel_restore[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_ime_enter_and_escape_do_nothing[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_ime_enter_and_escape_do_nothing[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_focus_on_save_or_cancel_does_not_save_leaving_the_input_does[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_focus_on_save_or_cancel_does_not_save_leaving_the_input_does[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_empty_or_too_long_is_not_sent_and_stops_leaving[1280x800-   -\u30bf\u30a4\u30c8\u30eb\u306f\u5fc5\u9808\u3067\u3059]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_empty_or_too_long_is_not_sent_and_stops_leaving[1280x800-\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042-\u30bf\u30a4\u30c8\u30eb\u306f255\u6587\u5b57\u4ee5\u5185\u3067\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_empty_or_too_long_is_not_sent_and_stops_leaving[1440x900-   -\u30bf\u30a4\u30c8\u30eb\u306f\u5fc5\u9808\u3067\u3059]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_empty_or_too_long_is_not_sent_and_stops_leaving[1440x900-\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042\u3042-\u30bf\u30a4\u30c8\u30eb\u306f255\u6587\u5b57\u4ee5\u5185\u3067\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_255_characters_counted_as_code_points_are_accepted[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_255_characters_counted_as_code_points_are_accepted[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_leaving_waits_for_the_save_the_blur_started[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_leaving_waits_for_the_save_the_blur_started[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_a_failed_save_stays_and_is_not_sent_again_unchanged[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_a_failed_save_stays_and_is_not_sent_again_unchanged[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_title_and_step_1_both_changed[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_title_and_step_1_both_changed[1440x900]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_failed_partial_update_keeps_the_title_input_and_gone_stops_it[1280x800]` | 成功 |  |
| `tests/e2e/test_edit_title.py::test_E_E11_failed_partial_update_keeps_the_title_input_and_gone_stops_it[1440x900]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_E_X01_no_request_leaves_the_app[1280x800]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_E_X01_no_request_leaves_the_app[1440x900]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_E_X01_every_screen_has_the_apps_own_icon[1280x800]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_E_X01_every_screen_has_the_apps_own_icon[1440x900]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_notifications_success_closes_error_stays[1280x800]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_notifications_success_closes_error_stays[1440x900]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_notification_stack_stays_bounded[1280x800]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_notification_stack_stays_bounded[1440x900]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_list_works_without_web_storage[1280x800]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_list_works_without_web_storage[1440x900]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_safe_storage_round_trip_when_available[1280x800]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_safe_storage_round_trip_when_available[1440x900]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_skip_link_header_and_dialog_focus[1280x800]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_skip_link_header_and_dialog_focus[1440x900]` | 成功 |  |
| `tests/e2e/test_foundation.py::test_stub_modes_through_the_generate_api` | 成功 |  |
| `tests/e2e/test_foundation.py::test_stub_guard_blocks_real_provider_and_outbound_http` | 成功 |  |
| `tests/e2e/test_legacy_compat.py::test_title_step1_and_generation_from_the_new_page[1280x800]` | 成功 |  |
| `tests/e2e/test_legacy_compat.py::test_title_step1_and_generation_from_the_new_page[1440x900]` | 成功 |  |
| `tests/e2e/test_legacy_compat.py::test_details_manual_add_additional_generation_delete_and_export[1280x800]` | 成功 |  |
| `tests/e2e/test_legacy_compat.py::test_details_manual_add_additional_generation_delete_and_export[1440x900]` | 成功 |  |
| `tests/e2e/test_legacy_compat.py::test_saving_dialogs_and_delete_messages_use_the_shared_notifications[1280x800]` | 成功 |  |
| `tests/e2e/test_legacy_compat.py::test_saving_dialogs_and_delete_messages_use_the_shared_notifications[1440x900]` | 成功 |  |
| `tests/e2e/test_legacy_compat.py::test_generation_messages_once_each_with_their_kind[1280x800]` | 成功 |  |
| `tests/e2e/test_legacy_compat.py::test_generation_messages_once_each_with_their_kind[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L01_order_and_open_analysis[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L01_order_and_open_analysis[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L02_rename_enter_escape_cancel[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L02_rename_enter_escape_cancel[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L02_ime_conversion_enter_and_escape_do_not_save[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L02_ime_conversion_enter_and_escape_do_not_save[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L03_validation_empty_and_too_long[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L03_validation_empty_and_too_long[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L03_server_reason_is_shown_as_is[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L03_server_reason_is_shown_as_is[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L04_browser_tab_title_is_unchanged[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L04_browser_tab_title_is_unchanged[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_no_change_means_no_confirmation[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_no_change_means_no_confirmation[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_continue_editing_and_escape_keep_the_draft[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_continue_editing_and_escape_keep_the_draft[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_save_and_go[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_save_and_go[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_discard_and_go[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_discard_and_go[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_save_and_go_failure_stays_on_page[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_save_and_go_failure_stays_on_page[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_leaving_waits_for_a_save_in_flight[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_leaving_waits_for_a_save_in_flight[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_rename_of_another_row[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_rename_of_another_row[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_browser_leave_confirmation_only_when_changed[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L05_browser_leave_confirmation_only_when_changed[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L06_delete_dialog_cancel_escape_failure_and_confirm[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L06_delete_dialog_cancel_escape_failure_and_confirm[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L06_count_is_the_value_when_the_list_was_shown[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L06_count_is_the_value_when_the_list_was_shown[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L07_export_menu_keyboard_and_links[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L07_export_menu_keyboard_and_links[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L07_only_one_menu_switching_down_and_up[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L07_only_one_menu_switching_down_and_up[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L07_download_while_renaming_has_no_leave_confirmation[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L07_download_while_renaming_has_no_leave_confirmation[1440x900]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L08_empty_list[1280x800]` | 成功 |  |
| `tests/e2e/test_list_page.py::test_E_L08_empty_list[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N01_two_columns_and_create[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N01_two_columns_and_create[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N02_blank_and_too_long_titles_are_not_sent[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N02_blank_and_too_long_titles_are_not_sent[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_title_enter_submits_but_the_ime_confirmation_enter_does_not[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_title_enter_submits_but_the_ime_confirmation_enter_does_not[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N03_sample_preview_transfer_and_create[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N03_sample_preview_transfer_and_create[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N04_without_input_there_is_no_confirmation[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N04_without_input_there_is_no_confirmation[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N04_input_asks_to_continue_or_discard[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N04_input_asks_to_continue_or_discard[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N04_discard_after_a_sample_transfer[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N04_discard_after_a_sample_transfer[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N05_double_click_creates_one_analysis[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N05_double_click_creates_one_analysis[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N05_further_submits_are_ignored_once_sent[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N05_further_submits_are_ignored_once_sent[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N05_restored_from_the_back_forward_cache_the_form_is_usable[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N05_restored_from_the_back_forward_cache_the_form_is_usable[1440x900]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N06_browser_leave_confirmation_only_with_input[1280x800]` | 成功 |  |
| `tests/e2e/test_new_analysis_page.py::test_E_N06_browser_leave_confirmation_only_with_input[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1920x1080]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1536x730]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1280x620]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1366x650]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1024x683]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[900x600]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome100-1920x945]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome125-1536x756]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome150-1280x630]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[edge125-1530x731]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[900x600]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1024x683]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[chrome150-1280x630]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_tab_shift_tab_and_arrows_show_the_focus_with_notifications[1280x620]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_notifications_are_reached_from_the_top_of_the_page[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_notifications_are_reached_from_the_top_of_the_page[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[900x600]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[1024x683]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[chrome150-1280x630]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_a_notification_after_the_focus_hides_nothing_and_takes_nothing[1280x620]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[900x600]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1024x683]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[chrome150-1280x630]` | 成功 |  |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1280x620]` | 成功 |  |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[windows-fallback-1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[windows-fallback-1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[sans-serif-1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[sans-serif-1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[serif-1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[serif-1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_fonts.py::test_the_font_checks_catch_cut_off_and_overlapping_text[button-cut-off-.edit-header__actions .ui-btn { width: 24px; overflow: hidden; white-space: nowrap; }-1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_fonts.py::test_the_font_checks_catch_cut_off_and_overlapping_text[buttons-overlap-.edit-header__actions > * + * { margin-left: -40px; }-1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K01_the_representative_scenario_by_keyboard_only[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K01_the_representative_scenario_by_keyboard_only[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K01_the_representative_scenario_by_keyboard_only[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K02_edit_dialogs_focus_tab_escape_and_return[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K02_edit_dialogs_focus_tab_escape_and_return[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K02_edit_dialogs_focus_tab_escape_and_return[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K02_list_and_new_dialogs[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K02_list_and_new_dialogs[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K02_list_and_new_dialogs[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K03_generation_progress_results_and_failures_reach_the_live_regions[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_E_K03_generation_progress_results_and_failures_reach_the_live_regions[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_the_focus_check_catches_a_dialog_that_is_not_modal[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_the_focus_check_catches_a_dialog_that_is_not_modal[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_the_announcement_check_catches_a_missing_live_region[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_the_announcement_check_catches_a_missing_live_region[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_tab_to_follows_a_control_drawn_again_while_it_tabs[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_keyboard.py::test_tab_to_follows_a_control_drawn_again_while_it_tabs[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_screens.py::test_E_V01_representative_screens_of_a_generation[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_screens.py::test_E_V01_representative_screens_of_a_generation[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_screens.py::test_E_V01_representative_screens_of_a_generation[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1920x1080]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1536x730]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1280x620]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1366x650]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1024x683]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[900x600]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome100-1920x945]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome125-1536x756]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome150-1280x630]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[edge125-1530x731]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1920x1080]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1536x730]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x620]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1366x650]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1024x683]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[900x600]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome100-1920x945]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome125-1536x756]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome150-1280x630]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[edge125-1530x731]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1920x1080]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1536x730]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1280x620]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1366x650]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1024x683]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[900x600]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome100-1920x945]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome125-1536x756]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome150-1280x630]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[edge125-1530x731]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1280x800]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1440x900]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1920x1080]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1536x730]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1280x620]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1366x650]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1024x683]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[900x600]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome100-1920x945]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome125-1536x756]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome150-1280x630]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[edge125-1530x731]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[page-min-width-1100-1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[three-panes-below-1280-edge150-1275x609]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[notifications-over-the-inspector-1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[bar-in-the-scroll-area-1093x500]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[covered-control-900x600]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[inspector-out-of-view-900x600]` | 成功 |  |
| `tests/e2e/test_pr7_viewports.py::test_reach_tells_as_shown_a_pane_scroll_and_a_notification_over_it_apart[1093x500]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_00_the_cache_tests_keep_their_conditions` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_01_the_icon_is_revalidated_as_the_other_static_files[1280x800]` | 成功 | ブラウザ自身の favicon の要求 5 件（200・304・304・304・304） |
| `tests/e2e/test_static_cache.py::test_C_01_C_03_only_the_css_changes_and_each_operation_fetches_its_own_version[edit-1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_01_C_03_only_the_css_changes_and_each_operation_fetches_its_own_version[list-1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_01_C_03_only_the_css_changes_and_each_operation_fetches_its_own_version[new-1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_02_only_modules_below_the_entry_change_and_run[1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_04_from_the_old_serving_after_ctrl_f5_on_three_screens[1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_05_the_same_steps_see_old_files_without_the_change[baseline-1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_05_the_same_steps_see_old_files_without_the_change[nocache-only-1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_06_same_second_and_older_time_changes_are_fetched[same-second-1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_06_same_second_and_older_time_changes_are_fetched[older-time-1280x800]` | 成功 |  |
| `tests/e2e/test_static_cache.py::test_C_07_the_judgement_buttons_look_disabled_after_a_css_update[1280x800]` | 成功 |  |

### 失敗したテストの証跡（実際にあるファイル）

「失敗時の証跡の設定」は、pytest-playwright に残させるものの設定で、ファイルが残ったことは示しません。ここには、この記録を書いた時点で各テストの保存先に実際にあったファイルを書きます。失敗したテストでは、この記録もページの終了処理の初めに画面を撮ります（page-at-failure.png。撮れなかったときは理由を書きます。pytest-playwright の画面 test-failed-1.png は、撮れなかったときに理由を残しません）。

失敗したテストはありません。

### 画面寸法の要求と実測（PR3-LAYOUT）

要求した表示領域（Playwright の viewport、CSS ピクセル）と、ブラウザで測った値です。アプリの表示前（about:blank）と、編集画面の表示後に測ります。client は `document.documentElement.clientWidth`×`clientHeight`（整数。利用者の PC で測った量）、visualViewport は小数の値です。

差を許容するのは chrome-1905x945（各軸 +1 CSS px まで）だけです（検証条件の限定変更。2026-10-06 の利用者の指示）。実測が要求と同じか各軸 +1 CSS ピクセルまで大きく、その差がアプリの表示前からあって表示後も同じで、要求と実測の間（両端を含む）にレイアウトの境界（1280px、ペインの幅の変化が止まる幅など。`tests/e2e/support.py` の LAYOUT_BOUNDARIES）がない場合に限ります。そのときも、ページ全体の横スクロール、ペインの収まり、主要な操作の表示と被覆の検査は、実測の寸法を基準に最後まで行います。ほかのケース（1280×800 と edge-1912x914）は一致が必要です。

| テスト | 要求 | 表示前（about:blank） | 表示後（編集画面） | 判定 |
|---|---|---|---|---|
| `tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[1280x800]` | 1280×800 | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | 一致 |
| `tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[chrome-1905x945]` | 1905×945（差の許容 +1） | client 1905×945、inner 1905×945、visualViewport 1905×945（scale 1）、devicePixelRatio 1、scroll 1905×945 | client 1905×945、inner 1905×945、visualViewport 1905×945（scale 1）、devicePixelRatio 1、scroll 1905×945 | 一致 |
| `tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes[edge-1912x914]` | 1912×914 | client 1912×914、inner 1912×914、visualViewport 1912×914（scale 1）、devicePixelRatio 1、scroll 1912×914 | client 1912×914、inner 1912×914、visualViewport 1912×914（scale 1）、devicePixelRatio 1、scroll 1912×914 | 一致 |

### 表示領域の記録（PR-7：E-V01〜E-V03・E-F01）

Playwright で表示領域の寸法（と devicePixelRatio）を指定した自動テストの記録です。**ブラウザの拡大・Windows の表示倍率を実際に変えた確認ではありません**（実機の確認は別に記録します。manual-check-pr7.md）。実測は `document.documentElement.clientWidth`×`clientHeight` と `window.devicePixelRatio` です。

| テスト | 寸法の出所 | 要求（CSS px・DPR） | 実測 | レイアウト | 備考 |
|---|---|---|---|---|---|
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1280x800]` | 基本寸法（計画 第8.0節） | 1280×800・DPR 1（既定） | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1440x900]` | 基本寸法（計画 第8.0節） | 1440×900・DPR 1（既定） | client 1440×900、inner 1440×900、visualViewport 1440×900（scale 1）、devicePixelRatio 1、scroll 1440×900 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1920x1080]` | 想定寸法：1920×1080・倍率100% | 1920×1080・DPR 1（既定） | client 1920×1080、inner 1920×1080、visualViewport 1920×1080（scale 1）、devicePixelRatio 1、scroll 1920×1080 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1536x730]` | 想定寸法：1920×1080・125% | 1536×730・DPR 1（既定） | client 1536×730、inner 1536×730、visualViewport 1536×730（scale 1）、devicePixelRatio 1、scroll 1536×730 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1280x620]` | 想定寸法：1920×1080・150% | 1280×620・DPR 1（既定） | client 1280×620、inner 1280×620、visualViewport 1280×620（scale 1）、devicePixelRatio 1、scroll 1280×620 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1366x650]` | 想定寸法：1366×768・100% | 1366×650・DPR 1（既定） | client 1366×650、inner 1366×650、visualViewport 1366×650（scale 1）、devicePixelRatio 1、scroll 1366×650 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1093x500]` | 想定寸法：1366×768・125% | 1093×500・DPR 1（既定） | client 1093×500、inner 1093×500、visualViewport 1093×500（scale 1）、devicePixelRatio 1、scroll 1093×500 | 構造ナビの折りたたみ | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1024x683]` | 想定寸法 | 1024×683・DPR 1（既定） | client 1024×683、inner 1024×683、visualViewport 1024×683（scale 1）、devicePixelRatio 1、scroll 1024×683 | 構造ナビの折りたたみ | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[900x600]` | 想定寸法（1024px 未満） | 900×600・DPR 1（既定） | client 900×600、inner 900×600、visualViewport 900×600（scale 1）、devicePixelRatio 1、scroll 900×600 | 構造ナビの折りたたみ | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome100-1920x945]` | 実測値 2026-10-28：Chrome 拡大100% | 1920×945・DPR 1 | client 1920×945、inner 1920×945、visualViewport 1920×945（scale 1）、devicePixelRatio 1、scroll 1920×945 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome125-1536x756]` | 実測値 2026-10-28：Chrome 拡大125% | 1536×756・DPR 1.25 | client 1536×756、inner 1536×756、visualViewport 1536×756（scale 1）、devicePixelRatio 1.25、scroll 1536×756 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome150-1280x630]` | 実測値 2026-10-28：Chrome 拡大150% | 1280×630・DPR 1.5 | client 1280×630、inner 1280×630、visualViewport 1280×630（scale 1）、devicePixelRatio 1.5、scroll 1280×630 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[edge125-1530x731]` | 実測値 2026-10-28：Edge 拡大125% | 1530×731・DPR 1.25 | client 1530×731、inner 1530×731、visualViewport 1530×731（scale 1）、devicePixelRatio 1.25、scroll 1530×731 | 3ペイン | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[edge150-1275x609]` | 実測値 2026-10-28：Edge 拡大150% | 1275×609・DPR 1.5 | client 1275×609、inner 1275×609、visualViewport 1275×609（scale 1）、devicePixelRatio 1.5、scroll 1275×609 | 構造ナビの折りたたみ | 保存・取消：入力の前から |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[windows-fallback-1280x800]` | 基本寸法（計画 第8.0節） | 1280×800・DPR 1（既定） | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | 3ペイン | --font-sans: "Yu Gothic UI", "Meiryo", sans-serif。描画に使われたフォント：一覧の見出し IPAPGothic（7 字）／ボタン IPAPGothic（9 字）／編集画面の要因名 IPAPGothic（5 字） |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[windows-fallback-1093x500]` | 想定寸法：1366×768・125% | 1093×500・DPR 1（既定） | client 1093×500、inner 1093×500、visualViewport 1093×500（scale 1）、devicePixelRatio 1、scroll 1093×500 | 構造ナビの折りたたみ | --font-sans: "Yu Gothic UI", "Meiryo", sans-serif。描画に使われたフォント：一覧の見出し IPAPGothic（7 字）／ボタン IPAPGothic（9 字）／編集画面の要因名 IPAPGothic（5 字） |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[sans-serif-1280x800]` | 基本寸法（計画 第8.0節） | 1280×800・DPR 1（既定） | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | 3ペイン | --font-sans: sans-serif。描画に使われたフォント：一覧の見出し IPAPGothic（7 字）／ボタン IPAPGothic（9 字）／編集画面の要因名 IPAPGothic（5 字） |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[sans-serif-1093x500]` | 想定寸法：1366×768・125% | 1093×500・DPR 1（既定） | client 1093×500、inner 1093×500、visualViewport 1093×500（scale 1）、devicePixelRatio 1、scroll 1093×500 | 構造ナビの折りたたみ | --font-sans: sans-serif。描画に使われたフォント：一覧の見出し IPAPGothic（7 字）／ボタン IPAPGothic（9 字）／編集画面の要因名 IPAPGothic（5 字） |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[serif-1280x800]` | 基本寸法（計画 第8.0節） | 1280×800・DPR 1（既定） | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | 3ペイン | --font-sans: serif。描画に使われたフォント：一覧の見出し IPAPGothic（4 字）、Liberation Serif（3 字）／ボタン IPAPGothic（8 字）、Liberation Serif（1 字）／編集画面の要因名 IPAPGothic（4 字）、Liberation Serif（1 字） |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[serif-1093x500]` | 想定寸法：1366×768・125% | 1093×500・DPR 1（既定） | client 1093×500、inner 1093×500、visualViewport 1093×500（scale 1）、devicePixelRatio 1、scroll 1093×500 | 構造ナビの折りたたみ | --font-sans: serif。描画に使われたフォント：一覧の見出し IPAPGothic（4 字）、Liberation Serif（3 字）／ボタン IPAPGothic（8 字）、Liberation Serif（1 字）／編集画面の要因名 IPAPGothic（4 字）、Liberation Serif（1 字） |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1280x800]` | 基本寸法（計画 第8.0節） | 1280×800・DPR 1（既定） | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1440x900]` | 基本寸法（計画 第8.0節） | 1440×900・DPR 1（既定） | client 1440×900、inner 1440×900、visualViewport 1440×900（scale 1）、devicePixelRatio 1、scroll 1440×900 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1920x1080]` | 想定寸法：1920×1080・倍率100% | 1920×1080・DPR 1（既定） | client 1920×1080、inner 1920×1080、visualViewport 1920×1080（scale 1）、devicePixelRatio 1、scroll 1920×1080 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1536x730]` | 想定寸法：1920×1080・125% | 1536×730・DPR 1（既定） | client 1536×730、inner 1536×730、visualViewport 1536×730（scale 1）、devicePixelRatio 1、scroll 1536×730 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1280x620]` | 想定寸法：1920×1080・150% | 1280×620・DPR 1（既定） | client 1280×620、inner 1280×620、visualViewport 1280×620（scale 1）、devicePixelRatio 1、scroll 1280×620 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1366x650]` | 想定寸法：1366×768・100% | 1366×650・DPR 1（既定） | client 1366×650、inner 1366×650、visualViewport 1366×650（scale 1）、devicePixelRatio 1、scroll 1366×650 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1093x500]` | 想定寸法：1366×768・125% | 1093×500・DPR 1（既定） | client 1093×500、inner 1093×500、visualViewport 1093×500（scale 1）、devicePixelRatio 1、scroll 1093×500 | 構造ナビの折りたたみ | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1024x683]` | 想定寸法 | 1024×683・DPR 1（既定） | client 1024×683、inner 1024×683、visualViewport 1024×683（scale 1）、devicePixelRatio 1、scroll 1024×683 | 構造ナビの折りたたみ | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[900x600]` | 想定寸法（1024px 未満） | 900×600・DPR 1（既定） | client 900×600、inner 900×600、visualViewport 900×600（scale 1）、devicePixelRatio 1、scroll 900×600 | 構造ナビの折りたたみ | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome100-1920x945]` | 実測値 2026-10-28：Chrome 拡大100% | 1920×945・DPR 1 | client 1920×945、inner 1920×945、visualViewport 1920×945（scale 1）、devicePixelRatio 1、scroll 1920×945 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome125-1536x756]` | 実測値 2026-10-28：Chrome 拡大125% | 1536×756・DPR 1.25 | client 1536×756、inner 1536×756、visualViewport 1536×756（scale 1）、devicePixelRatio 1.25、scroll 1536×756 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome150-1280x630]` | 実測値 2026-10-28：Chrome 拡大150% | 1280×630・DPR 1.5 | client 1280×630、inner 1280×630、visualViewport 1280×630（scale 1）、devicePixelRatio 1.5、scroll 1280×630 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[edge125-1530x731]` | 実測値 2026-10-28：Edge 拡大125% | 1530×731・DPR 1.25 | client 1530×731、inner 1530×731、visualViewport 1530×731（scale 1）、devicePixelRatio 1.25、scroll 1530×731 | 3ペイン | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[edge150-1275x609]` | 実測値 2026-10-28：Edge 拡大150% | 1275×609・DPR 1.5 | client 1275×609、inner 1275×609、visualViewport 1275×609（scale 1）、devicePixelRatio 1.5、scroll 1275×609 | 構造ナビの折りたたみ | ③・二次要因Bを選択 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x800]` | 基本寸法（計画 第8.0節） | 1280×800・DPR 1（既定） | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1440x900]` | 基本寸法（計画 第8.0節） | 1440×900・DPR 1（既定） | client 1440×900、inner 1440×900、visualViewport 1440×900（scale 1）、devicePixelRatio 1、scroll 1440×900 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1920x1080]` | 想定寸法：1920×1080・倍率100% | 1920×1080・DPR 1（既定） | client 1920×1080、inner 1920×1080、visualViewport 1920×1080（scale 1）、devicePixelRatio 1、scroll 1920×1080 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1536x730]` | 想定寸法：1920×1080・125% | 1536×730・DPR 1（既定） | client 1536×730、inner 1536×730、visualViewport 1536×730（scale 1）、devicePixelRatio 1、scroll 1536×730 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x620]` | 想定寸法：1920×1080・150% | 1280×620・DPR 1（既定） | client 1280×620、inner 1280×620、visualViewport 1280×620（scale 1）、devicePixelRatio 1、scroll 1280×620 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1366x650]` | 想定寸法：1366×768・100% | 1366×650・DPR 1（既定） | client 1366×650、inner 1366×650、visualViewport 1366×650（scale 1）、devicePixelRatio 1、scroll 1366×650 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1093x500]` | 想定寸法：1366×768・125% | 1093×500・DPR 1（既定） | client 1093×500、inner 1093×500、visualViewport 1093×500（scale 1）、devicePixelRatio 1、scroll 1093×500 | 構造ナビの折りたたみ | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1024x683]` | 想定寸法 | 1024×683・DPR 1（既定） | client 1024×683、inner 1024×683、visualViewport 1024×683（scale 1）、devicePixelRatio 1、scroll 1024×683 | 構造ナビの折りたたみ | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[900x600]` | 想定寸法（1024px 未満） | 900×600・DPR 1（既定） | client 900×600、inner 900×600、visualViewport 900×600（scale 1）、devicePixelRatio 1、scroll 900×600 | 構造ナビの折りたたみ | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome100-1920x945]` | 実測値 2026-10-28：Chrome 拡大100% | 1920×945・DPR 1 | client 1920×945、inner 1920×945、visualViewport 1920×945（scale 1）、devicePixelRatio 1、scroll 1920×945 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome125-1536x756]` | 実測値 2026-10-28：Chrome 拡大125% | 1536×756・DPR 1.25 | client 1536×756、inner 1536×756、visualViewport 1536×756（scale 1）、devicePixelRatio 1.25、scroll 1536×756 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome150-1280x630]` | 実測値 2026-10-28：Chrome 拡大150% | 1280×630・DPR 1.5 | client 1280×630、inner 1280×630、visualViewport 1280×630（scale 1）、devicePixelRatio 1.5、scroll 1280×630 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[edge125-1530x731]` | 実測値 2026-10-28：Edge 拡大125% | 1530×731・DPR 1.25 | client 1530×731、inner 1530×731、visualViewport 1530×731（scale 1）、devicePixelRatio 1.25、scroll 1530×731 | 3ペイン | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[edge150-1275x609]` | 実測値 2026-10-28：Edge 拡大150% | 1275×609・DPR 1.5 | client 1275×609、inner 1275×609、visualViewport 1275×609（scale 1）、devicePixelRatio 1.5、scroll 1275×609 | 構造ナビの折りたたみ | 生成中・生成ログ・通知・保存失敗 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1280x800]` | 基本寸法（計画 第8.0節） | 1280×800・DPR 1（既定） | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1440x900]` | 基本寸法（計画 第8.0節） | 1440×900・DPR 1（既定） | client 1440×900、inner 1440×900、visualViewport 1440×900（scale 1）、devicePixelRatio 1、scroll 1440×900 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1920x1080]` | 想定寸法：1920×1080・倍率100% | 1920×1080・DPR 1（既定） | client 1920×1080、inner 1920×1080、visualViewport 1920×1080（scale 1）、devicePixelRatio 1、scroll 1920×1080 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1536x730]` | 想定寸法：1920×1080・125% | 1536×730・DPR 1（既定） | client 1536×730、inner 1536×730、visualViewport 1536×730（scale 1）、devicePixelRatio 1、scroll 1536×730 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1280x620]` | 想定寸法：1920×1080・150% | 1280×620・DPR 1（既定） | client 1280×620、inner 1280×620、visualViewport 1280×620（scale 1）、devicePixelRatio 1、scroll 1280×620 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1366x650]` | 想定寸法：1366×768・100% | 1366×650・DPR 1（既定） | client 1366×650、inner 1366×650、visualViewport 1366×650（scale 1）、devicePixelRatio 1、scroll 1366×650 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1093x500]` | 想定寸法：1366×768・125% | 1093×500・DPR 1（既定） | client 1093×500、inner 1093×500、visualViewport 1093×500（scale 1）、devicePixelRatio 1、scroll 1093×500 | 構造ナビの折りたたみ | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1024x683]` | 想定寸法 | 1024×683・DPR 1（既定） | client 1024×683、inner 1024×683、visualViewport 1024×683（scale 1）、devicePixelRatio 1、scroll 1024×683 | 構造ナビの折りたたみ | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[900x600]` | 想定寸法（1024px 未満） | 900×600・DPR 1（既定） | client 900×600、inner 900×600、visualViewport 900×600（scale 1）、devicePixelRatio 1、scroll 900×600 | 構造ナビの折りたたみ | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome100-1920x945]` | 実測値 2026-10-28：Chrome 拡大100% | 1920×945・DPR 1 | client 1920×945、inner 1920×945、visualViewport 1920×945（scale 1）、devicePixelRatio 1、scroll 1920×945 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome125-1536x756]` | 実測値 2026-10-28：Chrome 拡大125% | 1536×756・DPR 1.25 | client 1536×756、inner 1536×756、visualViewport 1536×756（scale 1）、devicePixelRatio 1.25、scroll 1536×756 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome150-1280x630]` | 実測値 2026-10-28：Chrome 拡大150% | 1280×630・DPR 1.5 | client 1280×630、inner 1280×630、visualViewport 1280×630（scale 1）、devicePixelRatio 1.5、scroll 1280×630 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[edge125-1530x731]` | 実測値 2026-10-28：Edge 拡大125% | 1530×731・DPR 1.25 | client 1530×731、inner 1530×731、visualViewport 1530×731（scale 1）、devicePixelRatio 1.25、scroll 1530×731 | 3ペイン | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[edge150-1275x609]` | 実測値 2026-10-28：Edge 拡大150% | 1275×609・DPR 1.5 | client 1275×609、inner 1275×609、visualViewport 1275×609（scale 1）、devicePixelRatio 1.5、scroll 1275×609 | 構造ナビの折りたたみ | ダイアログ |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1280x800]` | 基本寸法（計画 第8.0節） | 1280×800・DPR 1（既定） | client 1280×800、inner 1280×800、visualViewport 1280×800（scale 1）、devicePixelRatio 1、scroll 1280×800 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1440x900]` | 基本寸法（計画 第8.0節） | 1440×900・DPR 1（既定） | client 1440×900、inner 1440×900、visualViewport 1440×900（scale 1）、devicePixelRatio 1、scroll 1440×900 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1920x1080]` | 想定寸法：1920×1080・倍率100% | 1920×1080・DPR 1（既定） | client 1920×1080、inner 1920×1080、visualViewport 1920×1080（scale 1）、devicePixelRatio 1、scroll 1920×1080 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1536x730]` | 想定寸法：1920×1080・125% | 1536×730・DPR 1（既定） | client 1536×730、inner 1536×730、visualViewport 1536×730（scale 1）、devicePixelRatio 1、scroll 1536×730 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1280x620]` | 想定寸法：1920×1080・150% | 1280×620・DPR 1（既定） | client 1280×620、inner 1280×620、visualViewport 1280×620（scale 1）、devicePixelRatio 1、scroll 1280×620 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1366x650]` | 想定寸法：1366×768・100% | 1366×650・DPR 1（既定） | client 1366×650、inner 1366×650、visualViewport 1366×650（scale 1）、devicePixelRatio 1、scroll 1366×650 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1093x500]` | 想定寸法：1366×768・125% | 1093×500・DPR 1（既定） | client 1093×500、inner 1093×500、visualViewport 1093×500（scale 1）、devicePixelRatio 1、scroll 1093×500 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1024x683]` | 想定寸法 | 1024×683・DPR 1（既定） | client 1024×683、inner 1024×683、visualViewport 1024×683（scale 1）、devicePixelRatio 1、scroll 1024×683 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[900x600]` | 想定寸法（1024px 未満） | 900×600・DPR 1（既定） | client 900×600、inner 900×600、visualViewport 900×600（scale 1）、devicePixelRatio 1、scroll 906×600 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome100-1920x945]` | 実測値 2026-10-28：Chrome 拡大100% | 1920×945・DPR 1 | client 1920×945、inner 1920×945、visualViewport 1920×945（scale 1）、devicePixelRatio 1、scroll 1920×945 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome125-1536x756]` | 実測値 2026-10-28：Chrome 拡大125% | 1536×756・DPR 1.25 | client 1536×756、inner 1536×756、visualViewport 1536×756（scale 1）、devicePixelRatio 1.25、scroll 1536×756 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome150-1280x630]` | 実測値 2026-10-28：Chrome 拡大150% | 1280×630・DPR 1.5 | client 1280×630、inner 1280×630、visualViewport 1280×630（scale 1）、devicePixelRatio 1.5、scroll 1280×630 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[edge125-1530x731]` | 実測値 2026-10-28：Edge 拡大125% | 1530×731・DPR 1.25 | client 1530×731、inner 1530×731、visualViewport 1530×731（scale 1）、devicePixelRatio 1.25、scroll 1530×731 | （編集画面以外） | 一覧 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[edge150-1275x609]` | 実測値 2026-10-28：Edge 拡大150% | 1275×609・DPR 1.5 | client 1275×609、inner 1275×609、visualViewport 1275×609（scale 1）、devicePixelRatio 1.5、scroll 1275×609 | （編集画面以外） | 一覧 |

#### 目視のレビュー用の画面（自動判定の補完。受入の判定には含めない）

保存した画面はありません（--e2e-screens を指定していない、または撮るテストを実行していない）。

### 主要な操作への到達（第8.7節の条件2・4。tests/e2e/layout_checks.py の reach()）

「表示のまま」は、スクロールせずに表示領域の中にあり、覆うもの（通知を含む）がなかった操作です。インスペクタの保存・取消とダイアログのボタンは、追加のスクロールなしで届くことが要件で（「スクロールなしが要件」）、表示のままでなければ失敗にします。ほかの操作は、それがあるペイン（長い一覧など）をスクロールして届けば合格です。**通知に覆われていた操作は、スクロールの有無にかかわらず失敗にします**（PR-7 の 2026-10-29 の修正で、通知の上へスクロールして判定する処理は廃止）。「届かない（失敗）」は検査が失敗にした操作で（検出力の確認のテストでは、失敗にすることを確かめた操作）、失敗したテストの行は、失敗した時点までの数です。

| テスト | 確かめた数 | 表示のまま（うちスクロールなしが要件） | ペインのスクロールで到達 | 届かない（失敗） |
|---|---|---|---|---|
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1280x800]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1440x900]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1920x1080]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1536x730]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1280x620]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1366x650]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1093x500]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[1024x683]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[900x600]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome100-1920x945]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome125-1536x756]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[chrome150-1280x630]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[edge125-1530x731]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_V01_save_and_cancel_in_view_from_the_moment_the_editor_is_shown[edge150-1275x609]` | 15 | 15（15） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1280x800]` | 1 | 1（0） | 0 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1093x500]` | 1 | 0（0） | 1 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[900x600]` | 1 | 0（0） | 1 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1024x683]` | 1 | 0（0） | 1 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[edge150-1275x609]` | 1 | 0（0） | 1 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[chrome150-1280x630]` | 1 | 0（0） | 1 | 0 |
| `tests/e2e/test_pr7_focus.py::test_E_K01_the_list_keeps_the_focus_in_view_with_notifications[1280x620]` | 1 | 0（0） | 1 | 0 |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[windows-fallback-1280x800]` | 22 | 21（2） | 1 | 0 |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[windows-fallback-1093x500]` | 22 | 18（2） | 4 | 0 |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[sans-serif-1280x800]` | 22 | 21（2） | 1 | 0 |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[sans-serif-1093x500]` | 22 | 18（2） | 4 | 0 |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[serif-1280x800]` | 22 | 21（2） | 1 | 0 |
| `tests/e2e/test_pr7_fonts.py::test_E_F01_without_biz_udpgothic_nothing_is_cut_off_or_overlaps[serif-1093x500]` | 22 | 18（2） | 4 | 0 |
| `tests/e2e/test_pr7_screens.py::test_E_V01_representative_screens_of_a_generation[1280x800]` | 7 | 6（1） | 1 | 0 |
| `tests/e2e/test_pr7_screens.py::test_E_V01_representative_screens_of_a_generation[1093x500]` | 7 | 5（1） | 2 | 0 |
| `tests/e2e/test_pr7_screens.py::test_E_V01_representative_screens_of_a_generation[edge150-1275x609]` | 7 | 6（1） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1280x800]` | 24 | 23（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1440x900]` | 24 | 23（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1920x1080]` | 24 | 23（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1536x730]` | 24 | 23（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1280x620]` | 24 | 22（4） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1366x650]` | 24 | 23（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1093x500]` | 31 | 27（5） | 4 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[1024x683]` | 31 | 29（5） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[900x600]` | 31 | 28（5） | 3 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome100-1920x945]` | 24 | 23（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome125-1536x756]` | 24 | 23（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[chrome150-1280x630]` | 24 | 22（4） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[edge125-1530x731]` | 24 | 23（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_edit_layout_and_main_controls[edge150-1275x609]` | 31 | 30（5） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x800]` | 12 | 11（5） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1440x900]` | 12 | 12（5） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1920x1080]` | 12 | 12（5） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1536x730]` | 12 | 11（5） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1280x620]` | 12 | 10（5） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1366x650]` | 12 | 10（5） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1093x500]` | 12 | 10（5） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[1024x683]` | 12 | 10（5） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[900x600]` | 12 | 9（5） | 3 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome100-1920x945]` | 12 | 12（5） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome125-1536x756]` | 12 | 12（5） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[chrome150-1280x630]` | 12 | 10（5） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[edge125-1530x731]` | 12 | 11（5） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_generation_status_log_notifications_and_a_failed_save[edge150-1275x609]` | 12 | 10（5） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1280x800]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1440x900]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1920x1080]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1536x730]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1280x620]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1366x650]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1093x500]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[1024x683]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[900x600]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome100-1920x945]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome125-1536x756]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[chrome150-1280x630]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[edge125-1530x731]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_dialogs_fit_and_their_buttons_are_reached[edge150-1275x609]` | 11 | 11（10） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1280x800]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1440x900]` | 13 | 13（4） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1920x1080]` | 13 | 13（4） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1536x730]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1280x620]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1366x650]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1093x500]` | 13 | 11（4） | 2 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[1024x683]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[900x600]` | 13 | 10（4） | 3 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome100-1920x945]` | 13 | 13（4） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome125-1536x756]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[chrome150-1280x630]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[edge125-1530x731]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens[edge150-1275x609]` | 13 | 12（4） | 1 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[page-min-width-1100-1093x500]` | 2 | 2（2） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[three-panes-below-1280-edge150-1275x609]` | 2 | 2（2） | 0 | 0 |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[notifications-over-the-inspector-1093x500]` | 5 | 4（4） | 0 | 1 |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[bar-in-the-scroll-area-1093x500]` | 3 | 2（2） | 0 | 1 |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[covered-control-900x600]` | 3 | 2（2） | 0 | 1 |
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[inspector-out-of-view-900x600]` | 3 | 2（2） | 0 | 1 |
| `tests/e2e/test_pr7_viewports.py::test_reach_tells_as_shown_a_pane_scroll_and_a_notification_over_it_apart[1093x500]` | 5 | 2（1） | 1 | 2 |

#### ペインのスクロールで届いた操作（スクロールしないと表示領域の外にあった）

| 操作 | 表示領域 |
|---|---|
| 一覧の改名（通知の表示中） | 1093×500、900×600、1024×683、1275×609、1280×630、1280×620 |
| インスペクタの削除（windows-fallback） | 1280×800、1093×500 |
| 作業リストの評価Yes（windows-fallback） | 1093×500 |
| インスペクタの評価No（windows-fallback） | 1093×500 |
| 操作バーの生成（windows-fallback） | 1093×500 |
| インスペクタの削除（sans-serif） | 1280×800、1093×500 |
| 作業リストの評価Yes（sans-serif） | 1093×500 |
| インスペクタの評価No（sans-serif） | 1093×500 |
| 操作バーの生成（sans-serif） | 1093×500 |
| インスペクタの削除（serif） | 1280×800、1093×500 |
| 作業リストの評価Yes（serif） | 1093×500 |
| インスペクタの評価No（serif） | 1093×500 |
| 操作バーの生成（serif） | 1093×500 |
| 生成ログを閉じる | 1280×800、1093×500、1275×609、900×600 |
| 操作バーの生成 | 1093×500、900×600 |
| インスペクタの削除 | 1280×800、1440×900、1920×1080、1536×730、1280×620、1366×650、1093×500、1024×683、900×600、1920×945、1536×756、1280×630、1530×731、1275×609 |
| 作業リストの評価Yes | 1280×620、1093×500、1024×683、900×600、1280×630 |
| インスペクタの評価No | 1093×500 |
| 生成ログの見出し | 1280×800、1536×730、1280×620、1366×650、1093×500、1024×683、900×600、1280×630、1530×731、1275×609 |
| 操作バーの生成（生成後） | 1280×620、1366×650、1093×500、1024×683、900×600、1280×630、1275×609 |
| 新規作成：作成 | 1280×800、1536×730、1280×620、1366×650、1093×500、1024×683、900×600、1536×756、1280×630、1530×731、1275×609 |
| 一覧：分析を開く | 1093×500、900×600 |
| 一覧：削除 | 900×600 |
| 生成 | 1093×500 |

#### 通知に覆われていた操作（失敗にしたもの）

| テスト | 操作 | 表示領域 | 位置（x, y, 幅×高さ） | 重なった点 | 重なった通知（種類・文・位置） |
|---|---|---|---|---|---|
| `tests/e2e/test_pr7_viewports.py::test_the_pr7_layout_checks_catch_what_they_must[notifications-over-the-inspector-1093x500]` | 保存（不具合） | 1093×500 | 1031, 462, 46×30 | (1054, 477)、(1038, 468)、(1070, 468)、(1038, 486)、(1070, 486) | error「検出力の確認：閉じるまで残るエラー。保存・取消の上に重なると失敗にならなければな」769,388 308×104 |
| `tests/e2e/test_pr7_viewports.py::test_reach_tells_as_shown_a_pane_scroll_and_a_notification_over_it_apart[1093x500]` | 生成（通知の下。スクロールなし） | 1093×500 | 41, 329.4, 228.5×36 | (155, 347)、(75, 337)、(235, 337)、(75, 358)、(235, 358) | error「到達の区別の確認」16,330 528×54 |
| `tests/e2e/test_pr7_viewports.py::test_reach_tells_as_shown_a_pane_scroll_and_a_notification_over_it_apart[1093x500]` | 生成（通知の下。ペインのスクロールあり） | 1093×500 | 41, 329.4, 228.5×36 | (155, 347)、(75, 337)、(235, 337)、(75, 358)、(235, 358) | error「到達の区別の確認」16,330 528×54 |

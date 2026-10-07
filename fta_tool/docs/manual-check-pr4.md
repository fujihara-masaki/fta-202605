# PR-4 Windows 実機確認の手順（Chrome・Edge）

計画書（[ui-redesign-implementation-plan.md](ui-redesign-implementation-plan.md)）第8.4節の確認を、Windows のインストール済みの **Google Chrome Stable と Microsoft Edge Stable の両方**で行うための手順です。対象は PR-4 の作業ブランチ `claude/ecstatic-volta-upe9jc` の受入候補の SHA（報告に書いた SHA）です。

この手順書は確認の進め方をまとめたもので、受入の合否を決めるものではありません。合否、PR の作成とマージは、利用者が判断します。

**確認の方式（2026-10-06 の利用者の方針）**：2026-10-06 の利用者の方針により、PR-4 以降は Windows の Chrome・Edge とも、可能な範囲を自動 E2E で確認し、自動化で確認できない変更箇所だけを実操作・目視で確認する。

- 自動 E2E：既存の `scripts/run_browser_e2e.ps1` を、Chrome は `-Channel chrome`、Edge は `-Channel msedge` で使います。同じテストをブラウザの指定だけ変えて実行します（Chrome 用・Edge 用に試験やスクリプトを分けていません）。
- 実操作・目視：PR-4 で変えた箇所のうち、自動化で確かめられない3点（第5節）だけです。PR-3 の手動確認（[manual-check-pr3.md](manual-check-pr3.md) の第4〜7節）を両ブラウザで繰り返すことはしません。表示倍率・ブラウザの拡大の体系的な確認は PR-7 です。
- PR-3 の Edge の手動確認（`4b49914`）と Chrome の自動確認（`410972d`）は、その時点の PR-3 の結果です。PR-4 の確認結果として流用しません。

| ブラウザ | 方式 | 対象の SHA | 状態 |
|---|---|---|---|
| Google Chrome（Stable） | 準備確認 → 全必須 E2E（第3節）＋実操作・目視（第5節） | 受入候補の SHA | **未実施** |
| Microsoft Edge（Stable） | 準備確認 → 全必須 E2E（第4節）＋実操作・目視（第5節） | 受入候補の SHA | **未実施** |

## 0. 守ること

- 普段の DB、過去の確認用 DB（PR-3 の Edge・Chrome の回を含む）、通常のブラウザのプロフィールは使いません。自動 E2E は記録フォルダの中の一時 DB・スタブ（AI: e2e-stub）・一時プロフィールで動きます。実操作・目視は、その回だけの新しい DB と AI: mock で行います（第5.1節）。
- Chrome と Edge は、**できるだけ同じ SHA** で確認します。順番に実行し（同時に実行しない）、ブラウザごとに新しい記録フォルダを作ります。
- 準備確認の成功や診断（`-Mode Diagnose`）の実施は、全必須 E2E の合格ではありません。一部のテストだけを実行した結果も、全必須 E2E の結果とは別に扱います。
- ブラウザが起動できない場合、同梱の Chromium に切り替えて合格扱いにすることはしません（スクリプトもしません）。その環境の未確認事項として、記録を渡してください。
- 試験を通す目的で、ブラウザの設定・企業のポリシー・プロキシ・Windows の表示倍率を変えないでください。テストの時間の上限やスキップ・除外の条件も変えません（favicon の 404 の既知の例外と PR3-LAYOUT の chrome-1905x945 の限定した許容は、PR-3 の条件のまま。Edge の 1912×914 は一致が必要）。
- 記録にはローカルのパス（ユーザー名を含む）が入ります。外部へ上げる前に確認してください。

## 1. コードを取り出す

[manual-check-pr3.md](manual-check-pr3.md) 第1節と同じ方法で、確認する SHA を SHA ごとの別フォルダ（git worktree）に取り出します。PR-4 の PR はまだ作っていないため、ブランチの先頭を確かめます。

```powershell
cd C:\work\fta-202605                                   # 普段のリポジトリ（例）
git fetch origin claude/ecstatic-volta-upe9jc
git ls-remote origin refs/heads/claude/ecstatic-volta-upe9jc   # ブランチの先頭の SHA
$sha = "<確認する SHA（40桁）>"
$wt  = "C:\fta-check\src-$($sha.Substring(0,7))"
git worktree add --detach $wt $sha
git -C $wt rev-parse HEAD                               # $sha と一致すること
git -C $wt status --short                               # 何も出ないこと
Test-Path "$wt\fta_tool\.env"                           # False であること
```

## 2. PowerShell の設定と自動確認専用の venv

新しい PowerShell を開くたびに、次を設定します（[manual-check-pr3.md](manual-check-pr3.md) 第12.2節と同じ変数）。

```powershell
$sha  = "<確認する SHA（40桁）>"
$src  = "C:\fta-check\src-$($sha.Substring(0,7))\fta_tool"
$venv = "C:\fta-check\e2e-venv"            # PR-3 で作った自動確認専用の venv（コードのフォルダの外）
$out  = "C:\fta-check\e2e"                 # 自動確認の記録フォルダを作る場所（コードのフォルダの外）
$ps1  = "$src\scripts\run_browser_e2e.ps1" # 確認する SHA と同じ版のスクリプト
```

- **venv の再利用**：PR-4 は `requirements.txt`・`requirements-dev.txt` を変えていません（Playwright 1.56.0、pytest-playwright 0.7.1 のまま）。PR-3 で作った venv があれば、そのまま使います。版だけ確かめます。

  ```powershell
  & "$venv\Scripts\python.exe" -m pip show playwright pytest-playwright | Select-String "^(Name|Version)"
  ```

  playwright 1.56.0・pytest-playwright 0.7.1 と出れば再利用できます。venv がない、または版が違う場合だけ、[manual-check-pr3.md](manual-check-pr3.md) 第12.3節の初回準備（`-Mode Setup`）を新しいフォルダで行います。既存の venv を上書きしないでください。
- 実行ポリシーで止められた場合は、ポリシーを変更せずに報告してください（手入力の同じ手順は manual-check-pr3.md 第12.7節。`--browser-channel` を `msedge` に替えれば Edge でも同じ）。

## 3. Google Chrome での自動確認

### 3.1 準備確認

```powershell
& $ps1 -Mode Preflight -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha
```

- 記録フォルダ `<SHA7桁>-<日時>-chrome-preflight` ができます。判定「成功」、終了コード 0、「起動したブラウザ」が `Google LLC …` であること。
- 実行するのは PR-3 と同じ7件（E-E01 の2件と PR3-LAYOUT の3寸法）です。**全必須 E2E の合格ではありません。**
- 失敗したら全件へ進まず、記録フォルダを渡してください。最初の画面遷移で止まる場合は manual-check-pr3.md 第12.10節の診断（`-Mode Diagnose -Channel chrome`）で止まる場所を記録します（診断は合否ではありません）。

### 3.2 全必須 E2E（準備確認が成功してから）

```powershell
& $ps1 -Mode Full -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha
```

- 記録フォルダ `<SHA7桁>-<日時>-chrome-full` ができます。合格の条件：判定「合格」（`REQUIRED_IDS` のすべての受入項目が成功し、失敗・スキップ・未実施が0件）、終了コード 0。件数そのものは条件にしません（PR-3 の 181 件は PR-4 の期待件数ではありません）。
- `REQUIRED_IDS` は累積です。PR-4 で E-E10〜E-E13・E-E20・PR4-LAYOUT が加わり、PR-1〜PR-3 の項目もすべて実行されます。
- 開発環境（Linux）での所要時間の目安は報告に書きます。Windows で画面を表示する実行は、それより長くかかる見込みです。実行中はテストのウィンドウを操作しないでください。

## 4. Microsoft Edge での自動確認（Chrome の後に）

Chrome の全必須 E2E が終わってから、同じ SHA・同じ venv で、`-Channel msedge` に替えて実行します。

```powershell
& $ps1 -Mode Preflight -Channel msedge -Venv $venv -OutRoot $out -ExpectedSha $sha
# 準備確認が成功したら
& $ps1 -Mode Full -Channel msedge -Venv $venv -OutRoot $out -ExpectedSha $sha
```

- 記録フォルダは `…-msedge-preflight`・`…-msedge-full` です。「起動したブラウザ」が `Microsoft Corporation …`（Edge の版）で、`run-info.md` の実行ファイルが `msedge.exe` であること。指定した channel（msedge）と、実際に起動したブラウザの両方で Edge の確認であることを示します。
- 合格・成功の条件は Chrome と同じです。PR3-LAYOUT の edge-1912x914 は、要求と実測（`clientWidth`×`clientHeight`）の一致が必要です（許容は chrome-1905x945 だけ）。
- Edge が見つからない・起動できない場合は、失敗として止まります（同梱の Chromium には切り替えません）。そのまま記録を渡してください。

### 4.1 渡すもの（Chrome・Edge 共通）

ブラウザごと・実行ごとに、記録フォルダの `e2e-report.md` と `run-info.md`（失敗・中止のときは記録フォルダ全体）。記録には、対象 SHA と未コミットの変更の有無、OS、指定した channel、実際に起動したブラウザの作成元・版・実行ファイル、画面寸法のケースと PR3-LAYOUT の要求・実測、成功・失敗・スキップ・未実施の件数が入ります。画面寸法のケース名（例：edge-1912x914）は、起動したブラウザとは別に記録されます（ケース名は寸法の名前で、Chrome で実行しても同じ名前です）。

## 5. 実操作・目視（両ブラウザ、PR-4 の変更箇所だけ）

自動 E2E の後に、次の3点だけを、Chrome と Edge のそれぞれで行います（所要は各10分程度の見込み）。

### 5.1 準備（ブラウザごとに新しい DB）

```powershell
$py  = "C:\work\fta-202605\fta_tool\.venv\Scripts\python.exe"   # 普段アプリを起動している python.exe（例）
$run = "C:\fta-check\runs\{0}-{1}-pr4-chrome" -f $sha.Substring(0,7), (Get-Date -Format "yyyyMMdd-HHmm")   # Edge の回は末尾を pr4-edge に
Test-Path $run                                   # False であること
New-Item -ItemType Directory -Path "$run\db", "$run\logs", "$run\screenshots" | Out-Null
$env:AI_PROVIDER = "mock"
Test-Path "$src\.env"                            # False であること
$server = Start-Process -FilePath $py -PassThru -NoNewWindow `
  -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", ('"{0}"' -f $src), "--host", "127.0.0.1", "--port", "8001") `
  -WorkingDirectory "$run\db" `
  -RedirectStandardOutput "$run\logs\stdout.log" -RedirectStandardError "$run\logs\stderr.log"
Start-Sleep -Seconds 5
Select-String -Path "$run\logs\stderr.log" -Pattern "dotenv file not found", "AI_PROVIDER", "Uvicorn running"
```

- 起動ログに `dotenv file not found`、`AI_PROVIDER                = mock`、`Uvicorn running on http://127.0.0.1:8001` が出ること（manual-check-pr3.md 第3節と同じ）。新しい DB なので一覧は空です。
- 確認するブラウザ（Chrome または Edge）を最大化し、`http://127.0.0.1:8001/analyses/new` で分析を1つ作る（タイトル「PR4確認」、頂上事象「決済処理が停止した」）。編集画面のヘッダーに「AI: mock」と出ること。
- Edge の回では、Chrome の回の DB を使いません（上の `$run` を新しく作る）。

### 5.2 実操作1：Microsoft IME での分析タイトルの入力

自動 E2E（E-E11）は、変換中の Enter・Esc を合成したキーイベント（`isComposing`・`keyCode 229`）で確かめています。実際の Microsoft IME の変換確定の Enter は、ここで確かめます。

1. ヘッダーの ✎ を押し、タイトルの末尾に、IME で「かくにん」と入力して変換し、「確認」で **Enter で確定する**。
2. 確定の Enter で、編集欄が閉じないこと・「タイトルを保存しました」が出ないこと（まだ保存されない）。
3. もう一度 Enter を押すと保存され、編集欄が閉じてヘッダーのタイトルが変わること（「タイトルを保存しました」）。
4. もう一度 ✎ を押し、IME で変換中に Esc を押して変換を取り消す。編集欄が閉じないこと（変換の取り消しだけ）。編集欄の外をクリックして閉じる（変更がなければ何も保存しない）。

### 5.3 実操作2：未保存の入力がある状態での F5（ブラウザの標準の確認）

自動 E2E（E-E12）は、再読み込みでブラウザの確認が出ること、取り消すと入力が残ること、受け入れると移動することを、テスト用ブラウザで確かめています。実際のブラウザの確認の表示は、ここで確かめます。

1. 「① 頂上事象・参考情報」で、頂上事象の末尾に「（F5の確認）」と入力する（保存しない）。「入力中（未保存）」と出ること。
2. F5 を押す。ブラウザの標準の確認（「このサイトを再読み込みしますか？」など。文言はブラウザが決める）が出ること。画面内の3択のダイアログではないこと。
3. 「キャンセル」（このページに留まる）を選ぶ。入力した「（F5の確認）」が残り、「入力中（未保存）」のままであること。
4. もう一度 F5 を押し、今度は「再読み込み」を選ぶ。入力が消え、保存済みの頂上事象に戻ること（下書きはブラウザに保存しない仕様）。
5. ヘッダーの ✎ でタイトルを変更して（Enter を押さずに）F5 を押し、同じ確認が出ること。「キャンセル」を選ぶと編集欄と入力が残ること。

### 5.4 目視：文字と主要なボタンが読みやすく、隠れていないこと

自動 E2E（PR4-LAYOUT）は、1280×800 と利用者環境の実測値（1905×945・1912×914）で、下の要素が表示領域の中にあり、ほかの要素に覆われず、文字が 12px 以上であることを確かめています。実際の画面での読みやすさは、ここで確かめます（最大化したウィンドウ、表示倍率・拡大は普段のまま。100% 以外の場合はその値を記録する）。

1. ヘッダー：✎ を押した編集欄（入力欄・「保存」・「取消」・文字数の説明）。空にして Enter を押したときのエラー。「出力▾」と「一覧へ」。
2. ①：各入力欄の「保存済み／入力中（未保存）」の表示、「頂上事象を保存」「参考情報を保存」、上部の「生成の前の自動保存」の説明。
3. ⑤：要因の件数の表、出力形式ごとの項目の表、3つの出力ボタン。
4. ①に未保存の入力を残して「一覧へ」を押し、未保存の確認のダイアログ（「編集を続ける」「破棄して移動」「保存して移動」）。「編集を続ける」で閉じる。

それぞれ、文字が読め、ボタンが欠けたり重なったり、通知の下に隠れたりしていないことを確かめ、1〜4 の画面のコピーを保存します。読みにくい・隠れている場合は、その画面のコピーと見え方を記録してください。

### 5.5 後片付けと記録

```powershell
Stop-Process -Id $server.Id
Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue   # 何も出ないこと
```

記録フォルダの `results.md` に、ブラウザごとに次を書きます。

- 対象 SHA、ブラウザの版（`chrome://version`・`edge://version`）、Windows の版と表示倍率・ブラウザの拡大。
- 自動確認の記録フォルダの名前と判定（準備確認・全必須 E2E を分けて）。
- 実操作1〜2・目視の結果（OK／NG）と画面のコピーのファイル名。NG の場合は手順と見え方。

worktree と記録フォルダは、受入の判断が終わるまで残してかまいません。片付けは manual-check-pr3.md 第9節と同じ手順です（削除を拒否されたら止めて原因を確かめる）。

## 6. 第8.4節の確認項目と自動テストの対応

区分：**自動**＝自動 E2E・pytest で確認する／**一部自動**＝自動で確認し、残りを実操作・目視で確認する／**実操作**＝実操作・目視が必要。

| 確認項目 | 区分 | 自動テスト（受入 ID・テスト） | 自動で確認すること | 実操作・目視で残すこと（理由） |
|---|---|---|---|---|
| 8.4 手動1：頂上事象を入力して保存状態を確かめ、元に戻して「保存済み」に戻る | 自動 | E-E10（`test_E_E10_stored_crlf_and_spaces_are_saved_and_restoring_is_saved_again` ほか） | 入力で「入力中（未保存）」、元に戻すと「保存済み」、前後の空白・CRLF/LF だけでは未保存にならない（DB に直接入れた CRLF の値で初期表示が保存済み）、ステップの「未保存あり」 | なし（表示の読みやすさは 5.4） |
| 8.4 手動2：参考情報を編集したまま「一覧へ」→3択、サーバーを止めて保存して移動 → 移動しない・結果の表示 → 再開して再試行 | 自動 | E-E12（`…partial_failure_retry_sends_the_failed_one_only`・`…discard_after_a_partial_success`・`…continue_and_escape…`）、E-E20 | サーバーの停止の代わりに、テスト用ブラウザで要求に 500・404 を返す・通信を切る（`page.route`）。項目ごとの「保存済み／失敗：理由／未送信：理由」、移動しないこと、失敗分だけの再試行と移動、部分成功後の破棄の説明、送信要求の宛先・回数・順番、DB の内容 | なし。利用者がサーバーを止め・再開する操作は不要にした |
| 8.4 手動3：タイトルの編集中に「分析一覧」→ 確認なしで保存して移動、空にすると止まる | 自動（IME は一部自動） | E-E11（`…leaving_waits_for_the_save_the_blur_started`・`…empty_or_too_long…`・`…a_failed_save_stays…`・`…title_and_step_1_both_changed`・`…ime_enter_and_escape_do_nothing`・`…focus_on_save_or_cancel…`） | 確認なしで移動、保存の応答を遅らせて移動を待つ、空・256文字・保存失敗で移動しない（入力と理由が残る、送信0件または1件）、blur とクリックで二重送信しない、保存・取消へのフォーカスで保存しない、変換中の Enter・Esc（合成イベント）で何もしない | 実際の Microsoft IME の変換確定の Enter（5.2。合成イベントは IME の実装そのものではないため） |
| 8.4 手動4：⑤の件数を目で数えた値と比べ、3形式を出力して⑤の表と中身を突き合わせる | 自動 | E-E13、T-06（`tests/test_ui_templates.py`） | 件数を共通データから（評価の変更・部分更新の後も）、不整合の要因は別の行、直接要因と Yes の区別。3形式のダウンロードの中身がエクスポートの URL と一致、⑤の表の各セルを実際の出力で照合（T-06） | なし（表の読みやすさは 5.4） |
| 保存失敗時に入力が残り、移動しない | 自動 | E-E10、E-E11、E-E12 | — | なし |
| 編集開始時の分析・要因へ保存 | 自動 | E-E20（`…order_and_the_target_fixed_when_editing_started`） | 選択を変え、呼び出し側の対象を書き換えても、登録時の要因へ送る。要因の保存元はテスト用に登録（インスペクタの編集 UI は PR-5） | なし（実インスペクタへの接続と R-01 の全経路は PR-5） |
| 新しいタイトル入力中の部分更新の失敗で入力が残る | 自動 | E-E11（`…failed_partial_update_keeps_the_title_input_and_gone_stops_it`） | 再読み込みしない、入力が残る、分析が削除されたら編集・保存を止める | なし |
| ブラウザ離脱確認（F5・タブを閉じる） | 一部自動 | E-E12（`…browser_navigation_gets_the_browsers_confirmation_only`・`…title_being_saved_asks_the_browser_too`） | 未保存のときだけ beforeunload の確認が出る、取り消すと入力が残る、受け入れると移動する、画面内の3択は出ない | 実際のブラウザの確認の表示と F5 の操作（5.3。テスト用ブラウザはダイアログを自動で応答するため） |
| 新しいタイトル編集・①・⑤・未保存確認のダイアログが読みやすく隠れていない | 一部自動 | PR4-LAYOUT（`tests/e2e/test_edit_pr4_layout.py`） | 1280×800・1905×945・1912×914 で表示領域の中、ほかの要素（通知を含む）に覆われない、文字 12px 以上、ページの横スクロールなし | 実際の画面での読みやすさ（5.4。フォント・画面の見え方は自動では判断できないため） |

## 7. 結果の受け渡し

- 自動確認：Chrome・Edge それぞれの準備確認と全必須 E2E の `e2e-report.md`・`run-info.md`。
- 実操作・目視：ブラウザごとの `results.md` と画面のコピー。
- 未実施の確認は「未実施」と書いてください（実施していない確認を合格とは扱いません）。

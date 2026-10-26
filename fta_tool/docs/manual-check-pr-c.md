# PR-C Windows 実機確認の手順（静的ファイルのキャッシュ制御。Chrome・Edge）

計画書 [static-assets-cache-control-plan.md](static-assets-cache-control-plan.md)（以下「計画書」）の Windows の確認を行うための手順です。対象は PR-C（PR #24）の作業ブランチ `claude/pr-c-static-cache` です。

この手順書は確認の進め方をまとめたもので、受入の合否を決めるものではありません。合否とマージは利用者が判断します。**開発環境での自動試験の成功は、Windows 実機での確認や PR-C の受入の判断の代わりではありません。**

## 0. この確認の方式（2026-10-26 の利用者の方針）

試験はできるだけ自動化し、利用者の手動の操作は、実際のキー操作でしか確かめられないものに絞ります。

| 区分 | 内容 | 利用者が行うこと |
|---|---|---|
| Windows の自動確認（第3節・第4節） | `run_browser_e2e.ps1` の Preflight と Full。Full は累積の全必須 E2E（PR-6 までの 60 項目と PR-C の C-00〜C-07。CSS・下位のモジュールの更新、リンク・goto・F5 の各操作、HTML の取得、移行、境界条件、対策を外した構成での検出力、生成中の評価のボタン）を、Chrome・Edge の一時プロフィールで実行し、合否の判定と記録まで行う | コマンドを実行し、終わるまで待つ。記録フォルダを渡す |
| 実際のキー操作による移行の確認（第5節。W-02） | 普段のプロフィールで、3画面の実際の Ctrl+F5 と、版の変更の後の編集画面の実際の F5。準備・版の変更・サーバーの停止と同じポートでの起動・集計・判定・記録・後片付けは `run_cache_check.ps1` が行う | 案内に従って、画面のリンクのクリック、Ctrl+F5 を3回、F5 を1回 |
| 元の W-01（DevTools でのヘッダー等の確認） | 自動確認とサーバーの記録の判定に統合した（第6節の対応表）。DevTools での再確認・転記・撮影は求めない | なし |
| W-03（次の実際の更新での観察） | PR-7 の取り込みなど、次の実際の更新の自動確認・通常の利用と共用する。この PR の受入には含めない | なし（その時点で通常に使う） |

## 1. 守ること

- 普段のコード・利用者の DB は使いません。自動確認は記録フォルダの中の一時 DB・スタブ（AI: e2e-stub）・一時プロフィールで動きます。W-02 は記録フォルダの中に静的ファイルの一時コピーと試験 DB を作り、終わると削除します（記録は残す）。
- **ブラウザのキャッシュ・サイトデータは消しません。** W-02 の間、DevTools の「キャッシュを無効にする」は使いません（使うと判定が NG になります）。
- Chrome と Edge は同じ SHA で、順番に実行します（同時に実行しない）。実行ごとに新しい記録フォルダができます。
- 試験を通す目的で、ブラウザの設定・企業のポリシー・プロキシ・Windows の表示倍率・試験の条件を変えないでください。ブラウザが起動できないときは、同梱の Chromium に切り替えず、記録フォルダを渡してください。
- 普段の FTA ツールのサーバーを 8001 で動かしている場合は、W-02 の前に止めてください（W-02 は 8001 を使います。`-Port` で変えられますが、変えた場合は記録に残ります）。
- 記録にはローカルのパス（ユーザー名を含む）が入ります。外部へ上げる前に確認してください。

## 2. コードを取り出す

受入候補のアプリ・試験・スクリプトは `2405992cdb5273571c3c23e7ffc96410433dff19` です（2026-10-26 のレビューの修正と、記録の改善を含む。以前の `56e6507`・`03f91a9` は使いません。アプリ本体は `03f91a9` と同じで、`2405992` で変えたのは試験の記録と W-02 の道具の記録だけ）。PR のブランチの先頭は、その後に文書だけを加えたものです。**確認はブランチの先頭の SHA で行い、アプリ・試験・スクリプト・依存の指定が `2405992` と同じことを確かめます。**

```powershell
cd C:\work\fta-202605                                       # 普段のリポジトリ（例）
git fetch origin claude/pr-c-static-cache
git ls-remote origin refs/heads/claude/pr-c-static-cache    # ブランチの先頭の SHA
$sha = "<ブランチの先頭の SHA（40桁）>"
$wt  = "C:\fta-check\src-$($sha.Substring(0,7))"
git worktree add --detach $wt $sha
git -C $wt rev-parse HEAD                                   # $sha と一致すること
git -C $wt status --short                                   # 何も出ないこと
git -C $wt diff --stat 2405992cdb5273571c3c23e7ffc96410433dff19 HEAD -- fta_tool/app fta_tool/tests fta_tool/scripts fta_tool/requirements.txt fta_tool/requirements-dev.txt ':(exclude)*.md'
                                                            # 何も出ないこと（出たら止めて報告。文書 *.md の差は除く）
Test-Path "$wt\fta_tool\.env"                               # False であること
```

新しい PowerShell を開くたびに、次を設定します。

```powershell
$sha  = "<ブランチの先頭の SHA（40桁）>"
$src  = "C:\fta-check\src-$($sha.Substring(0,7))\fta_tool"
$venv = "C:\fta-check\e2e-venv"            # これまでの自動確認専用の venv（コードのフォルダの外）
$out  = "C:\fta-check\e2e"                 # 記録フォルダを作る場所（コードのフォルダの外）
$ps1  = "$src\scripts\run_browser_e2e.ps1"
$w02  = "$src\scripts\run_cache_check.ps1"
```

PR-C は `requirements.txt`・`requirements-dev.txt` を変えていません。venv の版だけ確かめます（Playwright 1.56.0、pytest-playwright 0.7.1）。

```powershell
& "$venv\Scripts\python.exe" -m pip show playwright pytest-playwright | Select-String "^(Name|Version)"
```

venv がない、または版が違う場合だけ、[manual-check-pr3.md](manual-check-pr3.md) 第12.3節の初回準備（`-Mode Setup`）を新しいフォルダで行います。

## 3. Google Chrome の自動確認

```powershell
& $ps1 -Mode Preflight -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha
# 準備確認が成功したら
& $ps1 -Mode Full -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha
```

- 準備確認は記録フォルダ `<SHA7桁>-<日時>-chrome-preflight`。判定「成功」、終了コード 0。**全必須 E2E の合格ではありません。**
- 準備確認には、W-02 のラッパー（`scripts/run_cache_check.ps1`）の確認が含まれます（`tests/e2e/test_windows_tools.py`）。この PC の **Windows PowerShell 5.1** で、構文解析、誤った SHA での中止（終了コード 9）、道具の起動と「未完了」の記録・終了コード 2 の受け渡し（ポートを使用中にして確かめる）を自動で行います。PowerShell 7（pwsh）が入っていれば、それでも別の試験として行います。**実行されたことは、記録フォルダの `e2e-report.md` の「テストごとの結果」で確かめます**：`tests/e2e/test_windows_tools.py::test_run_cache_check_ps1_with_the_installed_powershell[windows-powershell]` の行が「成功」で、備考に「Windows PowerShell 5.1.…… Desktop（…powershell.exe）で実行」と書かれます（PowerShell 7 があれば `[pwsh]` の行が別にあり、備考は「PowerShell 7.…… Core（…）で実行」）。Windows ではこの試験が準備確認の対象なので、行がない・成功でない場合は準備確認が失敗になります。版は `pytest-tmp` の `powershell-check.json` にも残ります。利用者の追加の操作はありません。実行ポリシーは変えません（スクリプトが止められた場合は失敗として報告してください）。
- 全必須 E2E は `…-chrome-full`。**合格の条件：必須 68 項目（`REQUIRED_IDS`）すべてが成功し、テスト単位の失敗・スキップ・未実施が 0 件（判定「合格」）、終了コード 0。** 件数そのものは条件にしません（PowerShell の確認と W-02 の道具の自己確認の試験も含まれます）。
- **C-03**（3画面の各操作で HTML の要求がサーバーに届くこと）が Chrome・Edge のどちらかで成功しなかった場合は、不合格として記録フォルダを渡してください。HTML の扱いの対応案は計画書 第5.5節（「C-03 が成立しない場合の対応案」）にあり、結果を見て利用者が判断します。
- PR-C の試験（`tests/e2e/test_static_cache.py`）は、試験ごとに専用のテスト用サーバー（一時の作業フォルダ、静的ファイルの一時コピー、要求の記録）を起動し、1つのブラウザコンテキスト・1つのオリジンの中で版を変えながら確かめます。通信の差し替え・キャッシュの無効化は使いません。`e2e-report.md` の C-00〜C-07 の行が、この PR の自動の判定です。
- `tests/e2e/test_cache_manual_check.py`（W-02 の道具の自己確認。キー操作は模擬）も実行されます：初めてのプロフィール、道具の目印のない旧方式の保存が残ったプロフィール、同じプロフィールでの2回続けての実行、F5 の代わりの強制の再読み込み（NG になること）。これは W-02 そのものではありません。
- `ERR_NO_BUFFER_SPACE` などで不合格になった回も、記録として残して渡してください（判定の条件は変えません）。

## 4. Microsoft Edge の自動確認（Chrome の後に）

```powershell
& $ps1 -Mode Preflight -Channel msedge -Venv $venv -OutRoot $out -ExpectedSha $sha
# 準備確認が成功したら
& $ps1 -Mode Full -Channel msedge -Venv $venv -OutRoot $out -ExpectedSha $sha
```

条件は Chrome と同じです。「起動したブラウザ」が `Microsoft Corporation …` であること。

## 5. 実際のキー操作による移行の確認（W-02。Chrome は必須、Edge は普段 FTA ツールに使う場合）

普段の Chrome（Edge）の**通常のウィンドウ**を使います。開始前に、普段のサーバーが 8001 を使っていないことを確かめてください。

```powershell
& $w02 -Venv $venv -OutRoot $out -ExpectedSha $sha -Browser chrome
# Edge を普段使う場合は、Chrome の後に（Edge のウィンドウで操作する）
& $w02 -Venv $venv -OutRoot $out -ExpectedSha $sha -Browser msedge
```

道具（`tests/e2e/cache_manual_check.py`）が案内を表示し、ブラウザの操作を検出すると自動で次へ進みます。利用者が行うのは次の操作だけです。

| 手順 | 道具が自動で行うこと | 利用者の操作 |
|---|---|---|
| 準備 | 記録フォルダの中に静的ファイルの一時コピー・試験 DB・分析「キャッシュの確認（W-02）」を作り、**PR-C の前と同じ配信**（`Cache-Control` なし）で 8001 に起動。目印の版は w0（ファイルの時刻は10日前） | — |
| 手順1（旧方式のキャッシュを作る） | 3画面の表示を（HTML の観測で）待ち、ファイルごとの始めの状態と、旧方式で保存されたか（200・`Cache-Control` なし、または要求なし）を記録（合否ではない） | `http://127.0.0.1:8001/` を開き、ヘッダーの「新規作成」→「分析一覧」→ 一覧の「編集」をクリック |
| 手順2（移行） | サーバーを止め、PR-C の配信と版 w1 にして**同じポートで起動**。3画面の Ctrl+F5 を待ち、各画面の要求がキャッシュを使わないものだったこと、ページが w1 を使ったこと、38件が 200・`Cache-Control: no-cache`・期待どおりの `Content-Type` で返ったことを判定 | 一覧・新規作成・編集の3画面で、**実際の Ctrl+F5 を1回ずつ**（画面の間はリンクで移動） |
| 手順3（更新の後の F5） | 編集画面の表示を待ってから、サーバーを止め、版 w2 にして同じポートで起動。F5 を待ち、通常の再読み込みだったこと、変更した3件（`components.css`、`common/dom.js`、深さ3の `pages/edit/factor-source.js`）が w1 の ETag で要求され 200・w2 の本文だったこと、編集画面のほかの31件が**ファイルごとに**要求されて 304 だったこと（期待の34件と名前で照合）、ページが使った CSS の計算値と2つのモジュールの目印が w2 だったことを判定 | 編集画面を表示したまま待ち、案内が出たら**編集画面で実際の F5 を1回**（Ctrl+F5 ではない） |
| 結果 | `result.md`・`result.json` を作り、一時コピーと試験 DB を削除。終了コード 0（完全な OK）・3（改善後の動作は OK、旧方式の準備に不足あり）・1（NG）・2（未完了。理由を `result.md` に記録） | — |

- ページが使った値は、テスト用サーバーが確認のあいだだけ HTML に加える小さなスクリプトが、読み込みの完了時に、そのページの `getComputedStyle` の値とモジュールが設定した目印、ナビゲーションの種類、ブラウザの版を、この回の識別子を付けて `/__fta_e2e/probe` に送って記録します。HTML は毎回取得されるため、この確認の前から保存されている（目印のない）静的ファイルが使われても、画面の表示は検出できます。値を読むために静的ファイルを追加で取得・import したり、キャッシュを無効にしたり、URL を変えたりはしません。前の回の報告や目印は識別子が違うため使いません。Console での確認・転記は不要です。
- 手順1 は合否ではなく記録です。始めの状態（ファイルごとに「要求なし（保存済みを使用）」「200・Cache-Control なし」「304」）と、旧方式の保存を作れたか（すべて／一部／なし）を `result.md` に書きます。以前の確認の保存が残っていて 304 になったファイルは「旧方式にできなかったファイル」として記録され、PR-C の動作（手順2・3）の判定とは区別されます。
- **終了コード 3** は「改善後の動作は OK、旧方式の準備に不足あり」で、終了コード 0 の完全な OK とは区別して記録します。`result.md` の「終了コード 3 の扱い」に、準備できなかったファイルと、既存の自動試験（C-04・C-05）で確認できている範囲が書かれます。**キャッシュの消去や追加の手動の試験はせず**、その記録をそのまま渡してください（必要かどうかは報告を整理した後に判断します）。
- 同じプロフィールで、もう一度実行しても構いません（前の回の保存は手順1 で旧方式に戻ります）。終わった後、このオリジンの静的ファイルは `no-cache`・`Last-Modified` 2001-01-01 として保存されるため、後でこのポートで別のサーバー（PR-C の前の版を含む）を動かしても、そのサーバーのファイルが使われます。手順2 の前に止めた場合は、`result.md` の「後片付けの注意」に従ってください。
- 各手順の待ち時間の上限は 20 分です。時間切れや Ctrl+C の中断は「未完了」で、合格にはしません。
- 記録フォルダ：`$out\<SHA7桁>-<日時>-chrome-w02`（Edge は `…-msedge-w02`）。
  - `result.md`：判定と項目ごとの結果。Ctrl+F5・F5 の行は「利用者の実操作」と書かれます（道具がサーバーの記録から、キャッシュを使わない再読み込みか通常の再読み込みかを判定したもの）。
  - `static-requests.jsonl`：サーバーが受けた要求ごとに、パス、状態（200・304）、要求の `If-None-Match`・`If-Modified-Since`・`Cache-Control`・`Pragma`、応答の ETag・`Cache-Control`・`Content-Type`、送った本文の SHA-256。
  - `probe.jsonl`：ページが報告した値（この回の識別子、パス、ナビゲーションの種類、CSS の値、モジュールの目印、ブラウザの版）。
  - `w02-output.log`（表示した案内と結果）、`server.log`（テスト用サーバーの出力）、エラーのときは `error.txt`。
- 一時コピーと試験 DB は記録フォルダの `work` に作られ、終わると削除されます。普段のコード・DB・ブラウザのデータは変わりません。
- 判定が NG・未完了のときは、記録フォルダ全体を渡してください。もう一度行う場合は、新しい記録フォルダで最初から実行します（ブラウザのキャッシュは消さない）。

## 6. 元の W-01 の確認事項の自動化先

元の W-01（DevTools でのヘッダー・MIME・304 の確認と撮影）は、次の自動確認とサーバーの記録の判定に統合しました。DevTools での再確認・転記・撮影は求めません。

| 元の W-01 の確認事項 | 自動化先 | 証跡 |
|---|---|---|
| `Cache-Control: no-cache`（200） | 第3・4節の Full：C-01〜C-04・C-06（変更したファイルの 200 の応答） | `e2e-report.md` の C-xx の判定 |
| 同（304） | 開発環境の H-02・H-03。Windows では C-01〜C-04 の 304（要求の `If-None-Match` と状態をサーバーの記録で判定） | 同上、開発環境の pytest の記録 |
| ETag が内容から作られること | H-01・H-04（開発環境）、C-01〜C-04（応答の ETag と送った本文のハッシュの照合） | 同上 |
| JavaScript の `Content-Type`（Windows の MIME） | C-02（Windows の Full。200 の `Content-Type`）、W-02 手順2（38件の `Content-Type`）。モジュールが実行されなければ全 E2E が失敗する | `e2e-report.md`、W-02 の `result.md` |
| 条件付き要求（`If-None-Match`）と 200／304 | C-01・C-02・C-04（旧 ETag の送信、変更したファイルの 200、ほかの 304）、W-02 手順3（実際の F5） | 同上、`static-requests.jsonl` |
| 画面の正常な動作 | 全必須 E2E（Windows の Full）、C-02（評価の保存・詳細の表示）、C-07（生成中の評価のボタン） | `e2e-report.md` |
| 移行済みの状態での確認 | C-04（強制の再読み込みの後の 304・各操作の更新）、W-02 手順3 | 同上 |

## 7. 後片付け

```powershell
# W-02 の道具は、終わると試験用サーバーを止め、一時コピーと試験 DB を削除します。
# 8001 で待ち受けが残っていないことを確かめる（何も出ないこと）
Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
# 確認が終わったら worktree を外す（記録フォルダ $out は残す）
cd C:\work\fta-202605
git worktree remove $wt
```

ブラウザのキャッシュ・サイトデータを消す必要はありません。

## 8. 結果の受け渡し

| 確認 | 渡すもの |
|---|---|
| Chrome・Edge の準備確認・全必須 E2E | 記録フォルダの `e2e-report.md`・`run-info.md`（失敗・中止のときは記録フォルダ全体） |
| W-02（Chrome、Edge を普段使う場合は Edge も） | 記録フォルダの `result.md`・`result.json`・`static-requests.jsonl`・`probe.jsonl` |
| 環境の事実 | Windows の版、表示倍率（実行したときの値）、`chrome://version`・`edge://version` の版の行（チャンネルの区分。確かめなかった場合は「未確認」）。W-02 の `result.md` にはページが報告したブラウザの版が入ります |

## 9. 状態

| 確認 | 状態 |
|---|---|
| 開発環境の自動試験（`56e6507`。レビューの修正の前） | 実施（計画書 第14.3節） |
| 開発環境の自動試験（`03f91a9`。レビューの修正の後） | 実施（計画書 第14.6節） |
| 開発環境の自動試験（`2405992`。記録の改善の後。受入候補） | 実施（計画書 第14.7節と PR の本文） |
| 固定版の Playwright のブラウザ（Chromium 141）での自動試験 | **未実施**（開発環境で導入できなかった。Chromium 153 の結果は 141 の結果ではない） |
| Windows の Chrome・Edge の Preflight・Full | **未実施** |
| W-02（Chrome） | **未実施** |
| W-02（Edge、普段使う場合） | **未実施** |
| 利用者の受入の判断 | **未実施** |

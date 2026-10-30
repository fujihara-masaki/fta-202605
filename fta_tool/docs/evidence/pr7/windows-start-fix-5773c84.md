# 2026-10-30 の Windows の起動の試験の失敗の原因と修正（候補 `5773c84`）

開発環境（Linux、Chromium 153 headless を --e2e-browser-executable で明示）での調査と、修正前後の判定の記録。2026-10-30 実行。**Windows の Chrome・Edge での結果ではありません。**

## 失敗した試験の仕組み

`test_close_waits_for_the_apps_own_process`（`32730b8` で追加）は、Windows の venv のランチャーの代わり（模擬ランチャー、`launcher.py`）を使う。起動の連なりは、テストのプロセス → venv の `python.exe`（Windows ではランチャー）→ 本物の Python で動く `launcher.py` → venv の `python.exe` → 本物の Python で動く `stub_server.py`（アプリ）。`start_server()` が見ているのは最初の `python.exe` だけで、アプリが HTTP に答えるまで待つ。

## 原因：模擬ランチャーが子に標準入出力を渡していなかった（試験の不具合）

- `32730b8` の模擬ランチャーは `subprocess.Popen(sys.argv[1:])` で子を起動していた。Windows の `subprocess.Popen` は、標準入出力を指定しないと `STARTF_USESTDHANDLES` を使わず、`close_fds` が既定の真なので**ハンドルを何も受け継がせない**（Python のドキュメントの `close_fds` の説明のとおり）。子の venv の `python.exe`（ランチャー）は、無効な標準ハンドルをそのまま（NULL として）本物の Python に渡す（CPython 3.12.3 `PC/launcher.c` の `safe_duplicate_handle` は `ERROR_INVALID_HANDLE` を許す）。アプリの Python は `sys.stdin`・`sys.stdout`・`sys.stderr` が `None` の状態で始まる。
- uvicorn 0.29.0 は、ログの書式を設定するときに `sys.stdout.isatty()` を呼ぶ（`uvicorn/logging.py`、色の指定がないとき）。`sys.stdout` が `None` なので設定に失敗し（`ValueError: Unable to configure formatter 'default'`）、アプリは終了コード 1 で終わる。標準エラーもないため、どこにも何も書かれない（`server.log` が空）。
- 模擬ランチャーは標準入力が閉じられるのを待ち続けるため、`start_server()` から見た「起動したプロセス」は動いたままで、アプリの終了に気づかず 60 秒待って `E2E server did not start:` になった。
- Linux では子は標準入出力（ファイル記述子 0・1・2）を受け継ぐため、開発環境では起きなかった。本物の venv のランチャーは標準ハンドルを複製して `STARTF_USESTDHANDLES` で渡す（`launcher.c` の `run_child`）ため、ランチャーを模擬しない試験（`test_the_test_server_releases_its_folder_when_closed` など）は Windows でも成功した。
- **アプリ（FTA）の不具合ではない**。テスト用サーバーは常に `start_server()` が標準入出力を指定して起動する。

**未確認**：Windows で実際にアプリが `sys.stdout` なしで始まり uvicorn の設定で止まったこと（`server.log` が空で、修正前は段階の記録がなかったため）。修正後は、同じ状況なら `server-stages.jsonl` に「標準の入出力がない」と残り、すぐに報告される（下の試験）。

### 開発環境での再現

Windows の「標準ハンドルなし」は Linux では、子の起動の直前にファイル記述子 0・1・2 を閉じることで模した。

標準入出力なしで `stub_server.py` を起動（修正前）：終了コード 1、`server.pid` だけが残り、何も書かれない。標準エラーだけを残すと、uvicorn のログの設定の失敗が出る：

```
    logging.config.dictConfig(self.log_config)
  File "/usr/lib/python3.12/logging/config.py", line 914, in dictConfig
    dictConfigClass(config).configure()
  File "/usr/lib/python3.12/logging/config.py", line 563, in configure
    raise ValueError('Unable to configure '
ValueError: Unable to configure formatter 'default'
```

修正前（`32730b8`）の `start_server()` に、子に標準入出力を渡さない模擬ランチャーを使った結果（Windows と同じ症状）：

```
after 60 s: RuntimeError('E2E server did not start:\n')
files: ['server.log', 'server.pid']
```

## 修正

1. **模擬ランチャー**（`test_display_check.py` の `LAUNCHER`）は、`launcher.c` と同じく子に標準入出力を明示して渡す（`stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr`。Windows では `subprocess` が継承できる複製を作り `STARTF_USESTDHANDLES` で渡す）。自分のプロセス ID を `launcher.pid` に書く。修正前の起動のしかたは `no-std-handles` として残し、回帰試験に使う。
2. **起動の段階の記録**（`stub_server.py`）：`server-stages.jsonl` に、Python の起動（プロセス ID・親のプロセス ID・実行ファイル・標準入出力の有無）、アプリの読み込み、ポートでの待ち受けの開始、終了、またはエラー（トレースバック）を書く（ファイルなので、標準出力・標準エラーがなくても残る）。標準入出力がないときは、uvicorn に進まずに理由を記録して終わる。
3. **起動の失敗の報告と後片付け**（`support.py` の `start_server()`・`start_failure()`・`stop_started()`）：
   - 起動したプロセスが終わったとき、アプリのプロセス（`server.pid`）が起動の途中で終わったとき（**待たずにすぐ**）、時間内に HTTP の応答がないときに失敗にする。
   - 失敗のときは、**何も止める前に**、起動したプロセスとアプリのプロセスの状態、`server-stages.jsonl`、ポートに接続できるか、を集める。その後で、起動したプロセスとその子孫（Windows は `taskkill /T /F`）と、残っていればアプリのプロセスを止め、止められなかったものを報告に書く。修正前は起動したプロセスだけを `kill` しており、ランチャーの代わりの下のアプリが残りうった。
   - 起動の待ち時間（60 秒）は変えていない（試験だけが `start_seconds` で短くできる）。
4. **`close()`**：起動したプロセスが終わった時点でアプリがまだ動いていたか（`app_outlived_process`）を記録する。

元の目的（ランチャーよりアプリが遅れて終わる場合でも、アプリ自身のプロセスの終了まで待つ）は変えていない。`test_close_waits_for_the_apps_own_process` は、模擬ランチャーが先に終わった時点でアプリがまだ動いていたこと（`app_outlived_process is True`）を確かめ、その後 `close()` がアプリの終了まで待ったことを確かめる（以前は前提の成立を確かめていなかった）。

追加した試験：

- `test_an_app_started_without_standard_handles_is_reported_at_once`：修正前の起動のしかた（`no-std-handles`）で、60 秒を待たずにすぐ失敗し、報告に「起動の途中で終了」「標準の入出力がない」、段階の記録（`python` はあり `listening` はない）が出て、模擬ランチャーとアプリのプロセスが残らないこと。Windows では修正前と同じ `Popen` の呼び方そのもの、Linux ではファイル記述子を閉じて模す。
- `test_a_server_that_does_not_answer_is_reported_then_stopped`：アプリが待ち受けを始めない（`FTA_E2E_START_DELAY`）とき、`start_seconds=5` で失敗し、報告が止める前の状態（アプリのプロセスは「動作中」、`app imported` まで、ポートは開いていない）を示し、その後で模擬ランチャーとアプリのプロセスが残らないこと。

### 修正後の報告の例（開発環境）

```
===== no-std-handles
E2E server did not start: アプリのプロセス（PID 379）が起動の途中で終了した
- 起動したプロセス（PID 378）：動作中
- アプリのプロセス（PID 379）：終了
- stub_server.py の記録（server-stages.jsonl）：
{"time": 1793346662.1129398, "stage": "python", "pid": 379, "ppid": 378, "executable": "/tmp/claude-0/-home-user-fta-202605/8138f360-15d8-55c1-a05d-56c0995df387/scratchpad/venv/bin/python", "version": "3.12.3", "streams": {"stdin": false, "stdout": false, "stderr": false}}
{"time": 1793346662.1162071, "stage": "error", "pid": 379, "error": "SystemExit: 標準の入出力がない（起動した側が渡していない）：stdin, stdout, stderr", "traceback": "Traceback (most recent call last):\n  File \"/home/user/fta-202605/fta_tool/tests/e2e/stub_server.py\", line 548, in main\n    _serve(args, workdir)\n  File \"/home/user/fta-202605/fta_tool/tests/e2e/stub_server.py\", line 571, in _serve\n    raise SystemExit(f\"標準の入出力がない（起動した側が渡していない）：{', '.join(missing)}\")\nSystemExit: 標準の入出力がない（起動した側が渡していない）：stdin, stdout, stderr\n"}
- ポート 58257：開いていない（ConnectionRefusedError: [Errno 111] Connection refused）
- 後片付け：起動したプロセスとアプリのプロセスは終了した
- server.log：空

===== pass
E2E server did not start: 5 秒たっても HTTP の応答がない
- 起動したプロセス（PID 380）：動作中
- アプリのプロセス（PID 381）：動作中
- stub_server.py の記録（server-stages.jsonl）：
{"time": 1793346662.339864, "stage": "python", "pid": 381, "ppid": 380, "executable": "/tmp/claude-0/-home-user-fta-202605/8138f360-15d8-55c1-a05d-56c0995df387/scratchpad/venv/bin/python", "version": "3.12.3", "streams": {"stdin": true, "stdout": true, "stderr": true}}
{"time": 1793346663.3067622, "stage": "app imported", "pid": 381}
- ポート 53849：開いていない（ConnectionRefusedError: [Errno 111] Connection refused）
- 後片付け：起動したプロセスとアプリのプロセスは終了した
- server.log：
WARNING:app.main:dotenv file not found at /home/user/fta-202605/fta_tool/.env — relying on shell environment variables. Copy .env.example to .env and set your values.

```

### 検出力（開発環境）

- `start_server()` から「アプリのプロセスが起動の途中で終わったらすぐ失敗にする」処理だけを外すと、`test_an_app_started_without_standard_handles_is_reported_at_once` は 60 秒待って失敗した（`AssertionError: E2E server did not start: 60 秒たっても HTTP の応答がない`、`assert (…) < 30`）。
- `stop_started()` から「残ったアプリのプロセスを止める」処理だけを外すと、`test_a_server_that_does_not_answer_is_reported_then_stopped` は失敗した（後片付けの文言がなく、アプリのプロセスが残った。この確認で残したプロセスは確認の後に止めた）。
- 下の F の修正を外すと、`test_the_server_starts_again_in_the_same_folder` は失敗した（`RuntimeError: E2E server did not start: アプリのプロセス（PID …）が起動の途中で終了した`）。
- 模擬ランチャーが標準入出力を渡さないこと自体は、Linux では再現しない（Linux の子はファイル記述子を受け継ぐ）。そのため Linux では `no-std-handles` の試験で同じ状況を模し、Windows では手順書 第3.0節の手順1で確かめる。

## F. 途中のコミット `6052d4b` の不具合：同じフォルダでの再起動を失敗にした（試験の道具の不具合。開発環境で検出）

- 上の修正の最初の版（`6052d4b`）を開発環境の Full で試すと、失敗 4（`tests/e2e/test_cache_manual_check.py` の W-02 の道具の試験 4件：`the tool did not reach B / 3画面で Ctrl+F5`）。
- 原因：W-02 の道具（`cache_manual_check.py`）は、テスト用サーバーを止めて同じフォルダ・同じポートで起動し直す。`6052d4b` の `start_server()` は、`server.pid` があればすぐ読み、そのプロセスが終わっていれば「アプリのプロセスが起動の途中で終了した」として失敗にする。2回目の起動では、新しいサーバーが書く前に、前のサーバー（停止済み）の `server.pid` を読んで誤って失敗にした。
- 修正（`5773c84`）：`start_server()` は起動の前に、前のサーバーがそのフォルダに残した `server.pid`・`server-stages.jsonl` を消す（テストの作業フォルダの中のファイルだけ）。試験 `test_the_server_starts_again_in_the_same_folder` を追加（同じフォルダ・ポートで起動し直し、2回目のサーバーのプロセス ID が1回目と違い、問い合わせに答え、自分で終了すること）。
- `6052d4b` は受入候補にしていない（Windows では使っていない）。開発環境の `6052d4b` の Full の実行は、この失敗が分かった時点で止めた（結果の記録は残していない）。

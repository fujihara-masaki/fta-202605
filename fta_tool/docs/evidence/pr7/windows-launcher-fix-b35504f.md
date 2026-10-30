# 模擬ランチャーの下でアプリが起動しない件の調査と修正（候補 `b35504f`）

開発環境（Linux、Chromium 153 headless を --e2e-browser-executable で明示）での調査と、修正前後の判定の記録。2026-10-30 実行。**Windows の Chrome・Edge での結果ではありません。原因は Windows では未確認で、`launcher_probe.py` で確かめます。**

## 分かっていること（Windows の記録から）

2026-10-30 の Windows では、試験の模擬ランチャーを使う試験だけが失敗した（`32730b8` で1件、`5773c84` で3件）。`5773c84` の3件では、`launcher.pid` はあり、`server.pid`・`server-stages.jsonl` はなく、`server.log` は空だった。起動の連なりは、テストのプロセス → venv の `python.exe`（ランチャー）→ 本物の Python で動く模擬ランチャー → venv の `python.exe`（ランチャー、2回目）→ 本物の Python で動く `stub_server.py`。模擬ランチャーは動いたが、アプリの Python は `main()` に達していない。模擬ランチャーを使わない3件は成功しており、venv のランチャー1段の起動・停止・削除・文字コードは問題ない。

## 原因の候補（どちらも Windows では未確認）

2つの模擬ランチャーに共通なのは、**自分の標準入力を `sys.stdin.buffer.read()` で読んで待っている間に、子を起動していた**ことと、子の標準ハンドルの渡し方。

1. **`5773c84` の方式（自分の標準入出力を子に渡す）**：子は、模擬ランチャーが読み取りを待っている同じパイプを標準入力として受け取る。Windows は、同期 I/O で開かれた1つのパイプ（ファイルオブジェクト）への操作を順に処理する。読み取りが終わるまで、同じパイプへのほかの操作（Python が起動の途中で標準入力を調べる処理など）が待たされうる。子の Python は、模擬ランチャーの標準入力が閉じられるまで起動の途中で止まる、という仮説。
2. **`32730b8` の方式（子に何も渡さない）**：`subprocess.Popen(command)` は Windows では `STARTF_USESTDHANDLES` を使わず、ハンドルを受け継がせない（`close_fds`）。コンソールの子の標準ハンドルには親の値がそのまま写されるが、子の中では無効か、別のものを指しうる。2段目の venv のランチャー（`launcher.c`）か本物の Python が、起動の途中で終わる、という仮説（`5773c84` の前の調査で考えた「uvicorn のログの設定で止まる」は、`main()` に達したことを前提にしており、`server.pid` がない記録とは合わない）。

Linux では、子はファイル記述子 0・1・2 を受け継ぎ、同じパイプの同時の操作も待たないため、どちらも起きない（下の確認でも、7 方式すべてで子は起動した）。

## 修正

- **模擬ランチャー**（`tests/e2e/launcher_probe.py` の `LAUNCHER`。試験と確認の道具で共通）：
  - アプリに**専用の標準入力のパイプ**（`own-stdin`）と、自分の標準出力・標準エラーを渡す。自分の標準入力が閉じられたら、アプリの標準入力を閉じて止める指示を伝え、自分はすぐ終わる（アプリより先に終わる、という試験の前提はそのまま）。
  - 「標準入出力なし」の試験は、Windows では `STARTUPINFO` に `STARTF_USESTDHANDLES` と NULL のハンドルを明示して渡す（`null-handles`。値がたまたま写る方式をやめる）。Linux では 0・1・2 を閉じる。
  - 自分のしたことを `launcher-stages.jsonl` に書く（標準出力を使わない）：起動（PID・親の PID・実行ファイル・標準入出力の有無）、子の起動の前（方式・コマンド）、子の起動の後（子の PID）または `Popen` の例外（トレースバック）、子の終了（終了コード）、標準入力が閉じられたこと、自分の終了。
- **`start_server()`**（`support.py`）：
  - 失敗の報告に、`launcher.pid`、`launcher-stages.jsonl`、記録された子の PID ごとの動作中・終了を加えた。`server.pid` がないときは「`main()` に達していない。起動の途中か、その前に止まった。子のプロセスがないとは限らない」とし、子がないとは書かない。
  - 模擬ランチャーが「子が終わった」「子を作れなかった」と記録し、`server.pid` がなければ、60 秒を待たずにすぐ失敗にする。
  - 後片付けは、起動したプロセスとその子孫（Windows は `taskkill /T /F`）、`server.pid` のプロセス、模擬ランチャーが記録した子の PID だけを止める（記録されたプロセスだけ）。
  - 前のサーバーが残した `launcher.pid`・`launcher-stages.jsonl` も、起動の前に消す（テストの作業フォルダの中だけ）。
- **FTA のアプリを使わない小さな確認**（`tests/e2e/launcher_probe.py`）：子は「最初の文で `reached.json` を書く」だけの1行の Python。7 通りの起動のしかたを、それぞれ別のフォルダで試し、子が最初の文に達したか（模擬ランチャーの標準入力を閉じる前・後）、子の PID、子の標準入出力、模擬ランチャーの記録、残ったプロセスを `probe-result.md`・`probe-result.json` に書く。

| 方式 | 内容 | 試験で起動を求めるか |
|---|---|---|
| `direct` | 模擬ランチャーなし（通常のテスト用サーバーと同じ、venv のランチャー1段） | 求める |
| `inherit-none` | 子に何も渡さない（`32730b8` の方式）。模擬ランチャーは標準入力を読んで待つ | 求めない（Windows での結果を記録するため） |
| `share-stdin` | 自分の標準入出力を子に渡し、同じ標準入力を読んで待つ（`5773c84` の方式） | 求めない（同上） |
| `share-stdin-base` | `share-stdin` で、子は2段目の venv のランチャーを通さない（`sys._base_executable`） | 求めない（2段のランチャーの影響を分ける） |
| `share-stdin-wait` | 自分の標準入出力を子に渡すが、標準入力は読まずに子の終了を待つ | 求める（読み取りの影響を分ける） |
| `own-stdin` | 子に専用の標準入力（修正後） | 求める |
| `null-handles` | 子に NULL の標準ハンドル（修正後の「標準入出力なし」） | 求める |

Windows で `share-stdin` だけが「標準入力を閉じるまで子が最初の文に達しなかった」となり、`share-stdin-wait` が起動すれば、候補1（読み取り中のパイプ）が確かめられる。`share-stdin-base` も同じなら2段のランチャーは関係しない。`inherit-none` が「最初の文に達せずに終了」なら候補2で、その終了コードが記録される。

## 開発環境での結果

確認の道具（`python -m tests.e2e.launcher_probe`）：7 方式すべてで子は起動した（Linux では起きないため。上のとおり）。

```
 方式 | 結果 | 子の標準入出力 | 残ったプロセス 
 direct | 子は起動した（0.05 秒） | {'stdin': True, 'stdout': True, 'stderr': True} | なし 
 inherit-none | 子は起動した（0.15 秒） | {'stdin': True, 'stdout': True, 'stderr': True} | なし 
 share-stdin | 子は起動した（0.1 秒） | {'stdin': True, 'stdout': True, 'stderr': True} | なし 
 share-stdin-base | 子は起動した（0.1 秒） | {'stdin': True, 'stdout': True, 'stderr': True} | なし 
 share-stdin-wait | 子は起動した（0.1 秒） | {'stdin': True, 'stdout': True, 'stderr': True} | なし 
 own-stdin | 子は起動した（0.1 秒） | {'stdin': True, 'stdout': True, 'stderr': True} | なし 
 null-handles | 子は起動した（0.1 秒） | {'stdin': False, 'stdout': False, 'stderr': False} | なし 
```

`server.pid` がなく、模擬ランチャーの子が `main()` の前に終わる場合（Windows の記録と同じ状態。ここでは子を `python -c "raise SystemExit(7)"` にして作った）：

修正前（`5773c84`）：60 秒待って、子の状態は分からない。

```
after 60 s:
E2E server did not start: 60 秒たっても HTTP の応答がない
- 起動したプロセス（PID 439）：動作中
- アプリのプロセス：server.pid がない（stub_server.py が始まっていない）
- stub_server.py の記録（server-stages.jsonl）：なし
- ポート 49781：開いていない（ConnectionRefusedError: [Errno 111] Connection refused）
- 後片付け：起動したプロセスとアプリのプロセスは終了した
- server.log：空
files: ['launcher.pid', 'server.log']
```

修正後：すぐに、模擬ランチャーの記録（子の PID・終了コード 7）とともに報告する。

```
E2E server did not start: 起動したプロセスの子が、アプリの起動の前に終わった（child exited）
- 起動したプロセス（PID 417）：動作中
- アプリのプロセス：server.pid がない（stub_server.py の main() に達していない。起動の途中か、その前に止まった。子のプロセスがないとは限らない）
- スタンドインのランチャー：launcher.pid 417、記録（launcher-stages.jsonl）：
{"time": 1793354372.7944632, "stage": "launcher started", "pid": 417, "ppid": 414, "executable": "/tmp/claude-0/-home-user-fta-202605/8138f360-15d8-55c1-a05d-56c0995df387/scratchpad/venv/bin/python", "streams": {"stdin": true, "stdout": true, "stderr": true}}
{"time": 1793354372.794522, "stage": "starting child", "pid": 417, "mode": "own-stdin", "then": "read", "command": ["/tmp/claude-0/-home-user-fta-202605/8138f360-15d8-55c1-a05d-56c0995df387/scratchpad/venv/bin/python", "-c", "raise SystemExit(7)", "-m", "tests.e2e.stub_server", "--port", "43019", "--stop-on-stdin-eof"]}
{"time": 1793354372.7950678, "stage": "child started", "pid": 417, "child_pid": 418}
{"time": 1793354372.8098407, "stage": "child exited", "pid": 417, "child_pid": 418, "exit_code": 7}
- スタンドインの子（PID 418）：終了
- stub_server.py の記録（server-stages.jsonl）：なし
- ポート 43019：開いていない（ConnectionRefusedError: [Errno 111] Connection refused）
- 後片付け：起動したプロセスとアプリのプロセスは終了した
- server.log：空
```

検出力：`start_server()` から「模擬ランチャーの子が終わったらすぐ失敗にする」処理だけを外すと、`test_a_child_that_ends_before_the_app_starts_is_reported_at_once` は 60 秒待って失敗した（`assert (…) < 30`）。

## 試験の目的は維持

`test_close_waits_for_the_apps_own_process` は、模擬ランチャー（`own-stdin`）が標準入力を閉じられてアプリより先に終わったこと（`app_outlived_process is True`、記録の順序が「標準入力が閉じられた」→「模擬ランチャーの終了」）を確かめ、その後 `close()` がアプリ自身のプロセスの終了まで待ったことを確かめる。待ち時間の延長・固定の待ち・試験の除外はしていない（確認の道具の 15 秒は、子が最初の文に達したかを見る上限で、達した子はすぐ書く）。

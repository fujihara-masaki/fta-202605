# 2026-10-30 の Windows の個別の回帰試験の失敗の原因と修正（候補 `32730b8`）

開発環境（Linux、Chromium 153 headless を --e2e-browser-executable で明示）での調査と、修正前後の判定の記録。2026-10-30 実行。**Windows の Chrome・Edge での結果ではありません。**

## A. `work/fta_tool.db` が削除できない（`WinError 32`、Edge）：試験の道具の不具合

調べたこと（原因の候補ごと）：

| 候補 | 調べた結果 |
|---|---|
| テストのプロセスの SQLite の接続が残っている | 残っていない。`E2EServer` の直接の読み書き（`query()` など）は1回ごとに `sqlite3.connect()` して `close()` する（`_Closing`）。開発環境では、閉じた後にこのプロセスが `work` の下のファイルを開いていないことを `/proc/self/fd` で確かめている（Windows ではこの一覧は取れず、空の一覧を解放の根拠にはしない：`open_handles_in()` は Windows では `None` を返す） |
| **サーバーのプロセス（またはその子）がファイルを持っている** | **これが原因と判断**。Windows の venv の `Scripts\python.exe` はランチャーで、本物の `python.exe` を子として起動し、その終了を待つ。子は「ジョブが閉じたら終了させる」ジョブ（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`）に入れられる（CPython 3.12.3 の `PC/launcher.c` の `run_child`。`PCbuild/venvlauncher.vcxproj` は同じ `launcher.c` を `VENV_REDIRECT` でビルドする）。修正前の `E2EServer.close()` は `terminate()`（Windows では `TerminateProcess`）でランチャーだけを止め、その終了を `wait()` で待っていた。ランチャーが止まるとジョブが閉じ、本物の `python.exe`（アプリ。`fta_tool.db` と `server.log` を開いている）の終了が**始まる**だけで、`wait()` はアプリの終了を待たずに戻る。その直後の削除は、アプリがまだ持っている `fta_tool.db` で `WinError 32` になる（削除は名前の順で `fta_tool.db` が最初）。Chrome では成功し Edge で失敗したのは、この時間差による（タイミングに依存する） |
| Windows に固有の一時的な使用（ウイルス対策・インデクサー） | 否定はできない（この環境では確かめられない）。修正後は、アプリのプロセスが終わったことを確かめてから削除するため、残る理由はこれだけになる。削除は回数と間隔を限って試し（10 回・0.5 秒おき、`remove_folder()`）、何回目で削除できたかを記録する。最後まで削除できなければ失敗にする |
| それ以外 | 見つかっていない |

**未確認**：利用者の Windows の venv が上のランチャーであること（Python の版と venv の作り方による。`e2e-report.md` の「Python」と、`$venv\Scripts\python.exe` と `$venv\pyvenv.cfg` の `home` の違いで分かる）と、Edge の実行で実際にアプリのプロセスが残っていたこと。Windows では再現していない。

修正：

- `E2EServer.close()` は、サーバーの標準入力を閉じて、アプリに自分で終わらせる（`stub_server.py --stop-on-stdin-eof`：uvicorn に終了を指示し、SQLAlchemy の接続を閉じてから終わる）。ランチャーは子が終わってから終わる。20 秒で終わらなければ `terminate`、さらに 10 秒で終わらなければ `kill`。
- どちらの場合も、アプリ自身のプロセス（`stub_server.py` が起動時に `server.pid` に書く）が終わるまで待つ（Windows は `OpenProcess`＋`WaitForSingleObject`、ほかは `kill(pid, 0)`）。10 秒後も残っていれば例外にする（止められないサーバーを成功にしない）。どう止まったか（`stopped`）を記録する。
- `display_check.py` は、サーバーを止められなかったときは `work` を消さずに「未完了」とし、理由を記録する。消したときは、何回目で消せたかを `result.md` の「後片付け」に書く。
- 試験 `test_the_test_server_releases_its_folder_when_closed`：アプリが自分で終了（終了コード 0）し、そのプロセスがないことを確かめ、`remove_folder()`（`ignore_errors` なし）で削除する。何回目で削除できたかを `e2e-report.md` の備考に書く。
- 追加の試験 `test_close_waits_for_the_apps_own_process`：アプリを子として動かし、標準入力が閉じられるとアプリより約 2 秒早く終わる代わりのランチャーを使い、`close()` がアプリ自身のプロセスの終了まで待つことを確かめる（Windows・Linux とも）。

削除の対象は、テストの一時フォルダ（`tmp_path` の下の `work`、道具は記録フォルダの中の `work` だけ）。利用者の通常の DB・ブラウザのプロフィールには触れない。

### 修正前後の判定（開発環境）

代わりのランチャー（`launcher.c` と同じく本物の Python を子として起動して終了を待つ。止められると即座に終わり、ジョブの代わりに約 1 秒後に子を止める）を、修正前（`795cf36`）と修正後の `start_server()` に使い、`close()` の直後に `fta_tool.db` を開いているプロセスを `/proc/*/fd` で調べた：

```
== 修正前（795cf36）
launcher pid 1214 app holders of fta_tool.db before close [1215]
close() returned after 0.00 s; how: (not recorded)
processes holding fta_tool.db right after close(): [1215]
1.5 s later: []
== 修正後
launcher pid 1226 app holders of fta_tool.db before close [1227]
close() returned after 0.36 s; how: 自分で終了（終了コード 0）。アプリのプロセス（PID 1227）の終了を確認
processes holding fta_tool.db right after close(): []
1.5 s later: []
== 修正後（アプリが 1 秒で終わらないとき：terminate の後もアプリの終了を待つ）
close() returned after 2.01 s; how: 1 秒で終わらず、止めた（terminate）。アプリのプロセス（PID 1245）の終了を確認
app gone: True
```

修正前は `close()` が戻った時点でアプリ（ランチャーの子）がまだ `fta_tool.db` を開いていた（Windows ではここで削除が `WinError 32` になる）。修正後は、`close()` はアプリのプロセスが終わってから戻る。

検出力：修正後の `support.py` から「アプリ自身のプロセスの終了を待つ」処理だけを外すと、`test_close_waits_for_the_apps_own_process` は失敗した（`AssertionError: 自分で終了（終了コード 0）`）。

## B. 子プロセスの出力の `UnicodeDecodeError`（両ブラウザ）：試験の不具合

- 原因：`test_display_check.py` の `run_tool()` は、子の Python（`display_check.py`）の出力を `encoding="utf-8"` で読んでいた。Windows の Python は、出力先がパイプやファイルのとき、`PYTHONIOENCODING` などの指定がなければロケールの文字コード（日本語の Windows では cp932）で書く。日本語の出力が UTF-8 として読めず、`subprocess` の読み取りのスレッド（Windows の `communicate()` はスレッドで読む）で `UnicodeDecodeError` が起き、pytest が `PytestUnhandledThreadExceptionWarning` を記録した。読めなかった出力は失われ（`stdout` が `None`）、道具が失敗したときの理由も試験のメッセージに出せなかった。テスト用サーバーの `server.log` も同じく cp932 で書かれ、UTF-8 として読まれていた。
- 修正：子の Python の環境を `python_env()` にまとめ、`PYTHONIOENCODING=utf-8` を指定する（標準出力・標準エラーだけ。`PYTHONUTF8` はファイルの開き方も変えるため使わない）。道具の実行とテスト用サーバー（`server.log`）の両方に使う。読み取りの側のエラーの無視・文字の置き換えはしていない。
- 追加の試験 `test_a_python_process_s_output_is_read_in_utf8`：`PYTHONIOENCODING=cp932`（Windows の既定の代わり）の環境から `python_env()` で作った子の、日本語の標準出力と標準エラーが UTF-8 でそのまま読めること。読み取りのスレッドの例外の警告はこのテストではエラーにする。

修正前後の判定（開発環境。道具が日本語のメッセージを出してすぐ終わる呼び出しで、Windows の既定の代わりに `PYTHONIOENCODING=cp932`）：

```
old (795cf36): UnicodeDecodeError: 'utf-8' codec can't decode byte 0x96 in position 0: invalid start byte
new (python_env): exit 2, stdout '未完了：記録フォルダはコードの外に指定してください：/home/user/fta-202605/fta_tool/x'
```

検出力：修正後の `support.py` から `PYTHONIOENCODING=utf-8` の行だけを外すと、`test_a_python_process_s_output_is_read_in_utf8` は `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x96 in position 0: invalid start byte` で失敗した。

**未確認**：Windows で警告が出なくなること（第3.0節の再試験で確かめる）。

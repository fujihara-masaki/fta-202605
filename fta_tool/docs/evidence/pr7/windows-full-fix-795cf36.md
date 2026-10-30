# 2026-10-30 の Windows の Full の失敗の原因と修正（候補 `795cf36`）

開発環境（Linux、Chromium 153 headless を --e2e-browser-executable で明示）での調査と、修正前後の判定の記録。2026-10-30 実行。**Windows の Chrome・Edge での結果ではありません。**

## A. 通知の「閉じる」に Tab が届かない（テスト側の不具合）

- 調査：ページの読み込み直後（何もフォーカスがない状態）に Tab を押すと、headless Chromium では最初の Tab で通知の「閉じる」に入った（通知を出していなければインスペクタの最初の操作）。ブラウザの「Tab の開始位置」が作業エリアの末尾に残っているため。開始位置をページの先頭（スキップリンク）にすると、通知の「閉じる」に届くのは **93 回目（1280×800）・79 回目（1093×500）**で、修正前の試験の上限 60 回を超える。ページの Tab で止まる操作は 111 個（1280×800）・97 個（1093×500）。
- 通知の「閉じる」は Tab の順序の中にあり、**作業エリアの最後の要因の直後、インスペクタの直前**に並ぶ（`WORK:select|一次要因13…` → `TOAST:閉じる` ×3 → `INSP:select|頂上事象`）。アプリの不具合ではない。
- 修正前の試験は、読み込み直後の開始位置という偶然の状態に頼っていた。Windows（headed の Chrome・Edge）でどこから始まったかは、この環境では再現できず**未確認**。
- 修正：巡回を利用者がクリックした位置（絞り込み欄、Shift+Tab はインスペクタの見出し）から始め、回数は「ページの Tab で止まる操作の数 + 2」（`tab_until()`）を上限にし、通知の「閉じる」3つが作業エリアの直後・インスペクタの直前に並ぶことを前後の両方向で確かめる。ページの上から Tab で届くことを確かめる試験を追加（`test_E_K01_the_notifications_are_reached_from_the_top_of_the_page`）。テストから通知のボタンに `.focus()` はしない。

修正前後の判定（開始位置を変えたもの。`old` は `18e329b` の `walk_with_notifications()`、`new` は修正後。`top` は作業ステップの余白をクリックして開始位置をページの上にしたもの、`load` は読み込み直後のまま）：

```
PASSED tests/e2e/test_zz_repro.py::test_repro[old-load-1280x800]
PASSED tests/e2e/test_zz_repro.py::test_repro[old-load-1093x500]
PASSED tests/e2e/test_zz_repro.py::test_repro[new-load-1280x800]
PASSED tests/e2e/test_zz_repro.py::test_repro[new-load-1093x500]
PASSED tests/e2e/test_zz_repro.py::test_repro[new-top-1280x800]
PASSED tests/e2e/test_zz_repro.py::test_repro[new-top-1093x500]
FAILED tests/e2e/test_zz_repro.py::test_repro[old-top-1280x800] …
FAILED tests/e2e/test_zz_repro.py::test_repro[old-top-1093x500] …
2 failed, 6 passed, 1 warning in 13.54s
```

`old-top` の失敗のエラーは `AssertionError: Tab が通知の閉じるに届いていない`（Windows と同じ）。

## B. 表示確認の道具の `work` が残る（試験の道具の不具合）

- 調査：`tests/e2e/support.py` の `start_server()` が、サーバーの標準出力の `server.log` をこのプロセスで開き、サーバーが起動した後も閉じていなかった（`E2EServer.close()` も閉じない）。Windows では、削除の共有を許さずに開いたファイル（Python の `open()` の既定）は削除できない（`PermissionError: [WinError 32]`）。`display_check.py` は `shutil.rmtree(work, ignore_errors=True)` でこの失敗を捨てていたため、`work` が残り、結果は OK のままだった。Linux では開いたファイルも削除できるため、開発環境では起きなかった。SQLite の接続は問い合わせごとに閉じており、関係しない。
- Windows で `WinError 32` が出ていたことは、この環境では確かめられない（**未確認**）。修正後は、削除できなければ理由が `result.md` に出る。
- 修正：`E2EServer.close()` がサーバーの停止の後に `server.log` のハンドルを閉じる（kill した場合も終了を待つ）。`display_check.py` は記録フォルダの `work` だけを削除し、最大 10 回（0.5 秒おき）試し、消せなければ理由（例外と残ったファイル）を記録して「未完了」（終了コード 2）にする。`ignore_errors` は使わない。

修正前（`18e329b` のコード）に修正後の回帰試験を当てた結果：

```
E       AssertionError: ['/tmp/pytest-of-root/pytest-112/test_the_test_server_releases_0/work/server.log']
E       assert ['/tmp/pytest...k/server.log'] == []
E         Left contains one more item: '/tmp/pytest-of-root/pytest-112/test_the_test_server_releases_0/work/server.log'
E         Use -v to get more diff
E       AttributeError: 'DisplayCheck' object has no attribute 'remove_work'
E       AttributeError: 'DisplayCheck' object has no attribute 'remove_work'
E       AttributeError: 'DisplayCheck' object has no attribute 'remove_work'
FAILED tests/e2e/test_display_check.py::test_the_test_server_releases_its_folder_when_closed
FAILED tests/e2e/test_display_check.py::test_the_tool_removes_its_work_folder
FAILED tests/e2e/test_display_check.py::test_a_work_folder_that_cannot_be_removed_is_not_ok
FAILED tests/e2e/test_display_check.py::test_only_the_record_folders_work_is_removed
4 failed, 14 deselected, 1 warning in 2.62s
```

修正後は同じ試験がすべて成功した。

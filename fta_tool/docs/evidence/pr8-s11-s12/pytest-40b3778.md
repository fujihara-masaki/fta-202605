# 通常の pytest と累積の全必須 E2E（対象 40b3778、開発環境 Linux、Chromium 153 を --e2e-browser-executable で明示）

対象：`40b377813931f2d3b4080a61d0b80ebf7de0b7a1`（S-11・S-12 の対策後の受入候補。クリーンな git worktree、実行の前後とも `git status --short` が 0 行、`.env` なし）。2026-11-02 03:31:05〜04:09:49 UTC。**Windows の Chrome・Edge での結果ではありません。** 実LLMは使っていません（E2E はテスト用サーバーの e2e-stub、通常の pytest は一時ディレクトリの DB とスタブ・mock）。

| 項目 | 値 |
|---|---|
| 環境 | Linux-6.18.44-fc-v185-x86_64-with-glibc2.39、Python 3.12.3、`requirements-dev.txt` の固定版（playwright 1.56.0 / pytest-playwright 0.7.1、pytest 8.2.0）を入れた venv（リポジトリの外） |
| ブラウザ | Chromium 153.0.8010.12（headless、`--e2e-browser-executable=/opt/pw-browsers/chromium`）。固定版の Chromium 141 は使っていない（PR-8 と同じ扱い） |
| 実行の順 | 1. E2E を除く → 2. 累積の全必須 E2E（Full、`e2e-report-40b3778-full.md`）→ 3. E2E を含む通常の pytest |
| 後片付け | 実行の後に残ったテスト用サーバー（`stub_server.py`）のプロセス：0 件。子プロセスで送る S-11・S-12 の要求（`tests/guarded_requests.py`）のプロセス：0 件 |

## 0. 追加の回帰試験だけ（S-11・S-12 を別々に）

追加の回帰試験は、実装の途中に開発用の作業ツリーで繰り返し実行した（コミットの前に S-11 17件・S-12 13件・T-07 23件すべて成功）。受入候補のクリーンな worktree では、下の 1.〜3. の後（04:10 UTC）に、S-11・S-12 を別々に追える形で次のとおり実行した（3. までにも同じ試験が含まれて成功している）。

```
python -m pytest -q -p no:cacheprovider tests/test_s11_delete_scope.py tests/test_s12_generate_parents.py tests/test_node_integrity.py -k "S11 or S12 or delete_api_refuses or another_analysis_directly_below"
32 passed, 21 deselected   # S-11 17、S-12 13、更新した T-07 2
python -m pytest -q -p no:cacheprovider tests/test_s11_delete_scope.py tests/test_node_integrity.py
40 passed                  # S-11 17 と T-07 全 23
python -m pytest -q -p no:cacheprovider tests/test_s12_generate_parents.py
13 passed                  # S-12（循環の要求は子プロセスで 30 秒の制限。各回とも制限より十分短く終了）
```

対策前のコードでの検出力（開発用の作業ツリー、`0e62163` に試験が読み込む名前（理由の文・定数・未使用の関数）だけを足し、削除・生成の処理は対策前のまま）：S-11・S-12 の異常系 19 件がすべて失敗、正常系はすべて成功。対策前の循環の生成要求は子プロセスの 30 秒の制限で打ち切られて失敗になり、試験全体は止まらなかった（約 3 分で全件終了、残ったプロセス 0）。

## 1. 通常の pytest（E2E を除く）

```
python -m pytest -q -p no:cacheprovider -m "not e2e" -rs
497 passed, 20 skipped, 599 deselected, 1705 warnings in 25.65s
```

終了コード 0。スキップ 20 件は、すべて PowerShell（pwsh / powershell）がないための**環境依存のスキップ**（PR-8 の `254f826` と同じ 20 件）：

```
SKIPPED [1] tests/test_run_browser_e2e_script.py:92: pwsh / powershell が見つからないため構文解析チェックをスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:123: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:130: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:143: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:154: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:245: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:274: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:290: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:302: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:330: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_browser_e2e_script.py:339: pwsh（PowerShell 7）が見つからないため、スクリプトの実行前の確認はスキップ
SKIPPED [1] tests/test_run_cache_check_script.py:44: pwsh / powershell が見つからないため構文解析チェックをスキップ
SKIPPED [1] tests/test_run_cache_check_script.py:115: pwsh（PowerShell 7）が見つからないため、ラッパーの実行の確認はスキップ（Windows では tests/e2e/test_windows_tools.py）
SKIPPED [4] tests/test_run_cache_check_script.py:128: pwsh（PowerShell 7）が見つからないため、ラッパーの実行の確認はスキップ（Windows では tests/e2e/test_windows_tools.py）
SKIPPED [1] tests/test_run_cache_check_script.py:143: pwsh（PowerShell 7）が見つからないため、ラッパーの実行の確認はスキップ（Windows では tests/e2e/test_windows_tools.py）
SKIPPED [1] tests/test_run_display_check_script.py:49: pwsh / powershell が見つからないため構文解析チェックをスキップ
SKIPPED [1] tests/test_run_langgraph_comparison_script.py:83: pwsh / powershell が見つからないため構文解析チェックをスキップ
```

## 2. 累積の全必須 E2E（Full。UI 改修の必須受入検証）

```
python -m pytest -q -p no:cacheprovider -m e2e --e2e-browser-executable=/opt/pw-browsers/chromium --e2e-required --e2e-env '開発環境（Linux、headless、Chromium 153 を明示）' --e2e-report <runs>/e2e-report-full.md --output <runs>/full-out
599 passed, 517 deselected, 115 warnings in 1134.99s (0:18:54)
```

終了コード 0。記録 `e2e-report-40b3778-full.md`：成功 599・失敗 0・**スキップ 0・未実施 0**、判定「合格」、**必須 77 項目すべて成功**（S11-DELETE-REFUSED 2件・S12-GEN-REFUSED 1件を含む）。寸法の組は base（FullSizes は未実施）。

## 3. 通常の pytest（E2E を含む）

```
python -m pytest -q -p no:cacheprovider --e2e-browser-executable=/opt/pw-browsers/chromium -rs --output <runs>/all-out
1096 passed, 20 skipped, 1817 warnings in 1159.54s (0:19:19)
```

終了コード 0。スキップ 20 件は 1. と同じ PowerShell のもの（E2E のスキップは 0 件）。

## 件数の比較（対策前 `254f826`、2026-11-02 の開発環境）

| 試験 | `254f826`（対策前） | `40b3778`（今回） | 差 |
|---|---|---|---|
| E2E を除く | 467 passed / 20 skipped | 497 passed / 20 skipped | +30（`test_s11_delete_scope.py` 17、`test_s12_generate_parents.py` 13。T-07 は更新した2件を含め 23 件のまま） |
| Full | 596 passed（75/75） | 599 passed（77/77） | +3（`test_s11_delete_refused.py` 2、`test_s12_generation_refused.py` 1） |
| E2E を含む | 1063 passed / 20 skipped | 1096 passed / 20 skipped | +33 |

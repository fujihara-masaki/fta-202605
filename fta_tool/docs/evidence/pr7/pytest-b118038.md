# 通常の pytest（対象 b118038、開発環境 Linux、Chromium 153 を --e2e-browser-executable で明示）

対象：`b118038a5fa37eaa28fceb20e54102c7a0906343`（クリーンな git worktree、未コミットの変更なし、`.env` なし）。2026-10-30 実行。**Windows の Chrome・Edge での結果ではありません。**

## 修正に関係する試験の個別の実行（E-K01・E-V01（全寸法）・道具の試験、`-W error::pytest.PytestUnhandledThreadExceptionWarning`）

記録は `e2e-report-b118038-individual.md`。

```
96 passed, 33 deselected, 1 warning in 234.43s (0:03:54)
```

## 通常の pytest（E2E を除く）

```
467 passed, 20 skipped, 596 deselected, 1413 warnings in 14.22s
```

スキップ 20件はすべて PowerShell がないため：

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

## 累積の全必須 E2E（Full）

記録は `e2e-report-b118038-full.md`（判定「合格」、必須 75 項目すべて成功）。

```
596 passed, 487 deselected, 113 warnings in 1468.63s (0:24:28)
```

## 通常の pytest（E2E を含む）

```
1063 passed, 20 skipped, 1523 warnings in 1494.93s (0:24:54)
```

## 表示領域の端数の再現（道具 `display_check.py`、ヘッドレス）

`--device-scale`・`--window-size`（・`--zoom-in-profile`：一時プロフィールの既定の拡大による、実際のブラウザの拡大）で実行。各拡大の項目は7つ。**Windows の確認ではありません。**

| 実行 | 拡大 | 表示領域（CSS px） | client | DPR | OK の項目 | 画面の大きさ（全部） |
|---|---|---|---|---|---|---|
| 表示倍率 1.5625、ウィンドウ 1220×670 | 100% | 1222.4×585.6 | 1222×585 | 1.5625 | 7 / 7 | 1910×915 |
| 表示倍率 1.25、ウィンドウ 1528×874、実際の拡大 | 100% | 1530.4×732 | 1530×732 | 1.25 | 7 / 7 | 1913×915 |
| 同上 | 125% | 1224.32×585.6 | 1224×585 | 1.5625 | 7 / 7 | 1913×915 |
| 同上 | 150%（参考） | 1020.27×488 | 1020×488 | 1.875 | 7 / 7 | 1913×915 |
| 表示倍率 1.5、ウィンドウ 1272×730、実際の拡大 | 100% | 1272×587.33 | 1272×587 | 1.5 | 7 / 7 | 1908×881 |
| 同上 | 125%（参考） | 1017.6×469.87 | 1017×470 | 1.875 | 7 / 7 | 1908×881 |
| 同上 | 150%（参考） | 848×391.56 | 848×391 | 2.25 | 5 / 7（B-3 の2項目が NG。アプリは変えていない） | 1908×881 |

どの実行も、道具の判定は OK（参考の条件の NG は判定に含めない）、終了コード 0。

すべての実行の後に、テスト用サーバーのプロセスは残っていなかった（0 件）。

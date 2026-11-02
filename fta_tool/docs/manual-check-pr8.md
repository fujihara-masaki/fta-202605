# PR-8 最終受入の準備と手順（文書更新と統合）

| 項目 | 内容 |
|---|---|
| 目的 | 実装計画 第8.8節の受入条件（特に 1・1-1・2・4）のため、受入候補の決め方、付録D の代表シナリオと試験・Windows の記録の対応、利用者の確認の手順を示す |
| 作成 | 2026-11-02（PR-8）。同日、S-11・S-12 の案1 の採用（利用者の判断）に合わせて改訂。同日、S-11・S-12 の専用 PR（`claude/pr8-s11-s12-fix`）で**最終の受入候補 `40b377813931f2d3b4080a61d0b80ebf7de0b7a1`** を決め、第1.2節・第3節・第4節・第5節・第6節を更新 |
| 対象 | UI 再設計の全体（統合用ブランチ `feature/ui-redesign` → 基準ブランチ `claude/fta-analysis-tool-Yg5yn`、PR #19） |
| 状態 | **準備のみ。利用者による PR-8 の最終受入は未実施**。**S-11・S-12 は案1（最終統合の前に、最小限のサーバー側の対策を別の1つの PR で行う）を採用**（2026-11-02、利用者）。**同日、専用 PR で実装し、受入候補 `40b3778` の開発環境の試験は成功**（[evidence/pr8-s11-s12/README.md](evidence/pr8-s11-s12/README.md)）。**Windows の Preflight → Full、付録D の補足の実操作、利用者の最終受入は未実施**（第5節）。最終受入は**対策後の受入候補**で行い、対策前のコード（`254f826` など）で先に PR-8 の最終受入を済ませることはしない。PR-7 の受入の合格（2026-11-01、PR-7 の対象範囲）を、PR-8 や UI 再設計の全体の受入の合格に読み替えない |

## 1. 進め方と SHA の追跡

### 1.1 順序

1. PR #27（PR-8 の文書）のレビューとマージ（利用者）。
2. マージ後の `feature/ui-redesign` から、**S-11・S-12 の専用の PR**（1つ）を作る。S-11 と S-12 の変更・試験は、コミットと試験の名前で別々に追える形にする（方針は計画書 第11節の「2026-11-02 の判断」、[pr8-s11-s12-options.md](pr8-s11-s12-options.md) 第6節）。
3. 専用 PR で、追加した回帰試験・通常の pytest・累積の全必須 E2E を開発環境で実施し、**受入候補の SHA** を決める（第1.2節）。
4. **同じ受入候補の SHA** で、Windows の Chrome・Edge の Preflight → Full（第5節の手順1・2）。
5. 表示倍率・IME の扱いを、受入候補と `b118038` の差分から決めて記録する（第3節・第5節の手順3）。
6. **同じ受入候補の SHA** で、付録D の補足の実操作と、利用者の最終受入（第5節の手順4・5）。
7. 専用 PR のマージ。マージ後の `feature/ui-redesign` のアプリ・試験が受入候補と同じことを確かめる（第3節）。
8. PR #19 のタイトル・本文の更新、Ready 化とマージ（利用者）。統合の後、利用環境で3画面の Ctrl+F5。

進捗（2026-11-02）：1〜3 は完了（PR #27 は `0e62163` でマージ済み。専用 PR は #28（`claude/pr8-s11-s12-fix`）、受入候補 `40b3778`、開発環境の試験は成功）。**4〜8 は未実施**。

### 1.2 SHA

| 区分 | SHA | 内容・確認方法 |
|---|---|---|
| 基準ブランチの統合前の SHA（切り戻し先） | `8a50db1740aa4e24081a656fbc090580b6d8d82a` | `claude/fta-analysis-tool-Yg5yn` の先頭（2026-11-02 に GitHub で確認。PR #19 の base）。`feature/ui-redesign` の祖先 |
| PR-8 の開始時の統合用ブランチ | `254f826072b146c11883ed37b5e9e39bacbc6ebf` | `feature/ui-redesign` の先頭（PR #26 のマージコミット）。**対策前**のコード |
| PR-7 の Windows の受入候補 | `b118038a5fa37eaa28fceb20e54102c7a0906343` | 2026-10-31 の Windows 11 Home の記録（[evidence/pr7/windows-2026-10-31-b118038.md](evidence/pr7/windows-2026-10-31-b118038.md)）。`254f826` とアプリ・試験は同じ（差分は `fta_tool/docs/` の 9 ファイルだけ）。**対策前**のコードの記録で、`b118038` の結果として保持する |
| PR-8 の開発環境の試験の対象 | `254f826`（クリーンな worktree） | 通常の pytest と累積の全必須 E2E（[evidence/pr8/README.md](evidence/pr8/README.md)）。**対策前**のコードの記録 |
| PR-8 のブランチ（文書だけ） | `claude/pr8-docs-integration`（起点 `254f826`、PR #27） | 差分は `fta_tool/README.md` と `fta_tool/docs/` だけ。HEAD の SHA は PR #27 の本文に記録する |
| S-11・S-12 の専用 PR の起点 | `0e62163b6460dfea358aea9ff582033c72799654` | `feature/ui-redesign` の先頭（PR #27 のマージコミット、2026-11-02 に GitHub で確認）。`254f826` との差分は文書だけ |
| **最終の受入候補**（S-11・S-12 の対策後） | **`40b377813931f2d3b4080a61d0b80ebf7de0b7a1`** | 専用 PR（`claude/pr8-s11-s12-fix`）の S-12 のコミット。開発環境の追加回帰・通常の pytest・累積の全必須 E2E を実施（[evidence/pr8-s11-s12/README.md](evidence/pr8-s11-s12/README.md)）。この SHA で Windows の Preflight → Full・付録D の実操作・最終受入をまとめて行う。候補の後のコミットは文書・記録だけで、`git diff --name-only 40b3778 <専用 PR の最終 HEAD> -- . ':(exclude)fta_tool/docs' ':(exclude)fta_tool/README.md' ':(exclude)fta_tool/tests/e2e/README.md'` が空であることを PR の本文に記録する（`tests/e2e/README.md` は試験の説明の文書で、試験・スクリプトは読まない。候補の後に必須項目の数（77）を書き足した） |
| 受入対象の確認（専用 PR のマージ後） | 専用 PR のマージ後の `feature/ui-redesign` の先頭 | アプリ・試験・スクリプトが最終の受入候補と同じこと（第3節のコマンド 3-2） |
| レビュー対象の SHA（PR #19） | 統合の時点の PR #19 の head（= `feature/ui-redesign` の先頭） | マージの直前に、上の受入対象の確認と同じ方法で、最終の受入候補とアプリ・試験が同じことを確かめる |

### 1.3 切り戻しの方法（計画書 第9節）

- 基準ブランチへ統合した後に戻す：統合のマージコミットを `git revert -m 1 <マージコミット>` で戻す（履歴を残す。強制 push はしない）。
- S-11・S-12 の対策だけ戻す：専用 PR のマージコミットを `git revert -m 1 <マージコミット>` で戻す（画面の PR とは独立。戻すと異常時の挙動は対策前に戻る）。戻した版は受入候補と違うため、受入の記録の扱いを利用者が判断する。
- 利用環境だけ戻す：統合前の SHA `8a50db1` を取り出して再起動する。DB のスキーマは変えていない（S-11・S-12 でも変えない方針）ので、改修後に作ったデータはそのまま旧画面で使える。ブラウザに保存した値（`fta:edit:v1:*`・`fta:genlog:v1:*`）は旧画面では使われない。
- 戻した後は、3画面で強制の再読み込み（Ctrl+F5）を行う（静的ファイルのキャッシュ制御は旧版にはないため、古い CSS・JS が残りうる）。

## 2. 承認済みの扱い（PR-7、2026-11-01。最終の受入候補でも保持する）

| 項目 | 扱い |
|---|---|
| Windows の FullSizes（全テストを PR-7 の全寸法で） | **未実施**。省くことを利用者が承認（開発環境では `d2eb76e` で 2691 件合格。Windows の結果に読み替えない）。最終の受入候補でも行わない |
| NVDA の実機の読み上げ | **未実施**。推奨の項目として未実施のまま承認。E-K03 は DOM の確認だけ |
| Edge の表示倍率 150%・拡大 150%（848×392 CSS px） | 参考の条件の **NG 2件を既知の UI 制限として保持**（2026-10-31 の判断で現状維持、将来の改善課題） |
| 画像の目視 | **代表の画像**の確認で利用者が合格と判断。全画像を確認済みとはしない |

## 3. 差分の確認（`b118038` の記録を使える範囲を決める）

S-11・S-12 の対策でアプリ（サーバー）と試験が変わるため、**最終の受入候補に「`b118038` とコードが同一であること」は求めない**。代わりに、次の2つを確かめる。

3-1 受入候補と `b118038` の差分の範囲（受入候補を決めた時点。開発環境と Windows のどちらでもよい）：

```bash
git diff --stat b118038a5fa37eaa28fceb20e54102c7a0906343 <受入候補> -- . ':(exclude)fta_tool/docs' ':(exclude)fta_tool/README.md'
git diff --name-only b118038a5fa37eaa28fceb20e54102c7a0906343 <受入候補> -- fta_tool/app/templates fta_tool/app/static fta_tool/scripts fta_tool/requirements.txt fta_tool/requirements-dev.txt
```

- 1つ目に出るのは、S-11・S-12 の専用 PR で変えたファイル（見込み：`fta_tool/app/crud.py`・`fta_tool/app/main.py`、必要なら判定の共通化のための `fta_tool/app/detail_view.py`、と試験）だけであること。
  - **2026-11-02 の確認（開発環境、`40b3778`）**：1つ目は `fta_tool/app/crud.py`・`fta_tool/app/detail_view.py`・`fta_tool/app/main.py` と試験 9 ファイル（`tests/e2e/acceptance.py`・`tests/e2e/test_edit_integrity.py`（説明の文だけ）・`tests/e2e/test_s11_delete_refused.py`・`tests/e2e/test_s12_generation_refused.py`・`tests/guarded_requests.py`・`tests/test_e2e_infrastructure.py`・`tests/test_node_integrity.py`・`tests/test_s11_delete_scope.py`・`tests/test_s12_generate_parents.py`）の計 12 ファイル。**2つ目は何も出なかった**（画面のテンプレート・CSS・JS、Windows のスクリプト、依存関係は `b118038` と同じ）。Windows でも手順0の最後のコマンドで確かめて記録する。
- 2つ目（画面のテンプレート・CSS・JS、Windows のスクリプト、依存関係）が**何も出なければ**、`b118038` の Windows の記録のうち、**画面の表示とブラウザの操作だけで決まる確認**（表示倍率・拡大の確認道具、Microsoft IME 5 か所、代表の画像の目視、PR-6 以前の F5 のブラウザ標準の確認・タブの複製など）を、`b118038` の結果のまま補足の根拠に使える（第4節の表の「補足に使える範囲」）。**新しい SHA で再実行した結果にはしない。**
- 2つ目に何か出た場合は、そのファイルに関係する表示・IME の確認を受入候補で行うか、利用者が判断する（第5節の手順3）。

3-2 専用 PR のマージ後と PR #19 の統合の直前（受入対象・レビュー対象の確認）：

```bash
git fetch origin feature/ui-redesign
git diff --name-only <受入候補> origin/feature/ui-redesign -- . ':(exclude)fta_tool/docs' ':(exclude)fta_tool/README.md'
```

何も出なければ、受入候補で行った試験と最終受入が、マージ後の版のアプリ・試験にそのまま当てはまる。（2026-11-02 の注記：S-11・S-12 の専用 PR では、受入候補 `40b3778` の後に文書の `fta_tool/tests/e2e/README.md` を更新したため、上のコマンドにはこの1ファイルが出る。試験・スクリプトはこのファイルを読まないので、`':(exclude)fta_tool/tests/e2e/README.md'` を足して空であることを確かめればよい）何か出た場合は、受入候補を作り直す（その差分の影響を確かめるまで受入の記録を使わない）。

## 4. 付録D の代表シナリオと試験・記録の対応

列の意味：

- **自動試験**：受入 ID（`tests/e2e/acceptance.py`）とテスト。S-11・S-12 の専用 PR で、必須受入項目 **S11-DELETE-REFUSED**（`tests/e2e/test_s11_delete_refused.py`）・**S12-GEN-REFUSED**（`tests/e2e/test_s12_generation_refused.py`）と、通常の pytest の回帰試験（`tests/test_s11_delete_scope.py`・`tests/test_s12_generate_parents.py`、T-07 の更新した2件）を加えた。
- **最終の受入候補での主な根拠**：受入候補の SHA での、開発環境の追加回帰・通常の pytest・累積の全必須 E2E と、**Windows の Chrome・Edge の Preflight → Full**（第5節の手順1・2）。**どのシナリオも、これが主な根拠**。
- **`b118038` などの既存の記録（補足に使える範囲）**：`b118038` の Full＝Windows 11 Home 10.0.26200、Chrome 156.0.8078.74・Edge 156.0.4314.50（headed）、e2e-stub、2026-10-31、各 598 件成功・必須 75 項目すべて成功。道具＝`display_check.py`（表示倍率と拡大、Microsoft IME 5 か所。同日、OK）。ほかの SHA の実操作は、その SHA の結果。**第3節の 3-1 の2つ目が空の場合だけ、画面の表示と操作に限って補足に使う。** サーバーの挙動（削除・生成の結果）については、`b118038`（対策前）の記録を根拠にしない。
- **S-11・S-12 の影響**：対策で変わる見込みの挙動。
- **追加の実操作・目視**：受入候補で、利用者が行うもの（第5節の手順4・5）。

| # | 付録D のシナリオ | 自動試験 | 最終の受入候補での主な根拠 | `b118038` などの既存の記録（補足に使える範囲） | S-11・S-12 の影響 | 追加の実操作・目視 | 利用者の最終受入 |
|---|---|---|---|---|---|---|---|
| 1 | 初回：0件の一覧 → 手入力またはサンプル → 作成 → ①が開く | E-L08、E-N01〜E-N03・E-N05、E-E01、E-K01（キーボードだけ） | 開発環境の Full、Windows の Chrome・Edge の Full | IME（新規作成のタイトル）：道具で Chrome・Edge OK。PR-2 `9fa2967`：手動確認 OK（`new.js` は `9fa2967` から変わっていない） | なし（見込み） | 手順4の1（起動と Ctrl+F5 を含む） | 未実施 |
| 2 | 未保存の値から生成：頂上事象・参考情報を編集し、保存せずに一次生成 → 自動保存と対象が分かる | E-G01・E-G09、E-E10、E-K01 | 同上 | なし（サーバーの生成の処理が変わるため） | S-12 の対象は二次・三次の親の経路。一次の生成の処理は変わらない（親の経路を使わない。E-G01 などの既存の試験が対策後も成功） | 手順4の2 | 未実施 |
| 3 | 評価と一括深掘り：Yes/No/未評価に分け、Yes だけから二次を生成 → 親ごとの進捗と結果 | E-E03、E-G02・E-G03・E-G05、E-K01・E-K03 | 同上 | 生成ログ・操作バーの読みやすさ：PR-6 `3ea61be`・`fc337f1`（`generation.js`・`genlog.js` は `fc337f1` から変わっていない。画面が変わらなければ補足に使える） | S-12：親指定なしの要求で不整合な親を除く・循環の検出。画面は従来どおり親を指定して送るため、正常な親の結果は変わらない（`test_S12_normal_parents_generate_as_before`、E-G02・E-G03 が対策後も成功） | 手順4の3 | 未実施 |
| 4 | 特定の親の補完：ある親に AI で追加、別の親に手動追加 → AI／手動と追加先を取り違えない | E-G07、E-E17、PR3-GEN-PARENTS、E-K01 | 同上 | IME（手動追加のタイトル）：道具で OK | S-12：追加生成（親指定あり）の循環の検出。正常な親は変わらない（同上、E-G07） | 手順4の4 | 未実施 |
| 5 | 評価の併存：Yes の要因を「直接要因でない」にし、根拠などを保存 → 3表示で意味が一貫 | E-E14・E-E02・E-E03、T-04 | 同上 | インスペクタの IME・目視：PR-5 `dbe1c04`（`factor-editor.js` は `fc337f1` から変わっていない）。保存・取消の位置：`b118038` の道具 | なし（見込み） | なし | 未実施 |
| 6 | 結果の分岐：正常、候補0件、全除外、一部の親の失敗、通信失敗、警告付き保存 | E-G03（8区分）、E-G12、PR1-STUB、S12-GEN-REFUSED | 同上 | なし（サーバーの生成の処理が変わるため） | S-12：自己参照・循環・上限超えの親は、既存の失敗の形式（`success:false`）で返り、画面は「処理失敗」と表示する（新しい区分は作っていない。S12-GEN-REFUSED） | なし（スタブの自動試験を根拠にする） | 未実施 |
| 7 | 多件・長文：全階層多数、長いタイトル・説明・警告 → 検索、横スクロール、位置の維持 | E-E04・E-E06・E-E07（30件の部分更新）、E-V01（長い名前の折り返し、一覧の長いタイトル）、PR3-LAYOUT（長い説明・メモ・根拠でペインが個別にスクロール） | 同上 | 道具：表示倍率・拡大の各組み合わせ（参考の 848×392 は既知の UI 制限） | なし（見込み） | 手順5（任意：実データの DB の写し） | 未実施 |
| 8 | 破壊操作：子孫付きの要因と分析全体の削除、取消、失敗 | E-E16・PR3-DELETE-SCOPE・T-07、E-L06、E-K02、**S11-DELETE-REFUSED**（拒否の理由の画面表示と DB の不変）、`tests/test_s11_delete_scope.py`（409 とデータの不変） | 同上 | 削除ダイアログの見た目：PR-1 `516ee00`（`list.js` は `516ee00` から変わっていない）、PR-5 `dbe1c04`。**削除の結果については根拠にしない**（対策前） | **S-11**：別の分析の子孫・自己参照・循環・走査を完了できない削除は、データを変えずに HTTP 409 と日本語の理由。正常な削除と対象不存在（404）は従来どおり | なし（拒否の表示は E2E で確かめる。不整合データの手作業での作成は求めない。手順5で実データの写しに不整合があった場合だけ、任意で写しの上で試してよい） | 未実施 |
| 9 | 出力：3形式の導線と項目差 | E-L07、T-06、PR4-LAYOUT、E-K01 | 同上 | なし | なし（見込み） | 手順4の5（実際のダウンロード） | 未実施 |
| 10 | 未保存の保護：各画面での離脱・要因の切替・再読み込み、保存の一部失敗 | E-L05、E-N04・E-N06、E-E11・E-E12・E-E15・E-E18・E-E20、E-K02 | 同上 | F5 のブラウザ標準の確認：PR-4 `7a9d517`、PR-5 `dbe1c04`、PR-6 `fc337f1`（`unsaved.js` は `fc337f1` から変わっていない） | なし（見込み） | なし | 未実施 |
| 11 | 生成中の操作：J-01 の決定どおりに止まる操作と、できる操作 | E-G04・E-G08・E-G10・E-G11・E-G12、C-07、E-K01 | 同上 | 評価のボタンの無効の見た目・生成中の F5・IME：PR-6 `fc337f1` | なし（見込み） | なし | 未実施 |

まとめ：

- **主な根拠**：最終の受入候補（対策後）の SHA での開発環境の試験と、Windows の Chrome・Edge の Preflight → Full、付録D の補足の実操作。
- **補足に使う範囲**：`b118038` の記録（とそれ以前の実操作の記録）は、その SHA の結果として保持し、第3節の 3-1 で画面のファイル・スクリプト・依存関係に差分がないと確かめた場合に限り、**画面の表示とブラウザの操作だけで決まる確認**（表示倍率・拡大、IME、代表の画像、F5 の標準の確認、タブの複製）の補足に使う。
- **根拠にしないもの**：開発環境（Linux）の成功を Windows の結果として扱わない。`b118038` の結果を新しい SHA で再実行した結果として扱わない。対策前の記録を、削除・生成のサーバーの挙動の根拠にしない。PR-7 の受入の合格を PR-8 の受入の合格として扱わない。

## 5. 最終の受入候補での Windows の確認と最終受入

前提：S-11・S-12 の専用 PR の本文に、最終の受入候補の 40 桁の SHA・開発環境の試験の結果・必須受入項目の数・Windows の Full の件数の見込みが書かれていること。**対策前のコードでは、この節を行わない。**

**2026-11-02 の値**：受入候補 `40b377813931f2d3b4080a61d0b80ebf7de0b7a1`、必須受入項目 **77**（PR-7 までの 75 に S11-DELETE-REFUSED・S12-GEN-REFUSED）。件数の見込みは [evidence/pr8-s11-s12/README.md](evidence/pr8-s11-s12/README.md) の「Windows の Full の件数の見込み」（開発環境の Full の件数に、Windows だけで実行される PowerShell の確認 2 件を足した数）。

**普段の DB は使わない**。手順1・2は自動確認の一時 DB、手順4は新しいフォルダの DB、手順5は DB の写し。AI は手順1・2がスタブ、手順4・5が mock（`AI_PROVIDER=mock`）。

### 手順0：取り出し（PowerShell。元の clone の絶対パスを保持する）

```powershell
$repo = "C:\work\fta-202605"                          # 普段のリポジトリ（元の clone）の絶対パス（例）
$sha  = "<最終の受入候補の SHA（40桁。専用 PR の本文からコピー）>"
$wt   = "C:\fta-check\src-$($sha.Substring(0,7))"     # 確認用の worktree（元の clone の外）
git -C $repo fetch origin
git -C $repo cat-file -t $sha                          # commit と表示されること
git -C $repo worktree add --detach $wt $sha
git -C $wt rev-parse HEAD                              # $sha と一致すること
git -C $wt status --short                              # 何も出ないこと
Test-Path "$wt\fta_tool\.env"                          # False であること
git -C $wt diff --name-only b118038a5fa37eaa28fceb20e54102c7a0906343 HEAD -- fta_tool/app/templates fta_tool/app/static fta_tool/scripts fta_tool/requirements.txt fta_tool/requirements-dev.txt   # 第3節 3-1 の2つ目。結果を記録
```

以降の変数（[manual-check-pr7.md](manual-check-pr7.md) 第2節と同じ）：

```powershell
$src  = "$wt\fta_tool"
$venv = "C:\fta-check\e2e-venv"               # 自動確認専用の venv（コードのフォルダの外）
$out  = "C:\fta-check\e2e"                    # 記録フォルダを作る場所（コードのフォルダの外）
$ps1  = "$src\scripts\run_browser_e2e.ps1"    # 受入候補と同じ版のスクリプト
$disp = "$src\scripts\run_display_check.ps1"
& "$venv\Scripts\python.exe" -m pip show playwright pytest-playwright | Select-String "^(Name|Version)"   # 1.56.0 / 0.7.1
```

### 手順1・2：Chrome、Edge の Preflight → Full（同じ受入候補の SHA で）

```powershell
& $ps1 -Mode Preflight -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha
& $ps1 -Mode Full      -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha   # Preflight が成功してから
& $ps1 -Mode Preflight -Channel msedge -Venv $venv -OutRoot $out -ExpectedSha $sha
& $ps1 -Mode Full      -Channel msedge -Venv $venv -OutRoot $out -ExpectedSha $sha   # Preflight が成功してから
# FullSizes は行わない（第2節。未実施として記録）
```

合格の条件（**成功件数を 598 件に固定しない**）：

- Preflight：判定「成功」、終了コード 0、「起動したブラウザ」が Chrome は `Google LLC …`、Edge は `Microsoft Corporation …`。
- Full：判定「合格」、終了コード 0、「結果（テスト単位）」が**失敗 0・スキップ 0・未実施 0**、「受入項目ごとの結果」が**すべて成功**で、その数が専用 PR の本文の必須受入項目の数（**77 項目**）と一致すること。S-11・S-12 で追加した E2E（`test_s11_delete_refused.py` の2件、`test_s12_generation_refused.py` の1件。受入項目 S11-DELETE-REFUSED・S12-GEN-REFUSED）が実行され成功していること（記録の「テストごとの結果」で名前を確かめる）。
- テストの件数は、専用 PR の本文の見込み（開発環境の Full の件数に、Windows だけの PowerShell の確認を足した数）と照らして記録する。違う場合は、その理由が分かるまで合格にしない。
- 失敗したら次へ進まず、記録フォルダを渡す。

### 手順3：表示倍率・IME（既存の記録を使える範囲の記録）

- 手順0の最後のコマンドで**何も出なかった**場合：画面のテンプレート・CSS・JS とスクリプトは `b118038` と同じ。表示倍率・拡大の全組み合わせと Microsoft IME 5 か所は、`b118038`（2026-10-31）の記録を `b118038` の結果のまま補足に使い、受入候補では再実行しない（記録欄に「`b118038` の記録を使用」と書く）。行うかどうかは利用者の判断で、行う場合は [manual-check-pr7.md](manual-check-pr7.md) 第5節のコマンドを `$disp` で実行する。
- **何か出た**場合：出たファイルに関係する表示・IME の確認（例：`static/js` の入力の処理なら IME、`static/css` ならその表示倍率）を、受入候補で第5節のコマンドで行う。範囲は利用者が判断し、行わなかった組み合わせは「未実施」と記録する。

### 手順4：新しい DB での代表の流れ（シナリオ 1〜4・9。所要 15 分前後）

普段と同じ Python・venv で、新しいフォルダを作業フォルダにして起動する（DB はそのフォルダの `fta_tool.db`）。

```powershell
$db = "C:\fta-check\pr8-new"
New-Item -ItemType Directory -Path $db | Out-Null
Set-Location $db                                       # ここから先、作業フォルダは Git の管理外
$env:AI_PROVIDER = "mock"
python -m uvicorn app.main:app --app-dir "$src" --port 8001
```

ブラウザ（普段使うもの。Edge または Chrome）で `http://localhost:8001/` を開き、一覧・新規作成・（作成後の）編集の3画面でそれぞれ1回 Ctrl+F5 を押してから：

1. 一覧（0件）→「＋ 新規分析を作成」→ サンプルを転記 → 分析タイトルを入力（Microsoft IME で日本語）→「作成して編集へ」→ ①が開く。
2. ①の頂上事象を少し変えて保存せずに、②「一次要因を生成」→ 生成ログに結果、通知が作業エリアの下に出る、頂上事象が保存済みになる。
3. 一次要因を1件 Yes、1件 No にし、③「Yesの一次要因から二次要因を生成」→ 対象の親名と件数が操作バーに出て、Yes の親だけに二次要因ができる。
4. 別の一次要因のインスペクタで「AIで追加生成」、さらに別の親で「手動追加」→ 追加先が正しく、AI／手動のタグが付く。
5. ⑤から JSON か Markdown を1つダウンロードして開き、分析の内容が入っていることを見る。
6. 見え方：通知が操作を覆わない、保存・取消が見える、文字の重なり・欠けがない（ウィンドウは普段の大きさ・拡大で）。

終わったら、サーバーの PowerShell で Ctrl+C を押して止める。

### 手順5（任意）：実データの DB の写しで開く

```powershell
$copy = "C:\fta-check\pr8-copy"
New-Item -ItemType Directory -Path $copy | Out-Null
Copy-Item "<普段の fta_tool.db のパス>" "$copy\fta_tool.db"     # コピーする（移動しない）
Set-Location $copy
$env:AI_PROVIDER = "mock"
python -m uvicorn app.main:app --app-dir "$src" --port 8001
```

一覧と、要因の多い分析の編集画面を開いて見る（写しなので普段の DB には影響しない）。不整合のある要因があれば、編集画面の構造ナビの末尾「親子関係に不整合がある要因」に出る。出た場合は記録に書く（対策後の版では、その分析・要因を削除しようとすると 409 の理由が表示される見込み。写しでも削除は試さなくてよい）。終わったら Ctrl+C で止める。

### 後片付け（作業フォルダの移動を含めて）

手順4・5で作業フォルダを Git の管理外のフォルダへ移しているため、そこで `git worktree remove` を実行すると失敗する（Git のリポジトリの外のため）。**元の clone を `git -C` で指定して**実行する。

```powershell
# サーバーを Ctrl+C で止めた後（止めないと DB・ファイルが使用中で消せない）
Remove-Item Env:AI_PROVIDER -ErrorAction SilentlyContinue
Set-Location $repo                                      # 元の clone へ戻る（DB のフォルダから出る）
git -C $repo worktree remove $wt                        # 確認用の worktree を消す（どの場所からでも同じ）
git -C $repo worktree list                              # $wt が残っていないこと
Remove-Item -Recurse -Force "C:\fta-check\pr8-new"      # 手順4の DB のフォルダ
Remove-Item -Recurse -Force "C:\fta-check\pr8-copy" -ErrorAction SilentlyContinue   # 手順5を行った場合
```

- `git worktree remove` が「untracked or modified files」で止まった場合は、`git -C $wt status --short` の出力を記録して渡す（`__pycache__/` と `*.db` は `.gitignore` の対象で、止まる理由にはならない）。`--force` は付けない。
- 記録フォルダ `$out` は残る（受け渡しに使う）。
- 自動確認のプロセスが残っていないかの確認は [manual-check-pr7.md](manual-check-pr7.md) 第7.3節。

### 記録（利用者が記入）

| 項目 | 記入 |
|---|---|
| 実施日時・確認した SHA（`git -C $wt rev-parse HEAD`） | |
| 手順0の画面のファイルの差分（何も出なかったか、出たファイル） | |
| OS・ブラウザと版・表示倍率・拡大 | |
| 手順1 Chrome：Preflight／Full（成功・失敗・スキップ・未実施、必須項目の数、記録フォルダ） | |
| 手順2 Edge：Preflight／Full（同上） | |
| 手順3：表示倍率・IME（`b118038` の記録を使用／受入候補で実施した範囲／未実施） | |
| 手順4の1〜6 | 各 OK／NG（NG は画面と状況） |
| 手順5（任意） | 実施／未実施、不整合のある要因の有無 |
| 後片付け（worktree の削除） | OK／NG |
| 判断 | 合格／不合格／条件付き |

## 6. 第8.8節の受入条件の状況（2026-11-02）

| 条件 | 状況 |
|---|---|
| 1 通常の pytest と必須受入検証が通る | **最終の受入候補 `40b3778`（対策後）の開発環境では成功**（[evidence/pr8-s11-s12/README.md](evidence/pr8-s11-s12/README.md)。Windows の Chrome・Edge の Full は未実施）。以下は対策前の記録：**対策前**の `254f826` では開発環境で成功（通常の pytest 467 passed / 20 skipped、E2E を含めて 1063 passed / 20 skipped。スキップはすべて PowerShell がないための環境依存。累積の全必須 E2E 596 passed・失敗 0・スキップ 0・未実施 0、必須 75 項目すべて成功。[evidence/pr8/README.md](evidence/pr8/README.md)）。（対策前の記録ここまで） |
| 1-1 利用者の Windows での手動確認（E2E とは別に記録） | PR-1〜PR-7 の各受入の記録はその SHA の結果として保持。**最終の受入候補での Windows の Preflight → Full と付録D の補足の実操作は未実施**（第5節） |
| 1-2 第6節の判断の記録の更新 | 計画書 第6節「PR-8 時点の J 項目の状況」で更新。J-25 の条件「安全性が確認できない削除を無条件に実行可能にしない」は、一覧からの分析の削除の経路で**対策前は満たしていない**（S-11）。**対策後（`40b3778`）はサーバーが拒否する**（開発環境の試験で確認。充足の判断は最終受入で）。J-20 の推奨の Firefox・macOS Safari は未確認 |
| 2 利用者が付録D を利用者の環境で確認し、受け入れた | **未実施**。最終の受入候補（対策後）で行う（第5節） |
| 3 README・現行仕様書の更新 | PR-8（PR #27）で更新。S-11・S-12 の対策で挙動が変わる箇所（現行仕様書 UI-03・UI-14・第5節・第8節〜第10節、README の既知の制約・API の表）は、専用 PR で更新した |
| 4 マージ前の基準ブランチの SHA を記録 | 第1.2節（`8a50db1`）。PR #19 の本文にも記録する |

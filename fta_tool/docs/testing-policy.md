# FTA分析支援ツール 試験方針（階層別：A・B・C）

## 0. この文書について

| 項目 | 内容 |
|---|---|
| 種類 | 試験方針の**正本**。継続改修での試験範囲の選び方・実行方法・結果の読み方・記録・失敗時の対応を定める。ほかの文書はこの文書を参照し、詳細な規則を重複して書かない |
| 対象 | `fta_tool/` の継続改修（アプリ・画面・API・DB・生成処理・プロンプト・設定・試験・スクリプト・依存関係・文書） |
| 適用開始 | **この文書を導入する PR が利用者に承認・マージされた時点**から、以後の改修に適用する（第2.1節） |
| 作成 | 2026-11-05（基準ブランチ `claude/fta-analysis-tool-Yg5yn` の `ce1b2eaee36482c1b4a5ae2cf3aca7ab1cbaef0c` を確認して作成）。文書だけの変更で、判定コード・必須 ID・テスト・スクリプトは変えていない |
| 関連文書 | [README](../README.md)「テストの実行」、[実ブラウザテストの手順](../tests/e2e/README.md)、[画面改修 実装計画](ui-redesign-implementation-plan.md) 第5.9.6節・第8.0節・第14.12節、Windows の手順書（[manual-check-pr7.md](manual-check-pr7.md)・[manual-check-pr8.md](manual-check-pr8.md)）、[LangGraph 比較試験](langgraph_comparison_test.md) |

用語：

| 用語 | 意味（現行の実装） |
|---|---|
| 通常の pytest | `fta_tool/` で実行する pytest。E2E を除くときは `-m "not e2e"` を付ける（第5.1節） |
| E2E | `tests/e2e/` の実ブラウザのテスト（`e2e` マーカー）。AI はスタブ、DB は一時 DB（[tests/e2e/README.md](../tests/e2e/README.md)） |
| 全必須 E2E | `pytest -m e2e --e2e-required`（または `FTA_E2E_REQUIRED=1`）。`tests/e2e/acceptance.py` の `REQUIRED_IDS`（現在 77 項目）がすべて実行・成功し、失敗・スキップ・未実施が 0 のときだけ判定「合格」 |
| Preflight | `scripts/run_browser_e2e.ps1 -Mode Preflight`（`--e2e-preflight`）。インストール済みのブラウザで少数の既存テストを動かす**準備確認**。全必須 E2E の合格ではない |
| Full | `scripts/run_browser_e2e.ps1 -Mode Full`。Windows のインストール済みの Chrome または Edge での全必須 E2E（基本寸法、PR-7 の表示のテストは自分の寸法） |
| FullSizes | `scripts/run_browser_e2e.ps1 -Mode FullSizes`。Full と同じ全必須 E2E を、全テストについて PR-7 のすべての寸法で行う（`--e2e-viewport-set pr7`）。所要は Full の数倍 |
| 開発環境 | Claude Code のリモート実行環境（Linux、Playwright 同梱の Chromium、headless）など、利用者の PC 以外の実行場所。CI はない |
| 利用者環境 | 利用者の Windows PC（インストール済みの Chrome・Edge、実際の表示倍率・IME） |
| 実Ollama | `AI_PROVIDER=ollama` で実際のモデルを呼ぶ生成。通常の pytest と E2E は実LLMを呼ばない |

## 1. 目的と背景

- UI 再設計（PR-1〜PR-8、PR-C、S-11・S-12）では、各 PR の受入に Windows 実機での全必須 E2E（Full）を求めた（[実装計画](ui-redesign-implementation-plan.md) 第5.9.6節・第8.0節）。再設計は完了し、2026-11-02 に基準ブランチへ統合された（PR #19、`7b20c98`）。
- 統合後の継続改修で、説明文だけの変更（PR #30）でも Windows の Full を毎回求めると、変更の規模に対して試験と調査の負担が大きい。Full は1ブラウザでも長時間かかり、環境要因の失敗（第2.4節）の調査も伴う。
- この文書は、**変更箇所と関連機能を十分に確かめ、影響の大きい変更と適切な節目では全回帰を行う**方針を定める。試験は可能な範囲で自動化し、利用者の手動操作・目視は自動化できない確認に絞る。

## 2. 適用範囲と既存の規定との関係

### 2.1 適用開始

- この文書を導入する PR が利用者に承認・マージされた時点から、以後の改修（その時点で未マージの PR を含む）に適用する。
- それより前に判断・マージされた PR の受入を、この方針で遡って判定し直さない。

### 2.2 UI 再設計の受入条件との関係

| 規定 | 位置づけ（この文書の導入後） |
|---|---|
| 実装計画 第5.9.6節（J-26 の実ブラウザのテスト基盤）・第8.0節（全 PR 共通の受入条件）・第8.1〜8.8節 | **UI 再設計（PR-1〜PR-8、PR-C、S-11・S-12）の受入条件**として当時適用したもの。記録・証跡・承認の内容はそのまま保持し、書き換えない |
| 第8.0節の「実ブラウザのテストは必須受入検証で記録し、未実施・スキップ・失敗が1件でもあれば合格にしない」 | **全必須 E2E を行ったとき（C）の合格条件**として維持する。A・B の部分実行の合否には当てはめない（部分実行は第5.6節で読む） |
| 第5.9.6節の「開発環境などでの E2E の成功を、実利用環境での手動確認の代わりにしない」 | 維持する。表示倍率・IME などの実操作が必要な条件は第4節の判断表の列⑤ |
| 継続改修（統合後の改修）の試験範囲 | **この文書**（A・B・C の選択、第4節） |

### 2.3 PR #30・#31 の扱い（過去の個別判断）

- [PR #31](https://github.com/fujihara-masaki/fta-202605/pull/31)（E2E 基盤：表示倍率 125%・150% での PR-7 の表示領域と横スクロールの判定）と [PR #30](https://github.com/fujihara-masaki/fta-202605/pull/30)（新規分析作成画面の説明文）は、2026-11-05 に、**Windows Full を実施しないまま**、関連・代表 E2E などを根拠に、利用者が**その PR に限った例外**として受入を承認し、マージされた（PR #31 は `9a40de0`、PR #30 は `ce1b2ea`）。
- この記録（Windows Full は未実施であること、受入の根拠、残余リスク）は各 PR の本文のとおり保持する。**この文書の導入によって、それらを「Windows Full 合格」や「この方針に沿った確認」に読み替えない。** また、この文書の一般方針を、それらの例外の承認から導いたものとして扱わない。
- 参考として、この方針で当てはめると、PR #31 は第4節の「E2E 基盤・合否判定」の行で開発環境・Windows の C が必要、PR #30 は「画面の説明文・ラベルだけ」の行で A・B（C は不要）にあたる。

### 2.4 継続事項（未解消）

- **PR4-LAYOUT の通信の停滞**：`6ea062e` の Windows Full（Windows 11 Enterprise、表示倍率 125%、Chrome 157）で、PR4-LAYOUT の 2 件が、ブラウザ内部の通信が約 22 秒停滞したことで失敗した（PR #31 の本文）。**原因は未確定で、解消していない。** PC のロックや VPN の切断などを、根拠なしに確定した原因として扱わない。次に Windows の C を行うときに再発するかを記録し、調査は `FTA_E2E_ACCESS_LOG` を使った PR4-LAYOUT だけの再現試験などで別に行う。この問題の解消は、この文書の導入の完了条件に含めない。
- そのほか、UI 再設計で承認済みの扱い（Windows の FullSizes は未実施、NVDA は未実施、848×392 CSS px の既知の UI 制限など。[manual-check-pr8.md](manual-check-pr8.md) 第2節）は変えない。

### 2.5 この文書で変えないもの

- 全必須 E2E の合格条件（`acceptance.py` の判定、`REQUIRED_IDS`、スキップ・未実施を失敗とする扱い）、`run_browser_e2e.ps1` の動作、テスト。**A・B の成功を、全必須 E2E の合格と書かない。**

## 3. A・B・C の定義

| 範囲 | 確認すること | 適用 |
|---|---|---|
| **A：変更箇所の確認** | 変更した画面・処理・文言・文書そのもの | **全 PR** |
| **B：関連機能の確認** | 変更箇所と関係する機能。影響範囲に応じて選ぶ | 第4節で必要とした PR |
| **C：全回帰の確認** | 通常のテスト一式と全必須 E2E などによる広範囲の既存機能 | 第4節で必要とした PR と、第4.3節の節目 |

### 3.1 A：変更箇所の確認

- 変更した箇所を直接確かめる試験（単体試験・テンプレートの構造テスト・該当する E2E）と、差分の確認（意図したファイルと行だけが変わっていること）。
- **文書だけの変更**では、A は次の4点とする。アプリの pytest や実ブラウザの試験を、文書の変更を理由に一律には求めない。
  1. 内容：事実（SHA・件数・日付・判断）と既存の記録が一致し、過去の記録を書き換えていない。
  2. 参照：リンクと相対パスが実在する。
  3. 記載したコマンド・オプション・ファイル名・テスト名が実装に実在する（`grep`、`pytest --help`、`pytest --collect-only -q <対象>` などで確かめる。試験自体の実行は不要）。
  4. 差分：`git diff --name-only <基準> HEAD` が文書だけで、`git diff --check` で空白の誤りがない。Markdown の構造（見出し・表・コードブロックの閉じ）が崩れていない。

### 3.2 B：関連機能の確認

- 変更箇所に依存する、または変更箇所が依存する機能を確かめる。**変更ファイルの名前だけで選ばず、処理の依存関係（呼び出し・共通部品・共有する状態）と、利用者の操作経路（同じ画面で続けて行う操作）を根拠に選ぶ。** 選んだ根拠を記録に書く（第6節）。
- 例：
  - 同じ画面の入力・保存・画面の移動
  - 文言の長さが変わることによる折り返し・配置・主要なボタンへの到達（PR-7 の表示の試験。例：`test_pr7_viewports.py` の `test_E_V01_list_and_new_screens`）
  - 変更した共通部品（`static/js/common/`、`static/css/` の共通、`templates/base.html`・`_macros.html`）を使う画面
  - 生成前の自動保存、未保存の保護、生成後の部分更新などの関連経路（例：`test_edit_generation.py` の `test_E_G01_*`、`test_edit_pr4_layout.py` の `test_E_E10_*`、`test_edit_refresh.py`）
- アプリ・試験・スクリプト・設定のコードを変える PR では、**通常の pytest（E2E を除く）一式を B に含める**（実ブラウザを使わず短時間で終わり、取りこぼしを減らせるため）。文書だけの PR には求めない。

### 3.3 C：全回帰の確認

- C は次の組み合わせで、環境の軸（第3.5節）で場所を分ける。
  - **開発環境の C**：通常の pytest（E2E を除く）一式と、開発環境の全必須 E2E（`pytest -m e2e --e2e-required`）。
  - **Windows の C**：利用者環境の Preflight → Full（第5.3・5.4節）。ブラウザ（Chrome・Edge）の範囲は第4節の列④。
- 合格条件は既存のまま：全必須 E2E は判定「合格」・終了コード 0・失敗 0・スキップ 0・未実施 0・受入項目がすべて成功（数が `REQUIRED_IDS` と一致）。通常の pytest は失敗 0（スキップは理由が環境依存であることを確かめて記録）。
- **FullSizes は C の必須要素にしない**（第5.5節）。

### 3.4 重複して実行しないこと

- C を同じ SHA・同じ実行環境・同じブラウザで行い、そこに A・B で選んだ試験がすべて含まれて成功している場合は、A・B の同じ試験を別に実行する必要はない（記録では「A・B は C の実行に含む」と書き、該当するテストが C の記録で成功していることを示す）。
- ただし、C に含まれない確認（目視、表示倍率・拡大の実操作、Microsoft IME、実Ollama、`--e2e-viewport-set pr7` の寸法、別のブラウザ）は、A・B で必要としたなら別に行う。

### 3.5 試験の範囲と、環境・ブラウザ・AI 方式の軸

A・B・C は**試験の範囲**を表す。次の軸は範囲とは別に、第4節の列で決める。

| 軸 | 値 |
|---|---|
| 実行環境 | 開発環境（Linux）／利用者環境（Windows） |
| ブラウザ | Playwright 同梱の Chromium（開発環境）／インストール済みの Google Chrome／Microsoft Edge |
| 表示倍率・入力 | 試験の画面寸法と DPR の指定（自動。実際の拡大の代わりにはならない）／Windows の表示倍率・ブラウザの拡大の実操作（`run_display_check.ps1`）／Microsoft IME の実操作（`run_display_check.ps1 -Ime` または手動） |
| AI 方式 | E2E のスタブ（`e2e-stub`）／`AI_PROVIDER=mock`／実Ollama |

例：「B を Windows の Chrome で、スタブの AI で行う」「C を開発環境で行い、Windows の C は行わない」。

### 3.6 影響範囲を説明できない場合

- 変更の影響範囲を、依存関係と操作経路で説明できない場合は、**上位の範囲（B を説明できなければ C）で確かめる。** 同じく、第4節の複数の行にあたる変更は、各列で最も上位の条件を採る。
- コードのファイルでも、**コメント・docstring・説明の文字列だけ**の変更（実行される処理・画面の表示・試験の判定が変わらない）は、そのファイルの行の C の条件に引き上げず、A（差分がコメントだけであることの確認と、そのファイルの単体試験）とする。表示される文言は「画面の説明文・ラベル」の行で扱う。

## 4. 試験範囲を選ぶ基準

### 4.1 判断表

列の意味：①A・B の確認範囲、②開発環境で C が必要になる条件、③Windows でも C が必要になる条件、④Chrome・Edge の確認範囲、⑤表示倍率・日本語 IME などの実操作が必要になる条件、⑥実Ollama での確認が必要になる条件。

| 変更内容 | ① A・B の確認範囲 | ② 開発環境の C | ③ Windows の C | ④ Chrome・Edge | ⑤ 表示倍率・IME 等の実操作 | ⑥ 実Ollama |
|---|---|---|---|---|---|---|
| **1. 文書だけ**（`*.md`、`docs/`） | A：第3.1節の4点。B：なし（手順書のコマンドを変えた場合は、実在の確認を A で行う） | 不要 | 不要 | 不要 | 不要（手順書の手順そのものを新しくした場合は、その手順を最初に使うときに確かめる） | 不要 |
| **2. 画面の説明文・ラベルだけ**（テンプレート・JS の表示文字列。要素・属性・id・class・ARIA の構造は変えない） | A：文言を検査するテスト（例：`tests/test_ui_templates.py` の T-xx）と、その画面の文言の表示。差分が文字列だけ。B：その画面の E2E のファイル全件、長さが変わる場合は PR-7 の表示の試験のうちその画面（例：`test_E_V01_list_and_new_screens`）と端数の表示領域の横スクロール（`test_the_sideways_scroll_check_at_a_fractional_display_area`）。文言が動作を説明する場合は、その動作をコードで確かめる | 不要 | 不要 | 自動：開発環境の B（Windows の Chrome の B は、長さが大きく変わり狭い表示領域で折り返しが増える場合）。目視：Chrome・Edge で変更箇所を各1回 | 長さが増えて折り返しが変わる場合：普段の表示倍率で、拡大 100%・125%・150% の目視。IME：不要 | 不要（AI に渡す文字列・プロンプトは行7） |
| **3. 画面固有の CSS・レイアウト**（`static/css/list.css`・`new.css`・`edit.css`、その画面のテンプレートの構造） | A：変更した要素の表示の試験。B：その画面の E2E 全件、PR-7 の表示の試験のうちその画面（E-V01〜E-V03、E-F01、E-K01）、編集画面なら PR3〜PR5-LAYOUT、該当ファイルを `--e2e-viewport-set pr7` で | ペインの構成・ブレークポイント（`support.py` の `LAYOUT_BOUNDARIES` に関わる幅・高さ）・固定表示（保存・取消、通知の位置）を変える場合 | ②と同じ条件 | ③にあたる場合：Chrome・Edge とも Full。それ以外：Windows の Chrome で B、Edge は目視 | 表示倍率・拡大：`run_display_check.ps1`（普段の表示倍率で `-Zooms 100,125,150`）。IME：不要 | 不要 |
| **4. 画面固有の JavaScript・入力・保存処理**（`static/js/pages/` の1画面分） | A：変更した処理の試験。B：その画面の E2E 全件と関連経路（未保存の保護・保存調整：`test_edit_leave.py`・`test_edit_switch.py`・`test_edit_pr4_layout.py`、生成前の自動保存・生成中の制限：`test_edit_generation*.py`、部分更新：`test_edit_refresh.py`） | 保存・未保存の保護・離脱・生成中の制限の振る舞い（要求の内容・順序・失敗時の扱い）を変える場合 | ②と同じ条件 | ③にあたる場合：Chrome は Full、Edge は Preflight と B。それ以外：Windows の Chrome で B | キー操作・Enter・入力の確定を扱う処理を変えた場合：Microsoft IME の実操作（`-Ime`、または該当箇所の手動）。表示倍率：表示も変える場合だけ | 不要（生成の要求の内容を変える場合は行7） |
| **5. 共通 JavaScript・共通 CSS・`base.html`**（`static/js/common/`、`static/css/tokens.css`・`base.css`・`components.css`、`templates/base.html`・`_macros.html`、`app/static_files.py`） | A：変更箇所の試験（T-01 など）。B：変更した部品を使う全画面の E2E | **必要**（実質的な変更。コメントだけは第3.6節） | **必要** | Chrome・Edge とも Full | CSS：`run_display_check.ps1`（普段の表示倍率で拡大 3 種）。IME の共通処理：`-Ime`。静的ファイルの配信・キャッシュ：W-02（`run_cache_check.ps1`、[manual-check-pr-c.md](manual-check-pr-c.md)） | 不要 |
| **6. API・保存・削除・親子関係・DB**（`app/main.py` のルート、`crud.py`・`models.py`・`schemas.py`・`database.py`・`detail_view.py`） | A：変更した処理の単体試験（例：`test_ui_endpoints.py`・`test_node_integrity.py`・`test_s11_delete_scope.py`・`test_s12_generate_parents.py`）。B：その API を呼ぶ画面の E2E（一覧の削除、編集の保存・削除・追加など） | **必要**（保存・削除・親子関係・DB の動作を変える場合） | 応答の形・エラーの扱い・DB のスキーマや移行・ファイルの扱いを変える場合 | ③にあたる場合：Chrome は Full、Edge は Preflight と B。それ以外：Windows の C は不要 | DB の移行を変える場合：実データの DB の写しで開く確認（[manual-check-pr8.md](manual-check-pr8.md) 第5節 手順5 と同じ方法）。表示倍率・IME：不要 | 不要（生成の入力を変える場合は行7） |
| **7. 生成処理・プロンプト・LangGraph・Quality Gate・利用モデル**（`app/services/` の生成・品質、`config/prompts.yaml`、モデル・件数・タイムアウトの既定値） | A：単体試験（例：`test_prompt_loader.py`・`test_ollama_generation.py`・`test_generation_workflow.py`・`test_quality_gate_*.py`・`test_factor_*.py`・`test_llm_models.py`・`test_generate_endpoint.py`）。B：生成の E2E（`test_edit_generation*.py`、E-G01〜E-G12。スタブのため画面の流れの確認） | 生成 API の応答の形・生成ワークフローの制御（再生成・判定・失敗の扱い）を変える場合。プロンプトの文言・モデルの設定だけは不要 | 生成の画面の経路（生成中の制限・生成ログ・反映）の動作が変わる場合 | ③にあたる場合：Chrome は Full、Edge は Preflight と B。それ以外：不要 | 不要 | **必要**（第8節）。動作確認は常に。比較評価はプロンプトの指示・品質要件、モデル、Quality Gate の閾値・判定、LangGraph の再生成の条件を変える場合 |
| **8. E2E 基盤・共通 fixture・合否判定・依存関係**（`tests/conftest.py`、`tests/e2e/conftest.py`・`support.py`・`acceptance.py`・`layout_checks.py`・`stub_server.py`、`scripts/run_browser_e2e.ps1` などの Windows 用スクリプト、`requirements*.txt`、`pytest.ini`） | A：基盤の試験（`test_e2e_infrastructure.py`・`test_run_browser_e2e_script.py`・`test_run_display_check_script.py` など）。B：変えた判定を使う E2E と、その判定の検出力の試験 | **必要**（収集・判定・必須 ID・記録・依存に影響するため。記録の表示文や診断だけの変更は B） | **必要**（同上） | Chrome・Edge とも Preflight → Full | 判定が表示領域・表示倍率に関わる場合：その表示倍率の Windows で、関連する E2E（B）を Full とは別に記録する（例：125%・150%） | 生成に使う依存（`requirements.txt` の LLM・LangGraph・HTTP 関係）を更新する場合：動作確認 |
| **9. 環境の変更**：ブラウザのメジャー更新、新しい Windows PC、初めて使う表示倍率、ブラウザのチャンネルの変更（例：Edge Stable と Extended Stable） | A・B：コードの変更はないため対象の試験はない。変わった環境で準備確認（Preflight）を行う（Preflight は A・B の代わりではなく、環境の確認） | 不要（開発環境の Playwright・Chromium を変える場合は行8） | 新しい PC・初めての表示倍率・チャンネルの変更：最初に使う前に Full。ブラウザのメジャー更新：次の定期の C（第4.3節）で兼ね、更新ごとには求めない（Preflight が失敗した場合や、利用中に表示・操作の異常を見つけた場合はその時点で Full） | 変わったブラウザ（PC・表示倍率の変更は Chrome・Edge とも） | 新しい PC・初めての表示倍率：`run_display_check.ps1`（その表示倍率、拡大 3 種）と `-Ime` を1回 | 新しい PC で実Ollamaを使う場合、Ollama・モデルの版を変える場合：動作確認 |
| **10. 機能統合・利用版のリリース・定期の回帰** | 第4.3節 | 第4.3節 | 第4.3節 | Chrome・Edge とも Full | リリース：代表の操作の短い確認（第4.3節）。表示倍率・IME：前回の確認の後に行3・4・5・9 にあたる変更があり、その時に行っていない場合 | リリース：前回の実Ollamaの確認の後に行7 の変更がある場合は動作確認 |

### 4.2 判断の補足

- 「必要」「〜の場合」は、その変更に**実質的な影響**があるときを指す。コメント・docstring・説明の文字列だけの変更は第3.6節。
- 行2 と行3・4 の境目：表示する文字列だけを変えるのは行2、要素の追加・削除・並べ替え・属性やクラスの変更は行3、イベントの処理や送る要求を変えるのは行4。
- 行の列③で Windows の C が「不要」でも、列④・⑤の目視・実操作・B の部分実行は行う。
- 一つの PR が複数の行にあたる場合は、列ごとに最も上位の条件を採る（第3.6節）。
- **通常の小規模な PR は、マージのたびに Full を行わない。** 第4.1節の列②・③で C が必要な PR と、第4.3節の節目だけで C を行う。

### 4.3 C を行う節目

| 節目 | 定義 | 行う C | 省略・兼用 |
|---|---|---|---|
| **機能統合** | 複数の PR を集めた統合用ブランチ（例：UI 再設計の `feature/ui-redesign`）を基準ブランチへマージする前 | 統合用ブランチの先頭で、開発環境の C と Windows の C（Chrome・Edge とも Full） | 統合用ブランチの先頭で既に C を行い、その後の差分が文書だけなら兼ねる（第7.4節） |
| **利用版のリリース** | 利用者が日常の分析に使う版を、基準ブランチの新しい SHA へ更新するとき | 前回の Windows の C（合格）の SHA から更新先までに、文書以外の変更があれば、更新先の SHA で開発環境の C と Windows の C（Chrome・Edge とも Full）。加えて代表の操作の短い確認（[manual-check-pr8.md](manual-check-pr8.md) 第5節 手順4 と同じ流れ。mock、新しい DB）と、利用環境での3画面の Ctrl+F5 | 差分が文書だけなら省略。その月の定期の C を同じ SHA で行っていれば兼ねる |
| **定期の回帰（初期案）** | 毎月1回、月末から翌月の最初の作業日までに、基準ブランチの先頭について判断する | 前回の Windows の C（合格）の SHA から基準ブランチの先頭までに、文書以外の変更がある場合：開発環境の C と Windows の C（Chrome・Edge とも Full） | **その差分が文書だけ（または変更なし）の月は省略**。同じ月に高影響の変更（行5・6・8 など）や節目で、基準ブランチの先頭（またはその祖先で、それ以降の差分が文書だけの SHA）の Windows の C を行っていれば兼ねる。C の後に文書以外の変更がマージされていれば、その変更は翌月の判断に含める |

- 定期の回帰の考え方：A・B だけでマージされた変更が少しずつ積み重なっても、多くとも約1か月で全回帰に含まれ、ブラウザの更新（行9）も同じ機会に確かめられる。改修がない月や文書だけの月は何も行わないため、負担は改修の頻度に比例する。月1回の頻度は初期案で、運用の実績（Full の所要時間、見つかった不具合）を見て利用者が見直す。自動実行のスケジュールは設けない。
- FullSizes は節目の C にも含めない（第5.5節）。

## 5. 実行方法と結果の読み方

すべて `fta_tool/` で実行する（`pytest.ini` がここを基準にする）。Windows の例は Windows PowerShell 5.1 で動く書き方で、変数は手順書（[manual-check-pr7.md](manual-check-pr7.md) 第2節）と同じ：`$sha`（確認する SHA、40 桁）、`$src`（その SHA の worktree の `fta_tool`）、`$venv`（自動確認専用の venv）、`$out`（記録フォルダを作る場所。コードのフォルダの外）、`$ps1 = "$src\scripts\run_browser_e2e.ps1"`。

### 5.1 E2E を除いた通常の pytest

```bash
cd fta_tool
pytest -m "not e2e"
```

- **`pytest` だけでは、Playwright とブラウザが入っている環境では E2E も実行する**（入っていなければ E2E はスキップ）。E2E を除くことを意図するときは `-m "not e2e"` と書き、記録にもそう書く。
- 結果は pytest の要約行（passed・failed・skipped）と終了コードで読む。スキップは理由を確かめる（PowerShell がない環境では Windows 用スクリプトの試験がスキップになる。環境依存）。
- `-m "not e2e"` で E2E を除外すると、`tests/e2e/` が収集の対象に含まれる場合（`fta_tool/` で引数なしに実行した場合を含む）、端末の最後に「実ブラウザテスト（E2E）の受入記録」の節が出て、「必須受入検証: いいえ / 判定: 不合格 / 成功 0・失敗 0・スキップ 0・未実施 N」と表示される（除外した E2E を「未実施」と数えるため。第5.6節）。終了コードは 0 のまま。**このときの合否は pytest の要約行と終了コードで読み、この節の「不合格」を通常の pytest の失敗と読まない。** 逆に、要約行の failed・error をこの説明で見逃さない。

### 5.2 A・B の部分実行（対象のファイル・テスト ID を指定）

開発環境（Linux）の例：

```bash
cd fta_tool
# 1) 想定した試験が収集されることを先に確かめる（件数を記録する）
pytest --collect-only -q tests/test_ui_templates.py -k T03
pytest --collect-only -q -m e2e tests/e2e/test_new_analysis_page.py "tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens"
# 2) 実行する（E2E は記録を新しいフォルダへ）
pytest tests/test_ui_templates.py -k T03
pytest -m e2e tests/e2e/test_new_analysis_page.py "tests/e2e/test_pr7_viewports.py::test_E_V01_list_and_new_screens" \
  --e2e-env "開発環境" --e2e-report <新しいフォルダ>/e2e-report.md
```

Windows（利用者環境、インストール済みの Chrome）の例：`run_browser_e2e.ps1` には部分実行のモードがないため、自動確認専用の venv の pytest を直接使う（[manual-check-pr7.md](manual-check-pr7.md) 第3.0節、PR #30・#31 と同じ方法）。スクリプトが行う実行前の確認（SHA の一致・未コミットの変更なし・コード側の `.env` なし）を、手で行って記録する。

```powershell
Set-Location $src
git rev-parse HEAD                      # $sha と一致すること
git status --short                      # 何も出ないこと
Test-Path "$src\.env"                   # False であること
Remove-Item Env:FTA_E2E_REQUIRED -ErrorAction SilentlyContinue   # 部分実行に全件必須の判定を付けない
$run = Join-Path $out ("{0}-{1}-chrome-partial" -f $sha.Substring(0,7), (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $run | Out-Null
$targets = @("tests\e2e\test_new_analysis_page.py", "tests\e2e\test_pr7_viewports.py::test_E_V01_list_and_new_screens")
& "$venv\Scripts\python.exe" -m pytest $targets -m e2e --collect-only -q -p no:cacheprovider 2>&1 | Tee-Object -FilePath "$run\collect.log"
& "$venv\Scripts\python.exe" -m pytest $targets -m e2e `
    --browser chromium --browser-channel chrome --headed `
    --e2e-env "利用者環境（Windows 11、Google Chrome、headed、部分実行）" --e2e-report "$run\e2e-report.md" `
    --basetemp "$run\pytest-tmp" --output "$run\failures" --screenshot only-on-failure --tracing retain-on-failure `
    -p no:cacheprovider -v -rfE 2>&1 | Tee-Object -FilePath "$run\pytest-output.log"
"終了コード $LASTEXITCODE" | Tee-Object -FilePath "$run\exit-code.txt"
```

- Edge で行う場合は `--browser-channel msedge` にする。`--output`・`--basetemp` には新しいフォルダを指定する（開始時に中身が消えるため。[tests/e2e/README.md](../tests/e2e/README.md)）。
- **想定した試験が収集・実行されたことを確かめる。** `--collect-only` の件数（`N/M tests collected (K deselected)` の N。除外がなければ `N tests collected`）と、実行後の成功件数が一致すること。0 件（pytest の終了コード 5）や、対象の中のスキップは成功として扱わない。`-k` の式の誤りで対象が減っていないかも件数で確かめる。`--collect-only` でも E2E を含むと端末に受入記録の節（判定「不合格」）が出るが、収集の確認では無視してよい。
- **必須受入検証でない実行では、E2E のスキップは終了コードを失敗にしない。** 例えばブラウザを起動できないと、対象の E2E はすべて「スキップ」になり、終了コードは 0 になる（2026-11-05 に開発環境で確認：Playwright の版に合うブラウザがない状態で `-k E_N01` の 2 件がスキップ、終了コード 0）。終了コードだけで成功と判断せず、成功件数とスキップ 0 を確かめる。
- `--basetemp` には、親のフォルダが既にある場所を指定する（上の例では `$run` を先に作っている）。親がないと、各試験の準備で `FileNotFoundError` になる。
- **部分実行に `--e2e-required` を付けない。環境変数 `FTA_E2E_REQUIRED` も設定しない**（`1`・`true`・`yes`・`on` で有効になる）。有効にすると、実行しなかった必須の受入項目がすべて「未実施」として失敗になり、終了コードが 1 になる。`--e2e-preflight` も部分実行には使わない（準備確認のテストだけに絞られる）。

### 5.3 Windows の Preflight

```powershell
& $ps1 -Mode Preflight -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha
```

- Preflight は**準備確認**（ブラウザが起動し、テスト用サーバーが応答し、編集画面が開くこと）で、終わると判定「成功」と表示される。**変更内容に合わせた A・B の確認とは目的が異なり、A・B の代わりにしない。** また全必須 E2E の合格ではない。
- 終了コード 9 は実行前の確認での中止（テストは実行していない）。

### 5.4 Windows の Full

```powershell
& $ps1 -Mode Full -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha   # Preflight が成功してから
& $ps1 -Mode Preflight -Channel msedge -Venv $venv -OutRoot $out -ExpectedSha $sha
& $ps1 -Mode Full -Channel msedge -Venv $venv -OutRoot $out -ExpectedSha $sha
```

- 合格：判定「合格」、終了コード 0、「結果（テスト単位）」が失敗 0・スキップ 0・未実施 0、「受入項目ごとの結果」がすべて成功でその数が `REQUIRED_IDS` の数（現在 77）と一致。成功件数は変更で増減するため固定しない（違うときは理由を確かめる）。
- 記録フォルダ（`e2e-report.md`・`run-info.md`・`pytest-output.log`・`failures`）は、合否にかかわらず保存する。

### 5.5 FullSizes の位置づけ

```powershell
& $ps1 -Mode FullSizes -Channel chrome -Venv $venv -OutRoot $out -ExpectedSha $sha
```

- Full と同じ全必須 E2E を、全テストについて PR-7 のすべての寸法で行う（所要は Full の数倍）。**C を行うたびに FullSizes を必須にしない。** Windows の FullSizes は UI 再設計でも省略が承認されている（[manual-check-pr8.md](manual-check-pr8.md) 第2節）。
- 行うのは、寸法の組・表示領域の判定・編集画面のブレークポイントなどを大きく変える場合に、開発環境で `pytest -m e2e --e2e-required --e2e-viewport-set pr7` として行うことを基本にし、Windows で行うかは利用者が判断する。

### 5.6 部分実行の記録（`e2e-report.md`）の読み方

現行の `tests/e2e/acceptance.py` は、`--e2e-required` も `--e2e-preflight` も付けない実行（部分実行を含む）について次のように動く。

| 記録の欄 | 部分実行での値 | 読み方 |
|---|---|---|
| 必須受入検証として実行 | 「いいえ（通常の実行）」 | 全必須 E2E ではない |
| 判定 | 多くの場合「**不合格**」 | 判定は、`REQUIRED_IDS` の全項目が実行・成功し、`-k`・`-m` で除外した E2E がないときだけ「合格」になる。部分実行では範囲外の必須項目が「未実施」になるため、**選んだ試験がすべて成功していても「不合格」になる**。このとき pytest の終了コードは 0 のまま（終了コードを失敗に変えるのは必須受入検証と準備確認のときだけ） |
| 結果（テスト単位） | 成功・失敗・スキップ・未実施 | 「未実施」は、収集されたが `-k`・`-m` で除外された E2E の数。コマンドで指定しなかったファイルの試験は収集されないため数えない |
| 受入項目ごとの結果 | 77 項目すべてが並ぶ | 範囲外の項目は「未実施」。範囲内でも、その項目の試験の一部を除外していれば「未実施」と表示されるため、**項目単位ではなく「テストごとの結果」で読む** |
| テストごとの結果 | 実行した試験と除外した試験 | 選んだ試験が**すべて「成功」**で、件数が `--collect-only` の件数と一致することを確かめる |

- 確認の例（2026-11-05、開発環境、`ce1b2ea`）：`pytest -m e2e tests/e2e/test_new_analysis_page.py -k E_N01 --e2e-report …` は、成功 2・失敗 0・スキップ 0・未実施 24（同じファイルの除外した 24 件）、判定「不合格」、終了コード 0。同じコマンドに `FTA_E2E_REQUIRED=1` を付けると、判定「不合格」、終了コード 1。
- E2E が1件も収集・除外されない実行（例：`tests/test_ui_templates.py` だけ）では、`--e2e-report` を付けても記録は書かれず、端末の節も出ない（同日に確認）。
- PR の記録では、元の `e2e-report.md` を**書き換えずに保存**し、次を**別々に**書く：
  - 「選定した A・B の範囲は成功（成功 N・失敗 0・スキップ 0、収集 N 件と一致、終了コード 0）」
  - 「C（全必須 E2E）は未実施。記録の判定『不合格』は、範囲外の必須項目の未実施によるもの」
- ただし、**選んだ試験の中に失敗・スキップがある、選んだ試験が実行されていない（収集件数より少ない）、終了コードが 0 でない場合は、A・B は成功ではない。** 「判定は不合格だが範囲外のため」という説明を、これらに当てはめない。
- 部分実行用の記録の改善は後続の課題（第10.2節）。それまでは上の読み方による。

## 6. 記録（PR の本文に貼るテンプレート）

範囲は**実行の前に**選んで書く（第7.1節）。

```markdown
## 試験の記録（試験方針：fta_tool/docs/testing-policy.md）

- 変更内容と影響範囲：<何を変えたか。依存関係・操作経路から見た影響>
- 判断表の該当行：<例：行2（画面の説明文・ラベルだけ）>
- 選定した範囲：A <内容> ／ B <内容> ／ C <実施・未実施>
- 選定の理由：<依存関係・操作経路の根拠。C を不要とした理由>
- 対象 SHA：<40桁>（試験した SHA。PR の HEAD と違う場合は差分の確認の結果：`git diff --name-only <試験した SHA> <HEAD>`）

| 確認 | 環境（OS・ブラウザと版・表示倍率・AI 方式） | 対象（テスト・コマンド） | 結果（成功・失敗・スキップ・未実施／収集件数／終了コード） |
|---|---|---|---|
| A | | | |
| B | | | |
| C | | | <実施した場合：判定・必須 N/N。未実施の場合：「未実施」> |
| 目視・実操作 | | | |
| 実Ollama | | | <動作確認・比較評価の別> |

- 対象内の失敗・スキップ・未実施：<なし／内容と扱い>
- 部分実行の記録の判定：<例：e2e-report.md の判定「不合格」は範囲外の必須項目の未実施による。選定範囲は上表のとおり>
- 今回対象外にした範囲と理由：<例：Edge の自動試験（行2 の列④により目視のみ）>
- 既知の問題・残余リスク：<例：PR4-LAYOUT の通信の停滞（未解消、今回の範囲外）>
- 例外判断：<なし／方針上必要な確認を省いた内容・理由・代わりの根拠・利用者の承認>
- 証跡：<記録フォルダ・ファイル名>
```

## 7. 実施の順序、失敗時の対応、対象 SHA の変化

### 7.1 範囲は実行の前に選ぶ

- A・B・C の範囲と対象の試験は、実行の前に決めて記録する。**失敗した試験を後から範囲外にして、合格や成功として扱わない。** 範囲を変える必要があると分かった場合は、変えた理由と元の結果を両方残す。

### 7.2 失敗したとき

1. 証跡（記録フォルダ、`e2e-report.md`、`pytest-output.log`、trace・画面）を保存し、最初の失敗の記録を残す。
2. 原因を次のどれかに分けて記録する：**アプリの不具合**／**試験の不具合**（判定・待ち・前提の誤り）／**環境要因**（ブラウザ・OS・ネットワーク・PC の状態など、根拠がある場合）／**原因未確定**。根拠のない推測を確定した原因として書かない。
3. 再試験の範囲を決める。**毎回無条件に Full を最初から繰り返さない。**
   - アプリの不具合：修正し、その修正について第4節で範囲を選び直す（修正が共通部品などに及べば C）。最初の失敗した試験は必ず含める。
   - 試験の不具合：修正した試験と、その判定を使う試験・検出力の試験を行う。共通の判定・fixture を直した場合は行8 により C。
   - 環境要因：要因を取り除いた（または記録した）うえで、失敗した試験とその関連を同じ環境で再試験する。
   - 原因未確定：合格として扱わない。再現の試験と調査の方法を記録し、扱い（再試験・継続事項・例外判断）を利用者に報告する。
4. 再試験で成功した場合も、最初の失敗・調査の結果・再試験の範囲と結果を、すべて記録に残す。

### 7.3 例外判断

- この文書の範囲内で A・B を選ぶことに、**利用者の個別の例外承認は要らない**（選定の理由を記録に書けばよい）。
- **方針上必要な確認（第4節で必要とした C、目視・実操作、実Ollamaなど）を省く場合**は例外判断とし、省いた内容・理由・代わりの根拠・残余リスクを記録し、利用者の承認を得る。PR #30・#31 の承認は、この意味の例外判断（当時の規定に対するもの）にあたる。

### 7.4 対象 SHA が変わったとき

- 試験の結果は、**実際に試験した SHA の結果**として記録する。試験していない SHA について「再試験済み」「合格」と書かない。
- 試験の後に PR の HEAD が変わった場合：`git diff --name-only <試験した SHA> <新しい HEAD>` で差分を確かめる。
  - 差分が文書だけ（試験・アプリ・スクリプト・設定・依存関係が同じ）なら、既存の結果を参照できる。記録には「結果は `<試験した SHA>` のもの。`<新しい HEAD>` との差分は文書だけ（確認したコマンドと結果）」と書く。
  - 文書以外の差分がある場合（基準ブランチの取り込みを含む）は、その差分について第4節で範囲を選び直し、必要な試験を新しい SHA で行う。取り込んだ変更が別の PR で試験済みでも、組み合わせた SHA で必要な範囲は改めて判断する。

## 8. スタブの E2E と実Ollama

### 8.1 区別

| 確認 | 何を確かめるか | 確かめないこと |
|---|---|---|
| スタブの E2E | 画面の流れ（生成の開始・生成中の制限・生成ログの区分・反映・失敗の表示）。AI は `stub_server.py` のスタブ、外部通信は遮断 | 実際のモデルの応答、生成の品質、処理時間 |
| 実Ollamaの**動作確認** | 実際のモデルで生成が最後まで通り、画面と出力が正しく扱えること | 品質の優劣（比較しない） |
| 実Ollamaの**比較評価** | 変更前後の生成の品質と処理時間を、同じ条件・複数回で比べること | — |

### 8.2 動作確認（判断表の行7・9・10 で必要な場合）

- 環境：`.env` に `AI_PROVIDER=ollama`、使うモデル（推奨 `gemma3:4b`、[README](../README.md) の Ollama の節）。モデルの一覧（`curl http://localhost:11434/api/tags`）とモデル名を記録する。普段の DB は使わず、新しいフォルダの DB で行う。
- 内容：1つの分析で、一次要因の生成、Yes の一次要因からの二次要因の生成（行7 で三次に関わる変更なら三次も）、追加生成を各1回。
- 確かめること：生成が成功する（通信失敗・処理失敗にならない）、件数が設定の範囲にある、生成ログの区分と品質警告の表示、出力（JSON・CSV・Markdown）が開ける、サーバーのログにエラーがない。処理時間は記録するが、合否にはしない。
- 変更がプロンプトの変数・分析コンテキストの受け渡しに関わる場合は、`FTA_DEBUG_PROMPT=true` でプロンプトに意図した内容が入ることも確かめる。

### 8.3 比較評価（行7 の比較評価の条件にあたる場合）

- [LangGraph 比較試験](langgraph_comparison_test.md) の道具（`scripts/run_langgraph_comparison.ps1` と `scripts/analyze_langgraph_comparison.py`）で、変更前と変更後を同じシナリオ・同じ設定・同じ反復回数で実行し、件数・形式の安定・品質の指標・処理時間を比べる。人手の品質評価の項目は同文書による。
- 比較評価の結果は、動作確認の結果と分けて記録する。比較評価で劣化が見つかった場合の扱い（採否）は利用者が判断する。

## 9. 方針の運用

- 判断表に当てはまらない変更、または判断に迷う変更は、第3.6節（上位の範囲）により、選んだ範囲と理由を PR に書く。
- この文書の改訂は文書の PR で行い、利用者の承認・マージから適用する。改訂の前に行った判断は、その時点の版で判断したものとして扱う。

## 10. 継続事項と後続の課題

### 10.1 継続事項

- PR4-LAYOUT の通信の停滞（第2.4節）：原因未確定・未解消。次の Windows の C で再発の有無を記録する。

### 10.2 後続の実装課題（この文書では実装しない）

1. **部分実行の記録の判定**：`acceptance.py` に、選んだ範囲だけを判定する区分（例：判定を「選定範囲：成功／失敗」とし、範囲外の必須項目を「範囲外」と表示する）を設け、部分実行の記録が「不合格」と表示される現状（第5.6節）を解消する。全必須 E2E の判定と終了コードは変えない。
2. **通常の pytest で E2E を除外したときの端末の表示**：`-m "not e2e"` で除外した E2E を「未実施」と数え、判定「不合格」を表示する現状（第5.1節）を、必須受入検証でない実行では誤解のない表示にする。
3. **Windows の部分実行のモード**：`run_browser_e2e.ps1` に、対象のテストを指定する部分実行のモードを加え、実行前の確認（SHA・未コミットの変更・`.env`）・記録フォルダ・収集件数の確認・`FTA_E2E_REQUIRED` の解除をスクリプトで行う。
4. **収集件数の照合**：部分実行で、想定した件数（`--collect-only` の件数）と実行件数の照合を記録に出す。
5. **記録の雛形の生成**：第6節のテンプレートの一部（SHA・環境・件数）を `e2e-report.md` から転記する補助。

各課題は、実装する場合に第4節の行8（E2E 基盤・合否判定）として扱う（開発環境・Windows の C が必要）。

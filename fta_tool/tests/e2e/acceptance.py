"""Required acceptance run for the real-browser tests (plan 5.9.6, J-26).

Two ways to run the browser tests:

* ``pytest`` (normal): E2E tests run when Playwright and Chromium are
  installed and are skipped otherwise, so ordinary development is not
  blocked.
* ``pytest -m e2e --e2e-required`` (or ``FTA_E2E_REQUIRED=1``): the required
  acceptance run of the UI redesign. A skipped E2E test is reported as a
  failure, and every acceptance ID in REQUIRED_IDS must have run and passed;
  an ID whose tests did not run ("未実施") fails the session as well.

* ``pytest -m e2e --e2e-preflight``: the preflight before a run in another
  browser (e.g. the installed Google Chrome, ``--browser-channel chrome``):
  only PREFLIGHT_TESTS run (the edit screen opens with its main parts). A
  skip, or no test at all, is a failure; success here is not the required
  run.

Each result is recorded as 成功 / 失敗 / スキップ / 未実施, together with the
environment, the commit, the browser and the viewports (``--e2e-report``
writes it as Markdown for the pull request); also when the run started and
ended, the browser channel asked for and what was actually started
(tests/e2e/conftest.py), the code-side .env, the test server and where the
evidence of failures goes. Every console error let through as the known
favicon 404 (tests/e2e/support.py) is listed with its test, URL and message.
For each failed test the files actually left in its evidence folder are
listed (pytest-playwright's options say only what it tries to keep), with
the page taken by tests/e2e/conftest.py or the reason it could not be taken.
PR3-LAYOUT records the display area it asked for and what the browser
measured before and after the app was shown, with the judgement
(tests/e2e/support.py judge_viewport: exact, a tolerated difference, or one
that is not tolerated).

This module is imported by tests/conftest.py and must not import Playwright.
"""

from __future__ import annotations

import datetime as _dt
import os
import pathlib
import platform
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

import pytest

REQUIRED_ENV = "FTA_E2E_REQUIRED"
ENV_LABEL_ENV = "FTA_E2E_ENV"
FTA_TOOL_DIR = pathlib.Path(__file__).resolve().parents[2]

# The preflight (--e2e-preflight): a few existing tests that open the edit
# screen and check its main parts, enough to show that the browser starts,
# the test server answers, test data is made and everything ends cleanly.
PREFLIGHT_TESTS = (
    "tests/e2e/test_edit_page.py::test_E_E01_without_factors_step_1_and_the_top_event",
    "tests/e2e/test_edit_page.py::test_E_E01_with_factors_step_2_and_the_first_primary_factor",
    "tests/e2e/test_edit_page.py::test_three_panes_fit_at_the_base_and_the_measured_sizes",
)

# Acceptance IDs that the required run must cover. Later PRs append theirs.
# E-xx / T-xx follow plan section 8.9; PR1-xx / PR2-xx / PR3-xx are checks
# added in PR-1 / PR-2 / PR-3 for the shared foundation, the parts that still
# run on the old processing, and conditions (or the user's decisions) that
# have no E-xx (PR4-xx: PR-4, PR5-xx: PR-5). PR1-COMPAT-NEW (the new analysis form before its migration)
# was replaced by E-N01〜E-N06 in PR-2; PR1-COMPAT-EDIT (the old edit screen)
# by E-E01〜 and PR3-LEGACY-OPS in PR-3.
REQUIRED_IDS: dict[str, str] = {
    "E-L01": "一覧から分析を開く（タイトル・「編集」）、並び順",
    "E-L02": "改名：Enter で保存、Esc・取消、変換中の Enter では保存しない",
    "E-L03": "改名の検査（空・256文字）と、サーバーのエラー理由の表示",
    "E-L04": "改名してもブラウザのタブ名が変わらない",
    "E-L05": "改名中の移動：3択、保存して移動の成功・失敗、破棄、継続、変更なしなら確認なし、別の行の ✎",
    "E-L06": "分析の削除ダイアログ：件数、キャンセル・Esc、確定、失敗時の表示",
    "E-L07": "出力メニュー：キーボード操作、URL と download、改名中でも離脱確認が出ない",
    "E-L08": "空の一覧",
    "E-X01": "全画面で、外部へのリクエストがない",
    "E-N01": "新規作成：2列の配置、4項目の保存（現行と同じ形）と編集画面への移動",
    "E-N02": "新規作成：タイトルの検査（空白のみ・256文字）、エラーとフォーカス、送信しない",
    "E-N03": "新規作成：サンプルのプレビュー・転記・未保存表示、demo_points の保存、タイトルは転記しない",
    "E-N04": "新規作成：キャンセル・ヘッダーのリンク（入力あり・なし）、入力を続ける／破棄して移動",
    "E-N05": "新規作成：二重送信で分析が2件できない、送信時に離脱確認が出ない",
    "E-N06": "新規作成：入力があるときだけブラウザの離脱確認",
    "PR1-BASE-NOTIFY": "通知：成功・警告は自動で閉じ、エラーは閉じるまで残る（J-24）。読み上げ領域",
    "PR1-BASE-STORAGE": "保存領域が使えない環境でも一覧が動き、保存領域の処理が例外を出さない",
    "PR1-BASE-A11Y": "スキップリンク、ヘッダーの aria-current、ダイアログのフォーカスの戻り先",
    "PR1-STUB": "E2E 用スタブ：作成・候補0件・処理失敗、実LLMと外部通信の遮断",
    "PR2-IME": "新規作成：タイトルの Enter は検査を経て送信、変換確定の Enter では送信しない（合成キー操作。実機は手動）",
    "PR2-NO-SAMPLES": "新規作成：サンプルの設定ファイルがなくても、サンプル欄なしで作成できる",
    "E-E01": "編集：既定の表示（要因なし→①と頂上事象、要因あり→②と最初の一次要因）",
    "E-E02": "編集：R-01 の全経路での選択と、全表示・インスペクタの一致。要確認で品質警告の全文",
    "E-E03": "編集：評価の保存と全表示への反映（ツリーを含む）、未評価に戻す、失敗時、連続クリック",
    "E-E04": "編集：絞り込み（作業リスト・一覧表は非表示、構造ナビ・ツリーは強調。文字、評価の Yes・No・未評価・要確認）、件数、生成対象が変わらない",
    "E-E05": "編集：表示タブのキー操作、選択の保持",
    "E-E06": "編集：再読み込み後の復元（選択・ステップ・タブ・スクロール・絞り込み）、不正なハッシュ、保存領域なし",
    "E-E07": "編集：部分更新の後もフォーカス・スクロール・入力中の値が残る、分析が削除されていた場合、取得の失敗、生成中は取得しない。ダイアログ（PR-5 から手動追加・削除のダイアログ。PR-3 は旧ダイアログ）を開いている間に更新されても閉じるとフォーカスが戻る、生成中に手動追加した要因が後から選んだ要因を置き換えない。一次要因を削除すると確認に要因名が出て、頂上事象が選ばれる",
    "E-E08": "編集：不正な親子関係の区分ごとの表示、走査が止まる、頂上事象として出ない、削除・追加・生成の可否と理由（すべての区分で追加生成・手動追加が無効になり、理由が見える）",
    "E-E09": "編集：demo_points を表示しない、マークアップを含む要因の文字列がそのまま文字として出る",
    "E-E19": "編集：部分更新の古い応答で表示が巻き戻らない（評価・頂上事象の保存の前に発行した取得、確定済みの評価と食い違う応答）、続けて保存される評価の間も取得しない。別のタブで後から評価が変わっても、以後の部分更新は止まらない（実際の2つのタブでも確認）",
    "PR3-LAYOUT": "編集：暫定の3ペイン（1280px 以上）が 1280×800 と利用者環境の実測値（clientWidth×clientHeight：Chrome 1905×945・Edge 1912×914）で横に並び、ページ全体の横スクロールがなく、主要な操作が見えて隠れない。1280×800・1440×900 で各ペインが個別にスクロールする（最終確認は PR-7 の E-V01〜E-V03）。表示領域は要求と実測を記録し、Chrome 1905×945 だけはアプリの表示前からある各軸 +1 CSS px までの差（レイアウトの境界を跨がないもの）を許容して実測の寸法で検査する（2026-10-06）",
    "PR3-DELETE-SCOPE": "編集：別分析の要因が子孫にある要因とその祖先・走査を完了できない・確認用の情報を取得できない場合は削除できず、削除要求が送られない。親不在・上位に不整合ありはその部分木（階層不一致の子孫を含む）だけが消え、階層不一致の要因そのものは削除できない（判断2とその追加判断）",
    "PR3-GEN-PARENTS": "編集：生成・追加生成・手動追加の親に不整合のある要因を使わない。対象0件なら要求を送らない、親指定なしの要求を送らない、対象件数と除外件数の表示（判断3）",
    "PR3-LEGACY-NOTIFY": "編集：通知（保存・生成・ダイアログ・削除・通信エラー）が共通の通知に種別どおり1回ずつ出る（旧処理の生成は同じ文言）、エラーは閉じるまで残る、旧 #toast がない（判断4）。PR-5 の要因の保存・手動追加・削除の通知と、タイトル必須の欄・ダイアログ内の表示。開いている画面内ダイアログのどの部分にも通知が重ならず、閉じると通常の位置に戻る",
    "PR3-LEGACY-OPS": "編集：暫定の旧処理（生成。PR-6 まで）と、作り直した操作（PR-4 のタイトル・①の保存・出力・一覧へ、PR-5 のインスペクタの保存・手動追加・削除）が新しい画面から再読み込みなしで使え、旧処理が保証していた内容（メモの保存と評価を変えない、品質警告の全文、追加後の選択、No の親への追加生成、削除後の親の選択、出力）を保つ。二次・三次の生成中は親ごとに「生成中…」「+N件」が出て、部分更新で消える（PR-3 の暫定）",
    "E-E10": "編集（PR-4）：①の保存と保存状態（入力中（未保存）／保存済み）。DB に直接入れた CRLF・前後の空白で未保存にならない、元に戻すと保存済み、送信後の入力は保存済みにしない、失敗時は入力と理由が残る、demo_points と未知のキーを保持し表示しない。生成前の自動保存（一次：頂上事象と参考情報、二次・三次：参考情報のみ）は保存ボタンと同じ保存・保存状態で、失敗・頂上事象が空なら生成しない",
    "E-E11": "編集（PR-4）：ヘッダーの分析タイトルの行内編集。Enter で保存、Esc・取消、フォーカスが外れたら保存（保存・取消への移動では保存しない、二重送信しない）、変換中の Enter・Esc では何もしない（合成イベント。実機の Microsoft IME は手動）、必須・255文字（コードポイント）、移動時は確認なしで保存を待って移動し、空・文字数違反・保存失敗では移動しない。①と両方の変更、部分更新の失敗で入力が残る、分析が削除されたら編集・保存を止める",
    "E-E12": "編集（PR-4）：画面を離れるときの3択（編集を続ける・Esc・破棄して移動・保存して移動）、保存して移動の順番・一部失敗・保存元ごとの結果・失敗分だけの再試行・部分成功後の破棄の説明、ブラウザ操作は標準の確認だけ（取り消すと入力が残る）",
    "E-E13": "編集（PR-4）：⑤の件数（共通データから。評価の変更・部分更新で更新、不整合の要因は別の行、直接要因は Yes と別）、出力の項目差の表、出力リンクとヘッダーの出力メニュー（一覧と同じ URL・download・キーボード操作）、未保存の入力があってもダウンロードで確認が出ない",
    "E-E20": "編集（PR-4）：保存調整処理の契約。全保存元の事前検査（不備があれば送信0件）、要因→頂上事象→参考情報の順、編集開始時の分析・要因へ保存（選択が変わっても）、一部失敗でも別の保存元を続ける、再試行は失敗分だけ、分析が見つからない場合は未送信、送信中の保存を待つ（10秒を超えたら理由を表示）、生成の準備・生成中・反映中は受け付けない",
    "PR4-LAYOUT": "編集（PR-4）：タイトルの行内編集・出力メニュー・①の保存状態と保存ボタン・⑤の表と出力リンク・離脱確認のダイアログ（一部失敗の結果を含む）が、1280×800 と利用者環境の実測値の寸法で見えて隠れず、文字が 12px 以上、ページ全体の横スクロールがない（実機での読みやすさの確認は手動）",
    "E-E14": "編集（PR-5）：実インスペクタの7項目（タイトル・説明・メモ・直接要因評価・評価コメント・根拠・再発防止策）を POST /nodes/{id}/update 1回で保存し評価を送らない。保存後に全表示（構造ナビ・作業リスト・親グループ見出し・ツリー・一覧表・パンくず・インスペクタ）・タグ・絞り込み・⑤が整合。正規化での保存状態（CRLF・空白、元に戻す、取消）、保存中の入力は保存済みにしない・保存と取消の二重操作なし、空タイトル・失敗で入力と理由が残る、保存成功と表示更新の失敗を区別し再送しない、詳細の読込み前・失敗時は入力・保存できない",
    "E-E15": "編集（PR-5）：R-01 の全経路（構造ナビ・作業リストの行・親グループ見出しの親名・ツリー・一覧表・要確認・パンくず・子要因リンク・頂上事象）で未保存なら3択、編集を続ける・Esc で選択・ステップ・ハッシュ・入力を保持しフォーカスを戻す。保存して移動は編集中の要因へ保存（移動先ではない）、①を含む一覧と要因→頂上事象→参考情報の順、事前検査（空タイトルは送信0件・移動しない）、一部失敗・再試行（部分更新で置き換わった操作元の後継へ、編集を続ける・Esc でフォーカスを戻す）、元に戻した場合・同一要因の再選択・同一要因の要確認・①だけの未保存では確認しない、A→B→A で保存元は1つ",
    "E-E16": "編集（PR-5）：要因の削除ダイアログ。対象名、サーバーの削除範囲計算による子孫件数と合計（絞り込み・表示の深さに依存しない）、画面表示時点の件数である旨。キャンセル・Esc・失敗で下書きを保持、編集中の要因・祖先の削除では「編集中の変更も破棄されます」と成功時にその下書きだけ解除、別の要因の削除では下書きを保持、削除後は親（なければ頂上事象）を選ぶ、確定時に削除可否を再確認",
    "E-E17": "編集（PR-5）：手動追加ダイアログ。追加先の表示と開始時の固定、重複の理由をダイアログ内に表示し入力を保持、Enter で追加・変換中の Enter では追加しない、追加後の自動選択は R-01 を通す（編集を続けるで元の選択と下書きを保持、追加済みの要因は残り、追加を再送しない）、遅れて届いた更新が後の選択を上書きしない（A→B と A→B→A、取り直し・生成中の保留を含む）",
    "E-E18": "編集（PR-5）：保存中・詳細読込み中の切替（保存結果は別の要因に反映されない、A→B→A で最初の古い応答を採用しない、保存前に発行した部分更新で巻き戻らない）、別の要因の追加・削除・生成結果の反映で下書きが残る、編集中の要因の外部削除で入力と理由が残り他へ送らない（要因の404と分析の404を区別）。生成中の選択保護（J-01 の一部の前倒し）：要因の保存要求を送らない、未保存なら2択（理由を表示、破棄はインスペクタの変更だけ）、未保存がなければ切替を拒否しない、生成後は3択",
    "PR5-LAYOUT": "編集（PR-5）：インスペクタの編集欄（7項目・保存状態・保存・取消・失敗の表示）、要因切替の3択、削除と手動追加のダイアログが、1280×800 と利用者環境の実測値の寸法で見えて隠れず、文字が 12px 以上、ページ全体の横スクロールがない（実機での読みやすさの確認は手動）",
}

OUTCOME_LABELS = {
    "passed": "成功",
    "failed": "失敗",
    "skipped": "スキップ",
    "not_run": "未実施",
}

# PR3-LAYOUT's judgement of the measured display area (tests/e2e/support.py).
VIEWPORT_EXACT = "一致"
VIEWPORT_TOLERATED = "許容した差"
VIEWPORT_REFUSED = "許容しない差"
VIEWPORT_VERDICTS = (VIEWPORT_EXACT, VIEWPORT_TOLERATED, VIEWPORT_REFUSED)
# The cases whose difference may be tolerated, with the CSS px allowed per
# axis (the user's instruction of 2026-10-06): chrome-1905x945 only.
VIEWPORT_ALLOWED = {"chrome-1905x945": 1}


@dataclass
class TestRecord:
    nodeid: str
    ids: list[str]
    outcome: Optional[str] = None  # passed / failed / skipped / None (= not run)
    reason: str = ""


@dataclass
class RunState:
    required: bool = False
    preflight: bool = False
    report_path: Optional[str] = None
    env_label: str = "未指定"
    records: dict[str, TestRecord] = field(default_factory=dict)
    deselected: dict[str, TestRecord] = field(default_factory=dict)
    playwright_available: bool = True
    playwright_reason: str = ""
    browser: dict[str, str] = field(default_factory=dict)
    # How the browser was asked for and what was started (tests/e2e/conftest.py).
    launch: dict = field(default_factory=dict)
    # The E2E test server: URL, working directory (its database) and log.
    server: dict[str, str] = field(default_factory=dict)
    viewports: list[str] = field(default_factory=list)
    preflight_missing: list[str] = field(default_factory=list)
    started: Optional[_dt.datetime] = None
    finished: Optional[_dt.datetime] = None
    started_clock: float = 0.0
    duration_seconds: Optional[float] = None
    id_results: dict[str, dict] = field(default_factory=dict)
    verdict: Optional[str] = None
    # The known favicon 404s let through (test, URL, message, the response),
    # and the pages whose browser records (CDP) could not be read.
    known_console: list[dict] = field(default_factory=list)
    cdp_unavailable: list[str] = field(default_factory=list)
    # Per test: where pytest-playwright keeps its screenshot and trace
    # ("folder") and the page of a failed test taken by the page fixture
    # ("screenshot": the file, or why there is none).
    evidence: dict[str, dict] = field(default_factory=dict)
    # PR3-LAYOUT, per test: the requested display area, the browser's
    # measurements before and after the app was shown and the judgement.
    viewport_checks: dict[str, dict] = field(default_factory=dict)


STATE_KEY = pytest.StashKey[RunState]()


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def state(config: pytest.Config) -> RunState:
    return config.stash[STATE_KEY]


def configure(config: pytest.Config) -> None:
    required = bool(config.getoption("e2e_required", default=False)) or _truthy(os.environ.get(REQUIRED_ENV))
    preflight = bool(config.getoption("e2e_preflight", default=False))
    if required and preflight:
        raise pytest.UsageError(
            "--e2e-preflight（準備確認）と必須受入検証（--e2e-required・FTA_E2E_REQUIRED）は同時に指定できません"
        )
    env_label = config.getoption("e2e_env", default=None) or os.environ.get(ENV_LABEL_ENV) or "未指定"
    config.stash[STATE_KEY] = RunState(
        required=required,
        preflight=preflight,
        report_path=config.getoption("e2e_report", default=None),
        env_label=env_label,
        started=_dt.datetime.now().astimezone(),
        started_clock=time.monotonic(),
    )


def _acceptance_ids(item: pytest.Item) -> list[str]:
    ids: list[str] = []
    for mark in item.iter_markers("acceptance"):
        ids.extend(str(arg) for arg in mark.args)
    return ids


def is_e2e(item: pytest.Item) -> bool:
    return item.get_closest_marker("e2e") is not None


def _playwright_status() -> tuple[bool, str]:
    import importlib.util

    missing = [name for name in ("playwright", "pytest_playwright") if importlib.util.find_spec(name) is None]
    if missing:
        return False, (
            "開発用依存（requirements-dev.txt）の " + "・".join(missing)
            + " が未導入のため、実ブラウザのテストを実行できません"
        )
    return True, ""


def _base_nodeid(item: pytest.Item) -> str:
    return item.nodeid.split("[", 1)[0]


def _select_preflight(config: pytest.Config, items: list[pytest.Item]) -> None:
    """--e2e-preflight: keep PREFLIGHT_TESTS (every parameter), nothing else."""
    run = state(config)
    selected = [item for item in items if is_e2e(item) and _base_nodeid(item) in PREFLIGHT_TESTS]
    keep = {id(item) for item in selected}
    found = {_base_nodeid(item) for item in selected}
    run.preflight_missing = [name for name in PREFLIGHT_TESTS if name not in found]
    others = [item for item in items if id(item) not in keep]
    if others:
        config.hook.pytest_deselected(items=others)
        items[:] = selected


def on_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run = state(config)
    if run.preflight:
        _select_preflight(config, items)
    available, reason = _playwright_status()
    run.playwright_available = available
    run.playwright_reason = reason
    if available:
        return
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if is_e2e(item):
            item.add_marker(marker)


def on_deselected(config: pytest.Config, items: list[pytest.Item]) -> None:
    run = state(config)
    if run.preflight:
        return  # the preflight leaves out the rest on purpose: not 未実施
    for item in items:
        if is_e2e(item):
            run.deselected[item.nodeid] = TestRecord(item.nodeid, _acceptance_ids(item))


def on_collection_finish(session: pytest.Session) -> None:
    run = state(session.config)
    for item in session.items:
        if is_e2e(item):
            run.records[item.nodeid] = TestRecord(item.nodeid, _acceptance_ids(item))
            run.deselected.pop(item.nodeid, None)


def _skip_reason(report: pytest.TestReport) -> str:
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2]).removeprefix("Skipped: ")
    return str(longrepr or "")


def _failure_reason(report: pytest.TestReport) -> str:
    text = getattr(report, "longreprtext", "") or str(report.longrepr or "")
    lines = [line for line in text.strip().splitlines() if line.strip()]
    # The error itself (pytest's "E   ..." lines) rather than only where it was raised.
    errors = [line[1:].strip() for line in lines if line.startswith("E ")]
    if errors:
        return " / ".join(errors[:3])[:300]
    return lines[-1][:300] if lines else ""


def on_report(item: pytest.Item, report: pytest.TestReport) -> None:
    run = state(item.config)
    record = run.records.get(item.nodeid)
    if record is None:
        return
    if report.skipped:
        reason = _skip_reason(report)
        if run.required or run.preflight:
            # Required run / preflight: a skipped browser test is not an acceptance.
            label = "必須E2E" if run.required else "準備確認"
            report.outcome = "failed"
            report.longrepr = f"[{label}] スキップは失敗として扱います：{reason}"
            record.outcome = "failed"
            record.reason = f"スキップ（{'必須' if run.required else '準備確認'}のため失敗）：{reason}"
        elif record.outcome != "failed":
            record.outcome = "skipped"
            record.reason = reason
    elif report.failed:
        record.outcome = "failed"
        record.reason = f"{report.when}: {_failure_reason(report)}"
    elif report.when == "call" and record.outcome is None:
        record.outcome = "passed"


def add_known_console(item: pytest.Item, watchers: list) -> None:
    """What the pages of a test let through as the known favicon 404, each
    console error once (PageWatcher.known holds one entry per message)."""
    run = state(item.config)
    for watcher in watchers:
        for index in sorted(watcher.known):
            run.known_console.append({"nodeid": item.nodeid, **watcher.known[index]})
        if watcher.cdp_error:
            run.cdp_unavailable.append(f"{item.nodeid}：{watcher.cdp_error}")


def add_evidence_folder(item: pytest.Item, folder) -> None:
    state(item.config).evidence.setdefault(item.nodeid, {})["folder"] = str(folder)


def add_failure_screenshot(item: pytest.Item, result: dict) -> None:
    state(item.config).evidence.setdefault(item.nodeid, {})["screenshot"] = result


def record_viewport(item: pytest.Item, **values) -> None:
    state(item.config).viewport_checks.setdefault(item.nodeid, {}).update(values)


def css_px(value) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


def viewport_counts(run: RunState) -> dict[str, int]:
    counts = {verdict: 0 for verdict in VIEWPORT_VERDICTS}
    for check in run.viewport_checks.values():
        if check.get("verdict") in counts:
            counts[check["verdict"]] += 1
    return counts


def _test_outcome(record: TestRecord) -> str:
    return record.outcome or "not_run"


def failure_evidence(run: RunState) -> list[dict]:
    """For each failed test: the files actually in its evidence folder now,
    and the page taken by the page fixture (or why there is none)."""
    found = []
    for record in run.records.values():
        if _test_outcome(record) != "failed":
            continue
        evidence = run.evidence.get(record.nodeid) or {}
        folder = evidence.get("folder")
        path = pathlib.Path(folder) if folder else None
        exists = path is not None and path.is_dir()
        files, error = [], ""
        try:  # the record is written whatever the folder holds
            if exists:
                files = [(p.name, p.stat().st_size) for p in sorted(path.iterdir(), key=lambda p: p.name) if p.is_file()]
        except OSError as problem:
            error = str(problem).strip().splitlines()[0][:200] if str(problem).strip() else type(problem).__name__
        found.append({
            "nodeid": record.nodeid,
            "folder": folder,
            "folder_exists": exists,
            "files": files,
            "error": error,
            "screenshot": evidence.get("screenshot"),
        })
    return found


def _owner(name: str) -> str:
    if name.startswith("trace") and name.endswith(".zip"):
        return "pytest-playwright の trace"
    if name.startswith("test-failed-") and name.endswith(".png"):
        return "pytest-playwright の画面"
    if name.endswith(".webm"):
        return "pytest-playwright の動画"
    return "この記録の画面" if name.endswith(".png") else "その他"


def summarize(run: RunState) -> None:
    all_records = list(run.records.values()) + list(run.deselected.values())
    id_results: dict[str, dict] = {}
    found_ids = {i for r in all_records for i in r.ids}
    if run.preflight:  # only the items the preflight ran
        known = [i for i in REQUIRED_IDS if i in found_ids] + sorted(found_ids - set(REQUIRED_IDS))
    else:
        known = list(REQUIRED_IDS) + sorted(found_ids - set(REQUIRED_IDS))
    for acceptance_id in known:
        related = [r for r in all_records if acceptance_id in r.ids]
        counts = {key: 0 for key in OUTCOME_LABELS}
        for record in related:
            counts[_test_outcome(record)] += 1
        if not related or counts["passed"] == 0 and counts["failed"] == 0 and counts["skipped"] == 0:
            status = "not_run"
        elif counts["failed"]:
            status = "failed"
        elif counts["skipped"] or counts["not_run"]:
            status = "skipped" if counts["skipped"] else "not_run"
        else:
            status = "passed"
        id_results[acceptance_id] = {
            "status": status,
            "counts": counts,
            "required": acceptance_id in REQUIRED_IDS,
            "description": REQUIRED_IDS.get(acceptance_id, ""),
        }
    run.id_results = id_results
    required_ok = all(v["status"] == "passed" for k, v in id_results.items() if v["required"])
    tests_ok = all(_test_outcome(r) == "passed" for r in run.records.values())
    if run.preflight:
        # At least one test, every one passed, every preflight test found.
        ok = bool(run.records) and tests_ok and not run.preflight_missing
        run.verdict = "成功" if ok else "失敗"
        return
    run.verdict = "合格" if required_ok and tests_ok and not run.deselected else "不合格"


def passed(run: RunState) -> bool:
    return run.verdict == ("成功" if run.preflight else "合格")


def on_session_finish(session: pytest.Session) -> None:
    run = state(session.config)
    run.finished = _dt.datetime.now().astimezone()
    run.duration_seconds = time.monotonic() - run.started_clock
    if not run.records and not run.deselected and not run.required and not run.preflight:
        return
    summarize(run)
    if (run.required or run.preflight) and not passed(run):
        # Keep a more specific failure (e.g. interrupted, usage error).
        if session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
    if run.report_path:
        path = pathlib.Path(run.report_path)
        if not path.is_absolute():
            path = pathlib.Path(session.config.invocation_params.dir) / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(session.config, run), encoding="utf-8")


def _git(*args: str) -> str:
    repo = pathlib.Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _count_tests(run: RunState) -> dict[str, int]:
    counts = {key: 0 for key in OUTCOME_LABELS}
    for record in run.records.values():
        counts[_test_outcome(record)] += 1
    counts["not_run"] += len(run.deselected)
    return counts


def _package_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:  # noqa: BLE001 - informational only
        return "未導入"


def _clock(moment: Optional[_dt.datetime]) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S %z") if moment else "-"


def _duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}分{rest:02d}秒"


def _cell(value) -> str:
    return " ".join(str(value).split()).replace("|", "／")


def _kind_of_run(run: RunState) -> str:
    if run.required:
        return "はい（スキップ・未実施は失敗）"
    if run.preflight:
        return "いいえ（準備確認：選んだ一部のテストだけ。スキップと0件は失敗。全必須 E2E の合格ではありません）"
    return "いいえ（通常の実行）"


def _verdict_text(run: RunState) -> str:
    if not run.preflight:
        return str(run.verdict)
    text = f"{run.verdict}（準備確認。全必須 E2E の合格ではありません）"
    if run.preflight_missing:
        text += "。見つからない準備確認のテスト：" + "、".join(f"`{name}`" for name in run.preflight_missing)
    return text


def _browser_rows(config: pytest.Config, run: RunState) -> list[str]:
    """What was asked for (channel, headed/headless) and what was started."""
    launch = run.launch or {}
    channel = config.getoption("browser_channel", default=None)
    started = launch.get("product") or (
        f"未起動（起動できませんでした：{_cell(launch['error'])}）" if launch.get("error") else "未起動")
    headed = launch.get("headless") is False or bool(config.getoption("headed", default=False))
    slowmo = config.getoption("slowmo", default=0) or 0
    return [
        f"| ブラウザの channel（指定） | {channel or 'なし（Playwright 同梱の Chromium）'} |",
        f"| 起動したブラウザ | {_cell(started)} |",
        f"| ブラウザの実行ファイル | {_cell(launch.get('executable') or '-')} |",
        f"| ブラウザのプロフィール | {_cell(launch.get('profile') or '-')} |",
        f"| 起動の設定 | {'headed（画面を表示）' if headed else 'headless'}、slowmo {f'{slowmo} ms（調査用）' if slowmo else 'なし'} |",
    ]


def _environment_rows(config: pytest.Config, run: RunState) -> list[str]:
    """The code-side .env, the test server and where failures leave evidence."""
    env_file = FTA_TOOL_DIR / ".env"
    if env_file.exists():
        env_text = (f"あり（{env_file}）。テスト用サーバーは読み込んだ後に AI の設定を e2e-stub に固定し、"
                    "実プロバイダと外部への通信を遮断する")
    else:
        env_text = f"なし（{env_file}）"
    server = run.server or {}
    server_text = ("AI: e2e-stub（tests/e2e/stub_server.py。実LLMの取得と外部への HTTP は遮断し、試みがあればテストを失敗にする）"
                   + (f"、{server['url']}、作業フォルダ（一時 DB）{server['workdir']}、ログ {server['log']}" if server else ""))
    output_path = _output_dir(config)
    if output_path is not None:
        evidence = (f"スクリーンショット {config.getoption('screenshot', default='off')}、"
                    f"trace {config.getoption('tracing', default='off')}、保存先 {output_path}"
                    "（設定です。実際に残ったファイルは下の「失敗したテストの証跡（実際にあるファイル）」）")
    else:
        evidence = "-"
    return [
        f"| コード側の .env | {_cell(env_text)} |",
        f"| テスト用サーバー | {_cell(server_text)} |",
        f"| 失敗時の証跡の設定（pytest-playwright） | {_cell(evidence)} |",
    ]


def _output_dir(config: pytest.Config) -> Optional[pathlib.Path]:
    output = config.getoption("output", default=None)
    if not output:
        return None
    path = pathlib.Path(output)
    return path if path.is_absolute() else pathlib.Path(config.invocation_params.dir) / path


def render_markdown(config: pytest.Config, run: RunState) -> str:
    sha = _git("rev-parse", "HEAD") or "取得できませんでした"
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "-"
    counts = _count_tests(run)
    args = shlex.join(["pytest", *config.invocation_params.args])
    browser = run.browser or {}
    lines = [
        "## 実ブラウザテスト（E2E）の記録",
        "",
    ]
    if run.preflight:
        lines += ["**準備確認の記録です（選んだ一部のテストだけを実行。全必須 E2E の合格ではありません）。**", ""]
    lines += [
        "| 項目 | 値 |",
        "|---|---|",
        f"| 実行日時（UTC） | {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} |",
        f"| 開始・終了（ローカル時刻） | {_clock(run.started)} 〜 {_clock(run.finished)}（所要 {_duration(run.duration_seconds)}） |",
        f"| 実行環境の区分 | {run.env_label} |",
        f"| OS | {platform.platform()} |",
        f"| Python | {platform.python_version()} |",
        f"| Playwright / pytest-playwright | {_package_version('playwright')} / {_package_version('pytest-playwright')} |",
        f"| ブラウザ | {browser.get('name', '未起動')} {browser.get('version', '')}（{browser.get('mode', '-')}） |",
        *_browser_rows(config, run),
        f"| 対象コミット | `{sha}`（{'追跡中のファイルに未コミットの変更あり' if dirty else '未コミットの変更なし'}） |",
        f"| ブランチ | `{branch}` |",
        f"| 実行コマンド | `{args}` |",
        f"| 必須受入検証として実行 | {_kind_of_run(run)} |",
        *_environment_rows(config, run),
        f"| 画面寸法（CSS ピクセル） | {'、'.join(run.viewports) or '-'} |",
        *_viewport_summary_rows(run),
        f"| 結果（テスト単位） | 成功 {counts['passed']}・失敗 {counts['failed']}・スキップ {counts['skipped']}・未実施 {counts['not_run']} |",
        f"| 既知の例外（favicon の 404） | {len(run.known_console)} 件（コンソールの確認から除いたもの。下の「既知の例外として除いたコンソールのエラー」） |",
        f"| 判定 | {_verdict_text(run)} |",
        "",
        "### 受入項目ごとの結果" + ("（準備確認で実行した項目だけ）" if run.preflight else ""),
        "",
        "| ID | 内容 | 結果 | 成功 | 失敗 | スキップ | 未実施 |",
        "|---|---|---|---|---|---|---|",
    ]
    for acceptance_id, result in run.id_results.items():
        c = result["counts"]
        lines.append(
            f"| {acceptance_id} | {result['description'] or '（必須外）'} | {OUTCOME_LABELS[result['status']]} "
            f"| {c['passed']} | {c['failed']} | {c['skipped']} | {c['not_run']} |"
        )
    lines += ["", "### テストごとの結果", "", "| テスト | 結果 | 備考 |", "|---|---|---|"]
    for record in list(run.records.values()) + list(run.deselected.values()):
        reason = record.reason.replace("|", "／").replace("\n", " ")
        lines.append(f"| `{record.nodeid}` | {OUTCOME_LABELS[_test_outcome(record)]} | {reason} |")
    lines += ["", *_evidence_lines(config, run)]
    if run.viewport_checks:
        lines += ["", *_viewport_lines(run)]
    lines += ["", *_known_console_lines(run)]
    if not run.playwright_available:
        lines += ["", f"注：{run.playwright_reason}"]
    lines.append("")
    return "\n".join(lines)


def _evidence_lines(config: pytest.Config, run: RunState) -> list[str]:
    lines = [
        "### 失敗したテストの証跡（実際にあるファイル）",
        "",
        "「失敗時の証跡の設定」は、pytest-playwright に残させるものの設定で、ファイルが残ったことは示しません。"
        "ここには、この記録を書いた時点で各テストの保存先に実際にあったファイルを書きます。"
        "失敗したテストでは、この記録もページの終了処理の初めに画面を撮ります（page-at-failure.png。"
        "撮れなかったときは理由を書きます。pytest-playwright の画面 test-failed-1.png は、撮れなかったときに理由を残しません）。",
        "",
    ]
    evidence = failure_evidence(run)
    if not evidence:
        return lines + ["失敗したテストはありません。"]
    output = _output_dir(config)
    lines += ["| テスト | 保存先 | 実際にあるファイル | この記録の画面 |", "|---|---|---|---|"]
    for item in evidence:
        if not item["folder"]:
            lines.append(f"| `{item['nodeid']}` | - | 保存先なし（pytest-playwright の画面・trace の対象外："
                         "自分でブラウザを開くテストか、ページを作る前に失敗した） | - |")
            continue
        folder = pathlib.Path(item["folder"])
        if output is not None and folder.is_relative_to(output):
            folder = folder.relative_to(output)
        if not item["folder_exists"]:
            files = "なし（保存先のフォルダがない）"
        elif item["error"]:
            files = f"読めなかった（{item['error']}）"
        else:
            files = "、".join(f"{name}（{size} バイト、{_owner(name)}）" for name, size in item["files"]) or "なし"
        shot = item["screenshot"]
        if shot is None:
            shot_text = "撮っていない（ページの終了処理まで進まなかった）"
        elif shot.get("file"):
            shot_text = f"{shot['file']}（{shot.get('bytes')} バイト）"
        else:
            shot_text = f"保存できなかった：{shot.get('reason')}"
        lines.append(f"| `{item['nodeid']}` | {_cell(folder)} | {_cell(files)} | {_cell(shot_text)} |")
    return lines


def _viewport_summary_rows(run: RunState) -> list[str]:
    if not run.viewport_checks:
        return []
    counts = viewport_counts(run)
    undecided = len(run.viewport_checks) - sum(counts.values())
    text = "・".join(f"{verdict} {count}" for verdict, count in counts.items())
    if undecided:
        text += f"・判定前に終了 {undecided}"
    return [f"| 画面寸法の要求と実測（PR3-LAYOUT） | {text}（下の「画面寸法の要求と実測（PR3-LAYOUT）」） |"]


def _measured(values: Optional[dict]) -> str:
    if not values:
        return "測っていない"
    client, inner, scroll = values.get("client"), values.get("inner"), values.get("scroll")
    visual = values.get("visualViewport")
    parts = [f"client {client[0]}×{client[1]}"]
    if inner:
        parts.append(f"inner {inner[0]}×{inner[1]}")
    if visual:
        parts.append(f"visualViewport {css_px(visual[0])}×{css_px(visual[1])}（scale {css_px(visual[2])}）")
    else:
        parts.append("visualViewport なし")
    parts.append(f"devicePixelRatio {values.get('devicePixelRatio')!r}")
    if scroll:
        parts.append(f"scroll {scroll[0]}×{scroll[1]}")
    return "、".join(parts)


def _viewport_lines(run: RunState) -> list[str]:
    allowed = "、".join(f"{case}（各軸 +{px} CSS px まで）" for case, px in VIEWPORT_ALLOWED.items())
    lines = [
        "### 画面寸法の要求と実測（PR3-LAYOUT）",
        "",
        "要求した表示領域（Playwright の viewport、CSS ピクセル）と、ブラウザで測った値です。アプリの表示前（about:blank）と、"
        "編集画面の表示後に測ります。client は `document.documentElement.clientWidth`×`clientHeight`（整数。利用者の PC で測った量）、"
        "visualViewport は小数の値です。",
        "",
        f"差を許容するのは {allowed}だけです（検証条件の限定変更。2026-10-06 の利用者の指示）。実測が要求と同じか各軸 +1 CSS ピクセルまで大きく、"
        "その差がアプリの表示前からあって表示後も同じで、要求と実測の間（両端を含む）にレイアウトの境界（1280px、ペインの幅の変化が止まる幅など。"
        "`tests/e2e/support.py` の LAYOUT_BOUNDARIES）がない場合に限ります。そのときも、ページ全体の横スクロール、ペインの収まり、"
        "主要な操作の表示と被覆の検査は、実測の寸法を基準に最後まで行います。ほかのケース（1280×800 と edge-1912x914）は一致が必要です。",
        "",
        "| テスト | 要求 | 表示前（about:blank） | 表示後（編集画面） | 判定 |",
        "|---|---|---|---|---|",
    ]
    for nodeid, check in run.viewport_checks.items():
        requested = check.get("requested")
        asked = f"{requested[0]}×{requested[1]}" if requested else "-"
        if check.get("allowed"):
            asked += f"（差の許容 +{check['allowed']}）"
        verdict = check.get("verdict")
        if verdict is None:
            judged = "判定前に終了（編集画面の表示か測定の前に失敗）"
        elif verdict == VIEWPORT_EXACT:
            judged = verdict
        else:
            size = check.get("size")
            judged = f"{verdict}：{check.get('reason', '')}"
            if verdict == VIEWPORT_TOLERATED and size:
                judged += f"。後続の検査は {size[0]}×{size[1]} を基準に実施"
        lines.append(f"| `{nodeid}` | {asked} | {_cell(_measured(check.get('before')))} "
                     f"| {_cell(_measured(check.get('after')))} | {_cell(judged)} |")
    return lines


def _known_console_lines(run: RunState) -> list[str]:
    lines = [
        "### 既知の例外として除いたコンソールのエラー（favicon の 404）",
        "",
        "既知事項に対する検証条件の限定変更です（2026-10-03 の利用者の判断）。favicon の不具合を直したものではありません"
        "（favicon の実装とこの除外の廃止は PR-7）。",
        "",
        "除くのは、テストのサーバーと同じオリジンの `/favicon.ico`（クエリ・別のパス・別のオリジンは対象外）に対するブラウザ自身の要求"
        "（CDP の種類 Other）の 404 で、コンソールの文・発生元の URL・ブラウザの記録（CDP の Log と応答）が1件ずつ一致するものだけです。"
        "ほかの 404、500、通信の失敗、発生元の分からないエラーは失敗のままです。",
        "",
        f"件数：{len(run.known_console)}",
    ]
    if run.known_console:
        lines += ["", "| テスト | 発生元の URL | 元のメッセージ | 応答（CDP） |", "|---|---|---|---|"]
        for event in run.known_console:
            lines.append(f"| `{event['nodeid']}` | `{event['url']}` | {_cell(event['text'])} "
                         f"| {event['status']}、種類 {event['type']}（要求 {event['request_id']}） |")
    if run.cdp_unavailable:
        lines += ["", f"注：ブラウザの記録（CDP）を読めなかったページが {len(run.cdp_unavailable)} 件あります"
                      "（そのページでは何も除いていません）：" + "、".join(_cell(t) for t in run.cdp_unavailable)]
    return lines


def terminal_summary(terminalreporter, config: pytest.Config) -> None:
    run = config.stash.get(STATE_KEY, None)
    if run is None or run.verdict is None:
        return
    tr = terminalreporter
    counts = _count_tests(run)
    tr.section("実ブラウザテスト（E2E）の受入記録")
    kind = "準備確認（全必須 E2E の合格ではありません）" if run.preflight else ("はい" if run.required else "いいえ")
    tr.line(
        f"必須受入検証: {kind} / 判定: {run.verdict} / "
        f"成功 {counts['passed']}・失敗 {counts['failed']}・スキップ {counts['skipped']}・未実施 {counts['not_run']}"
    )
    browser = run.browser or {}
    if browser:
        tr.line(f"ブラウザ: {browser.get('name')} {browser.get('version')}（{browser.get('mode')}） 画面寸法: {'、'.join(run.viewports)}")
    launch = run.launch or {}
    channel = config.getoption("browser_channel", default=None)
    if channel or launch.get("error"):
        tr.line(f"channel: {channel or 'なし'} / 起動したブラウザ: {launch.get('product') or '未起動'}"
                + (f"（{launch['error']}）" if launch.get("error") else ""))
    if run.preflight_missing:
        tr.line("見つからない準備確認のテスト: " + "、".join(run.preflight_missing), red=True)
    tr.line(f"既知の例外（favicon の 404。コンソールの確認から除いたもの）: {len(run.known_console)} 件")
    if run.viewport_checks:
        counts = viewport_counts(run)
        tr.line("画面寸法の要求と実測（PR3-LAYOUT）: " + "・".join(f"{v} {n} 件" for v, n in counts.items())
                + "".join(f"（{nodeid.rsplit('[', 1)[-1].rstrip(']')}：要求 {c['requested'][0]}×{c['requested'][1]}"
                          f" → 実測 {c['size'][0]}×{c['size'][1]}）"
                          for nodeid, c in run.viewport_checks.items()
                          if c.get("verdict") in (VIEWPORT_TOLERATED, VIEWPORT_REFUSED) and c.get("size")))
    evidence = failure_evidence(run)
    if evidence:
        traces = sum(1 for e in evidence if any(_owner(n) == "pytest-playwright の trace" for n, _ in e["files"]))
        pictures = sum(1 for e in evidence if any(n.endswith(".png") for n, _ in e["files"]))
        missing = sum(1 for e in evidence if e["screenshot"] is not None and not e["screenshot"].get("file"))
        tr.line(f"失敗したテストの証跡（実際にあるファイル）: {len(evidence)} 件中、trace あり {traces} 件・画面あり {pictures} 件"
                + (f"（画面を撮れなかったもの {missing} 件。理由は e2e-report.md）" if missing else ""))
    for acceptance_id, result in run.id_results.items():
        c = result["counts"]
        tr.line(
            f"  {acceptance_id:<17} {OUTCOME_LABELS[result['status']]:<5} "
            f"(成功{c['passed']} 失敗{c['failed']} スキップ{c['skipped']} 未実施{c['not_run']})"
        )
    if not run.playwright_available:
        tr.line(f"注: {run.playwright_reason}")
    if run.required and run.verdict != "合格":
        tr.line("必須受入検証は不合格です（スキップ・未実施・失敗を含むため）。", red=True, bold=True)
    if run.preflight:
        if run.verdict == "成功":
            tr.line("準備確認は成功しました。全必須 E2E の合格ではありません（次に必須受入検証を実行します）。", bold=True)
        else:
            tr.line("準備確認は失敗しました（失敗・スキップ・0件・見つからないテストのいずれかを含むため）。", red=True, bold=True)

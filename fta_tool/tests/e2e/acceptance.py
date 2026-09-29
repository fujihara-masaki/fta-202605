"""Required acceptance run for the real-browser tests (plan 5.9.6, J-26).

Two ways to run the browser tests:

* ``pytest`` (normal): E2E tests run when Playwright and Chromium are
  installed and are skipped otherwise, so ordinary development is not
  blocked.
* ``pytest -m e2e --e2e-required`` (or ``FTA_E2E_REQUIRED=1``): the required
  acceptance run of the UI redesign. A skipped E2E test is reported as a
  failure, and every acceptance ID in REQUIRED_IDS must have run and passed;
  an ID whose tests did not run ("未実施") fails the session as well.

Each result is recorded as 成功 / 失敗 / スキップ / 未実施, together with the
environment, the commit, the browser and the viewports (``--e2e-report``
writes it as Markdown for the pull request).

This module is imported by tests/conftest.py and must not import Playwright.
"""

from __future__ import annotations

import datetime as _dt
import os
import pathlib
import platform
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Optional

import pytest

REQUIRED_ENV = "FTA_E2E_REQUIRED"
ENV_LABEL_ENV = "FTA_E2E_ENV"

# Acceptance IDs that the required run must cover. Later PRs append theirs.
# E-xx / T-xx follow plan section 8.9; PR1-xx / PR2-xx / PR3-xx are checks
# added in PR-1 / PR-2 / PR-3 for the shared foundation, the parts that still
# run on the old processing, and conditions (or the user's decisions) that
# have no E-xx. PR1-COMPAT-NEW (the new analysis form before its migration)
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
    "E-E03": "編集：評価の保存と全表示への反映（ツリーを含む）、失敗時、連続クリック",
    "E-E04": "編集：絞り込み（作業リスト・一覧表は非表示、構造ナビ・ツリーは強調）、件数、生成対象が変わらない",
    "E-E05": "編集：表示タブのキー操作、選択の保持",
    "E-E06": "編集：再読み込み後の復元（選択・ステップ・タブ・スクロール・絞り込み）、不正なハッシュ、保存領域なし",
    "E-E07": "編集：部分更新の後もフォーカス・スクロール・入力中の値が残る、分析が削除されていた場合、取得の失敗、生成中は取得しない",
    "E-E09": "編集：demo_points を表示しない、マークアップを含む要因の文字列がそのまま文字として出る",
    "E-E19": "編集：部分更新の古い応答で表示が巻き戻らない（評価の書き込みの前に発行した取得・確定済みの評価と食い違う応答）",
    "PR3-LEGACY-OPS": "編集：暫定の旧処理（タイトル・①の保存、生成、詳細編集、手動追加、削除、出力、一覧へ）が新しい画面から再読み込みなしで使える",
}

OUTCOME_LABELS = {
    "passed": "成功",
    "failed": "失敗",
    "skipped": "スキップ",
    "not_run": "未実施",
}


@dataclass
class TestRecord:
    nodeid: str
    ids: list[str]
    outcome: Optional[str] = None  # passed / failed / skipped / None (= not run)
    reason: str = ""


@dataclass
class RunState:
    required: bool = False
    report_path: Optional[str] = None
    env_label: str = "未指定"
    records: dict[str, TestRecord] = field(default_factory=dict)
    deselected: dict[str, TestRecord] = field(default_factory=dict)
    playwright_available: bool = True
    playwright_reason: str = ""
    browser: dict[str, str] = field(default_factory=dict)
    viewports: list[str] = field(default_factory=list)
    id_results: dict[str, dict] = field(default_factory=dict)
    verdict: Optional[str] = None


STATE_KEY = pytest.StashKey[RunState]()


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def state(config: pytest.Config) -> RunState:
    return config.stash[STATE_KEY]


def configure(config: pytest.Config) -> None:
    required = bool(config.getoption("e2e_required", default=False)) or _truthy(os.environ.get(REQUIRED_ENV))
    env_label = config.getoption("e2e_env", default=None) or os.environ.get(ENV_LABEL_ENV) or "未指定"
    config.stash[STATE_KEY] = RunState(
        required=required,
        report_path=config.getoption("e2e_report", default=None),
        env_label=env_label,
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


def on_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run = state(config)
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
    return lines[-1][:300] if lines else ""


def on_report(item: pytest.Item, report: pytest.TestReport) -> None:
    run = state(item.config)
    record = run.records.get(item.nodeid)
    if record is None:
        return
    if report.skipped:
        reason = _skip_reason(report)
        if run.required:
            # Required run: a skipped browser test is not an acceptance.
            report.outcome = "failed"
            report.longrepr = f"[必須E2E] スキップは失敗として扱います：{reason}"
            record.outcome = "failed"
            record.reason = f"スキップ（必須のため失敗）：{reason}"
        elif record.outcome != "failed":
            record.outcome = "skipped"
            record.reason = reason
    elif report.failed:
        record.outcome = "failed"
        record.reason = f"{report.when}: {_failure_reason(report)}"
    elif report.when == "call" and record.outcome is None:
        record.outcome = "passed"


def _test_outcome(record: TestRecord) -> str:
    return record.outcome or "not_run"


def summarize(run: RunState) -> None:
    all_records = list(run.records.values()) + list(run.deselected.values())
    id_results: dict[str, dict] = {}
    known = list(REQUIRED_IDS) + sorted(
        {i for r in all_records for i in r.ids if i not in REQUIRED_IDS}
    )
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
    run.verdict = "合格" if required_ok and tests_ok and not run.deselected else "不合格"


def on_session_finish(session: pytest.Session) -> None:
    run = state(session.config)
    if not run.records and not run.deselected and not run.required:
        return
    summarize(run)
    if run.required and run.verdict != "合格":
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
        "| 項目 | 値 |",
        "|---|---|",
        f"| 実行日時（UTC） | {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} |",
        f"| 実行環境の区分 | {run.env_label} |",
        f"| OS | {platform.platform()} |",
        f"| Python | {platform.python_version()} |",
        f"| Playwright / pytest-playwright | {_package_version('playwright')} / {_package_version('pytest-playwright')} |",
        f"| ブラウザ | {browser.get('name', '未起動')} {browser.get('version', '')}（{browser.get('mode', '-')}） |",
        f"| 対象コミット | `{sha}`（{'追跡中のファイルに未コミットの変更あり' if dirty else '未コミットの変更なし'}） |",
        f"| ブランチ | `{branch}` |",
        f"| 実行コマンド | `{args}` |",
        f"| 必須受入検証として実行 | {'はい（スキップ・未実施は失敗）' if run.required else 'いいえ（通常の実行）'} |",
        f"| 画面寸法（CSS ピクセル） | {'、'.join(run.viewports) or '-'} |",
        f"| 結果（テスト単位） | 成功 {counts['passed']}・失敗 {counts['failed']}・スキップ {counts['skipped']}・未実施 {counts['not_run']} |",
        f"| 判定 | {run.verdict} |",
        "",
        "### 受入項目ごとの結果",
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
    if not run.playwright_available:
        lines += ["", f"注：{run.playwright_reason}"]
    lines.append("")
    return "\n".join(lines)


def terminal_summary(terminalreporter, config: pytest.Config) -> None:
    run = config.stash.get(STATE_KEY, None)
    if run is None or run.verdict is None:
        return
    tr = terminalreporter
    counts = _count_tests(run)
    tr.section("実ブラウザテスト（E2E）の受入記録")
    tr.line(
        f"必須受入検証: {'はい' if run.required else 'いいえ'} / 判定: {run.verdict} / "
        f"成功 {counts['passed']}・失敗 {counts['failed']}・スキップ {counts['skipped']}・未実施 {counts['not_run']}"
    )
    browser = run.browser or {}
    if browser:
        tr.line(f"ブラウザ: {browser.get('name')} {browser.get('version')}（{browser.get('mode')}） 画面寸法: {'、'.join(run.viewports)}")
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

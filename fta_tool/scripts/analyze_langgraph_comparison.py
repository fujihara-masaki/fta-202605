#!/usr/bin/env python3
"""LangGraph / Quality Gate 比較試験ログの解析スクリプト。

``scripts/run_langgraph_comparison.ps1`` が保存した試験ディレクトリ
（サーバーログ・generate API レスポンス・エクスポートファイル・
runs_index.csv）を読み込み、次の 3 ファイルを生成する。

  - ``analysis/runs.csv``            実行×リクエスト単位の集計（Excel向け UTF-8 BOM）
  - ``analysis/factor_quality.csv``  候補・保存要因単位の品質情報（人手評価列付き）
  - ``analysis/summary.md``          設定別の比較サマリ

設計方針:
  - 実 Ollama / 実サーバーには一切アクセスしない（ファイル解析のみ）。
  - 古いログ・欠損ファイルがあっても例外終了しない。読めなかった項目は
    空欄にし、``summary.md`` の「解析ノート」に記録する。
  - 生成アルゴリズム・品質判定には触れない（ログの読み取り専用）。

補助モード（PowerShell スクリプトから利用）:
  - ``--list-scenarios``        config/sample_scenarios.yaml のシナリオID一覧を表示
  - ``--dump-scenario ID``      シナリオ1件を JSON で標準出力へ出す

使用例::

    python scripts/analyze_langgraph_comparison.py comparison_results/trial_20260712
    python scripts/analyze_langgraph_comparison.py --dump-scenario internet_web_access_failure
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import pathlib
import re
import statistics
import sys
from collections import Counter, defaultdict
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 共通ヘルパ
# ---------------------------------------------------------------------------

# key=value 抽出（value は 'quoted' / "quoted" / 空白なしトークン）
_KV_RE = re.compile(r"(\w+)=('(?:[^']*)'|\"(?:[^\"]*)\"|\S+)")

# elapsed=1234ms 形式
_ELAPSED_MS_RE = re.compile(r"elapsed=(\d+)ms")

_TRUTHY = {"1", "true", "yes", "on"}


def parse_kv_line(line: str) -> dict[str, str]:
    """grep しやすい ``key=value`` ログ行を辞書にする（失敗しても空辞書）。"""
    out: dict[str, str] = {}
    try:
        for key, raw in _KV_RE.findall(line):
            value = raw
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            out[key] = value
    except Exception:
        pass
    return out


def to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text in _TRUTHY


def ns_to_ms(value: Any) -> Optional[float]:
    """Ollama のナノ秒メトリクスをミリ秒へ（欠損は None のまま）。"""
    number = to_float(value)
    if number is None:
        return None
    return number / 1_000_000.0


# 警告文の可変部分（「タイトル」・（35文字）等）を落として理由ラベルへ正規化
_VARIABLE_PART_RE = re.compile(r"「[^」]*」|（[^）]*）|\([^)]*\)|:.*$|：.*$")


def normalize_reason(reason: str) -> str:
    """警告・除外理由の文字列を集計用ラベルに正規化する。"""
    text = (reason or "").strip()
    if not text:
        return ""
    text = _VARIABLE_PART_RE.sub("", text).strip()
    return text or (reason or "").strip()


def split_reasons(joined: str) -> list[str]:
    """``"理由A; 理由B"`` 形式を理由ラベルのリストへ。"""
    if not joined:
        return []
    return [normalize_reason(p) for p in joined.split(";") if p.strip()]


def read_text_tolerant(path: pathlib.Path) -> str:
    """BOM・エンコーディング・改行差を許容してテキストを読む（失敗は空文字）。"""
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_json_tolerant(path: pathlib.Path) -> Optional[Any]:
    text = read_text_tolerant(path)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def fmt(value: Any, digits: int = 1) -> str:
    """summary.md 用の数値フォーマット（None は「-」）。"""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "-"
        return f"{value:.{digits}f}"
    return str(value)


def mean_or_none(values: list[float]) -> Optional[float]:
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def median_or_none(values: list[float]) -> Optional[float]:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def stdev_or_none(values: list[float]) -> Optional[float]:
    values = [v for v in values if v is not None]
    return statistics.stdev(values) if len(values) >= 2 else None


# ---------------------------------------------------------------------------
# シナリオ補助モード（PowerShell から利用）
# ---------------------------------------------------------------------------

def _default_scenario_file() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "config" / "sample_scenarios.yaml"


def load_scenarios(scenario_file: Optional[str] = None) -> list[dict]:
    import yaml  # requirements.txt に含まれる（アプリ本体と同じ依存）

    path = pathlib.Path(scenario_file) if scenario_file else _default_scenario_file()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    scenarios = data.get("scenarios") or []
    return [s for s in scenarios if isinstance(s, dict) and s.get("id")]


def cmd_list_scenarios(scenario_file: Optional[str]) -> int:
    for scenario in load_scenarios(scenario_file):
        print(f"{scenario['id']}\t{scenario.get('title', '')}")
    return 0


def cmd_dump_scenario(scenario_id: str, scenario_file: Optional[str]) -> int:
    for scenario in load_scenarios(scenario_file):
        if scenario["id"] == scenario_id:
            print(json.dumps(scenario, ensure_ascii=False))
            return 0
    print(f"scenario not found: {scenario_id}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# 1実行（run）分の解析
# ---------------------------------------------------------------------------

class RunData:
    """1 回の実行（サーバー起動〜エクスポートまで）のログ解析結果。"""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.config = ""
        self.langgraph: Optional[bool] = None
        self.quality_gate: Optional[bool] = None
        self.phase = ""              # warmup / measured
        self.iteration: Optional[int] = None
        self.order_index: Optional[int] = None
        self.scenario_id = ""
        self.status = ""
        self.start_time = ""
        self.end_time = ""
        self.notes: list[str] = []

        # generate リクエスト単位（`generate_factors workflow |` 行 ≒ 階層単位）
        self.requests: list[dict] = []
        # 親要因単位の処理時間（`generate_factors summary |` 行）
        self.parent_timings: list[dict] = []
        # Ollama 推論メトリクス（`generation_metrics | {json}` 行）
        self.ollama_metrics: list[dict] = []
        # LangGraph 実行サマリ（`langgraph run summary |` 行）
        self.workflow_summaries: list[dict] = []
        # decide 行の decision 内訳（regenerate 等の途中判定を含む）
        self.decide_counts: Counter = Counter()
        # 候補単位の品質行（factor_quality.csv の素材）
        self.candidates: list[dict] = []
        # 理由ラベル別件数
        self.warning_reasons: Counter = Counter()
        self.critical_reasons: Counter = Counter()
        # generate API レスポンス（gen_level*.json）
        self.responses: list[dict] = []
        # エクスポートCSVの保存済み要因
        self.exported_factors: list[dict] = []

    # --- 集計プロパティ -----------------------------------------------------

    def request_value_sum(self, key: str) -> Optional[int]:
        values = [r.get(key) for r in self.requests if r.get(key) is not None]
        return sum(values) if values else None

    @property
    def total_elapsed_ms(self) -> Optional[int]:
        return self.request_value_sum("elapsed_ms")

    def ollama_sum(self, key: str) -> Optional[float]:
        values = [m.get(key) for m in self.ollama_metrics if m.get(key) is not None]
        return sum(values) if values else None

    @property
    def final_decisions(self) -> Counter:
        counter: Counter = Counter()
        for request in self.requests:
            for decision in request.get("decisions") or []:
                counter[decision] += 1
        return counter

    @property
    def retry_total(self) -> Optional[int]:
        return self.request_value_sum("retries")

    @property
    def avg_quality_score(self) -> Optional[float]:
        """レスポンス quality_summary.average_overall_score の平均（0-100）。"""
        return mean_or_none([
            to_float((r.get("quality_summary") or {}).get("average_overall_score"))
            for r in self.responses
        ])

    @property
    def workflow_quality_score(self) -> Optional[float]:
        """LangGraph run summary の quality_score 平均（0-1）。"""
        return mean_or_none([s.get("quality_score") for s in self.workflow_summaries])


def parse_server_log(text: str, run: RunData) -> None:
    """サーバーログ 1 ファイル分を RunData に取り込む（行単位・例外安全）。"""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            _parse_log_line(line, run)
        except Exception as e:  # 1行の異常で解析全体を止めない
            run.notes.append(f"ログ行の解析に失敗: {e}: {line[:120]}")


def _parse_log_line(line: str, run: RunData) -> None:
    if "generate_factors workflow |" in line:
        kv = parse_kv_line(line.split("generate_factors workflow |", 1)[1])
        decisions_raw = kv.get("decisions", "-")
        run.requests.append({
            "level": to_int(kv.get("level")),
            "langgraph": to_bool(kv.get("langgraph")),
            "quality_gate": to_bool(kv.get("quality_gate")),
            "mode": kv.get("mode", ""),
            "decisions": (
                [d for d in decisions_raw.split(",") if d and d != "-"]
                if decisions_raw else []
            ),
            "regenerated": to_bool(kv.get("regenerated")),
            "retries": to_int(kv.get("retries")),
            "rejected_by_gate": to_int(kv.get("rejected_by_gate")),
            "regenerated_created": to_int(kv.get("regenerated_created")),
            "outcome": kv.get("outcome", ""),
            "created": to_int(kv.get("created")),
            "elapsed_ms": to_int(kv.get("elapsed_ms")),
        })
        if run.langgraph is None:
            run.langgraph = to_bool(kv.get("langgraph"))
        if run.quality_gate is None:
            run.quality_gate = to_bool(kv.get("quality_gate"))

    elif "generate_factors summary |" in line:
        kv = parse_kv_line(line.split("generate_factors summary |", 1)[1])
        elapsed_match = _ELAPSED_MS_RE.search(line)
        run.parent_timings.append({
            "level": to_int(kv.get("level")),
            "parent": kv.get("parent", ""),
            "ai_returned": to_int(kv.get("ai_returned")),
            "created": to_int(kv.get("created")),
            "excluded_quality": to_int(kv.get("excluded_quality")),
            "skipped_dedup": to_int(kv.get("skipped_dedup")),
            "elapsed_ms": to_int(elapsed_match.group(1)) if elapsed_match else None,
        })

    elif "generation_metrics | " in line:
        payload = line.split("generation_metrics | ", 1)[1].strip()
        try:
            data = json.loads(payload)
        except ValueError:
            run.notes.append("generation_metrics 行の JSON 解析に失敗")
            return
        run.ollama_metrics.append({
            "level": to_int(data.get("level")),
            "model_name": data.get("model_name", ""),
            "success": bool(data.get("success")),
            "retries": to_int(data.get("retries"), 0),
            "elapsed_ms": to_float(data.get("elapsed_ms")),
            "total_duration_ms": ns_to_ms(data.get("total_duration")),
            "load_duration_ms": ns_to_ms(data.get("load_duration")),
            "prompt_eval_duration_ms": ns_to_ms(data.get("prompt_eval_duration")),
            "eval_duration_ms": ns_to_ms(data.get("eval_duration")),
            "prompt_eval_count": to_int(data.get("prompt_eval_count")),
            "eval_count": to_int(data.get("eval_count")),
        })

    elif "langgraph run summary |" in line:
        kv = parse_kv_line(line.split("langgraph run summary |", 1)[1])
        node_ms: dict[str, int] = {}
        for part in (kv.get("node_ms") or "").split(","):
            if ":" in part:
                name, _, ms = part.rpartition(":")
                value = to_int(ms)
                if name and value is not None:
                    node_ms[name] = node_ms.get(name, 0) + value
        run.workflow_summaries.append({
            "level": to_int(kv.get("level")),
            "parent_id": kv.get("parent_id", ""),
            "decision": kv.get("decision", ""),
            "severity": kv.get("severity", ""),
            "outcome": kv.get("outcome", ""),
            "quality_score": to_float(kv.get("quality_score")),
            "warnings": to_int(kv.get("warnings")),
            "regenerated": to_bool(kv.get("regenerated")),
            "retry_count": to_int(kv.get("retry_count")),
            "rejected": to_int(kv.get("rejected")),
            "elapsed_ms": to_int(kv.get("elapsed_ms")),
            "node_ms": node_ms,
        })

    elif "langgraph decide |" in line:
        kv = parse_kv_line(line.split("langgraph decide |", 1)[1])
        decision = kv.get("decision", "")
        if decision:
            run.decide_counts[decision] += 1

    elif "langgraph reject candidate |" in line:
        kv = parse_kv_line(line.split("langgraph reject candidate |", 1)[1])
        reasons = split_reasons(kv.get("reasons", ""))
        for reason in reasons:
            run.critical_reasons[reason] += 1
        run.candidates.append({
            "source": "gate_reject",
            "level": to_int(kv.get("level")),
            "parent": kv.get("parent", ""),
            "attempt": to_int(kv.get("attempt")),
            "title": kv.get("title", ""),
            "score": None,
            "severity": "critical",
            "excluded": True,
            "saved": False,
            "warnings": "",
            "critical_reasons": "; ".join(reasons),
        })

    elif "langgraph candidate |" in line:
        kv = parse_kv_line(line.split("langgraph candidate |", 1)[1])
        warnings = split_reasons(kv.get("warnings", ""))
        criticals = split_reasons(kv.get("critical_reasons", ""))
        for reason in warnings:
            run.warning_reasons[reason] += 1
        for reason in criticals:
            run.critical_reasons[reason] += 1
        excluded = to_bool(kv.get("excluded"))
        run.candidates.append({
            "source": "langgraph_candidate",
            "level": to_int(kv.get("level")),
            "parent": kv.get("parent", ""),
            "attempt": to_int(kv.get("attempt")),
            "title": kv.get("title", ""),
            "score": to_int(kv.get("score")),
            "severity": kv.get("severity", ""),
            "excluded": excluded,
            "saved": None,  # 保存可否はエクスポートCSVと突き合わせて確定
            "warnings": "; ".join(warnings),
            "critical_reasons": "; ".join(criticals),
        })

    elif "quality exclude |" in line:
        kv = parse_kv_line(line.split("quality exclude |", 1)[1])
        reason = normalize_reason(kv.get("reason", ""))
        if reason:
            run.critical_reasons[reason] += 1
        run.candidates.append({
            "source": "legacy_exclude",
            "level": to_int(kv.get("level")),
            "parent": kv.get("parent", ""),
            "attempt": None,
            "title": kv.get("title", ""),
            "score": to_int(kv.get("score")),
            "severity": "",
            "excluded": True,
            "saved": False,
            "warnings": "",
            "critical_reasons": reason,
        })

    elif "quality warning |" in line:
        kv = parse_kv_line(line.split("quality warning |", 1)[1])
        warnings = split_reasons(kv.get("warnings", ""))
        for reason in warnings:
            run.warning_reasons[reason] += 1
        run.candidates.append({
            "source": "legacy_warning",
            "level": to_int(kv.get("level")),
            "parent": kv.get("parent", ""),
            "attempt": None,
            "title": kv.get("title", ""),
            "score": to_int(kv.get("score")),
            "severity": "warning",
            "excluded": False,
            "saved": True,
            "warnings": "; ".join(warnings),
            "critical_reasons": "",
        })

    elif "dedup skip |" in line:
        kv = parse_kv_line(line.split("dedup skip |", 1)[1])
        run.candidates.append({
            "source": "dedup_skip",
            "level": to_int(kv.get("level")),
            "parent": kv.get("parent", ""),
            "attempt": None,
            "title": kv.get("title", ""),
            "score": None,
            "severity": "",
            "excluded": True,
            "saved": False,
            "warnings": "",
            "critical_reasons": "既存要因との重複・類似",
        })


_LEVEL_LABELS = {"頂上事象": 0, "一次要因": 1, "二次要因": 2, "三次要因": 3}


def parse_export_csv(text: str, run: RunData) -> None:
    """エクスポート CSV から保存済み要因の品質列を取り込む。"""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return
    index = {name: i for i, name in enumerate(header)}

    def cell(row: list[str], name: str) -> str:
        i = index.get(name)
        return row[i] if i is not None and i < len(row) else ""

    for row in reader:
        if not row:
            continue
        level_label = cell(row, "レベル")
        run.exported_factors.append({
            "source": "export",
            "level": _LEVEL_LABELS.get(level_label, to_int(level_label)),
            "parent": cell(row, "親要因"),
            "title": cell(row, "タイトル"),
            "warnings": cell(row, "警告理由"),
            "quality_status": cell(row, "品質ステータス"),
            "user_judgement": cell(row, "ユーザ評価"),
            "saved": True,
        })


def load_run(run_dir: pathlib.Path, index_row: Optional[dict] = None) -> RunData:
    """1 実行分のディレクトリを読み込む（存在しないファイルは黙って許容）。"""
    run = RunData(run_dir.name)

    meta = load_json_tolerant(run_dir / "run_meta.json") or {}
    merged: dict[str, Any] = dict(index_row or {})
    merged.update({k: v for k, v in meta.items() if v not in (None, "")})

    run.config = str(merged.get("config", merged.get("config_label", "")) or "")
    run.phase = str(merged.get("phase", "") or "")
    run.iteration = to_int(merged.get("iteration"))
    run.order_index = to_int(merged.get("order_index"))
    run.scenario_id = str(merged.get("scenario_id", "") or "")
    run.status = str(merged.get("status", "") or "")
    run.start_time = str(merged.get("start_time", "") or "")
    run.end_time = str(merged.get("end_time", "") or "")
    run.langgraph = to_bool(merged.get("langgraph"))
    run.quality_gate = to_bool(merged.get("quality_gate"))

    # サーバーログ（stderr が主。stdout 側も読む）
    found_log = False
    for name in ("server.err.log", "server.out.log", "server.log"):
        path = run_dir / name
        if path.exists():
            found_log = True
            parse_server_log(read_text_tolerant(path), run)
    if not found_log:
        run.notes.append("サーバーログが見つかりません")

    # generate API レスポンス
    for path in sorted(run_dir.glob("gen_level*.json")):
        data = load_json_tolerant(path)
        if isinstance(data, dict):
            match = re.search(r"gen_level(\d+)", path.name)
            run.responses.append({
                "level": to_int(match.group(1)) if match else None,
                "success": data.get("success"),
                "created": to_int(data.get("created")),
                "skipped": to_int(data.get("skipped")),
                "elapsed_ms": to_int(data.get("elapsed_ms")),
                "quality_summary": data.get("quality_summary") or {},
            })
        else:
            run.notes.append(f"{path.name} を解析できません")

    # ログから workflow 行が取れなかった古いログ → レスポンスで代替
    if not run.requests and run.responses:
        run.notes.append("workflow ログ行がないため gen_level*.json から集計")
        for response in run.responses:
            qs = response["quality_summary"]
            decisions_raw = qs.get("decisions")
            run.requests.append({
                "level": response["level"],
                "langgraph": run.langgraph,
                "quality_gate": to_bool(qs.get("quality_gate")),
                "mode": qs.get("workflow", ""),
                "decisions": list(decisions_raw) if isinstance(decisions_raw, list) else [],
                "regenerated": to_bool(qs.get("regenerated")),
                "retries": to_int(qs.get("retry_count")),
                "rejected_by_gate": to_int(qs.get("rejected_by_gate")),
                "regenerated_created": to_int(qs.get("regenerated_created")),
                "outcome": qs.get("outcome", ""),
                "created": response["created"],
                "elapsed_ms": response["elapsed_ms"],
            })

    # ai_returned / 除外数は workflow 行に無い → summary 行かレスポンスから
    for request in run.requests:
        level = request.get("level")
        same_level = [p for p in run.parent_timings if p.get("level") == level]
        if same_level:
            for key, src in (("ai_returned", "ai_returned"),
                             ("excluded_quality", "excluded_quality"),
                             ("excluded_dedup", "skipped_dedup")):
                values = [p.get(src) for p in same_level if p.get(src) is not None]
                if values and request.get(key) is None:
                    request[key] = sum(values)
        response = next((r for r in run.responses if r.get("level") == level), None)
        if response:
            qs = response["quality_summary"]
            request.setdefault("ai_returned", to_int(qs.get("ai_returned")))
            request.setdefault("excluded_quality", to_int(qs.get("excluded_by_quality")))
            request.setdefault("excluded_dedup", to_int(qs.get("excluded_by_dedup")))
            if request.get("avg_score") is None:
                request["avg_score"] = to_float(qs.get("average_overall_score"))

    # エクスポート CSV（保存済み要因の品質ステータス）
    export_csv_path = run_dir / "export.csv"
    if export_csv_path.exists():
        try:
            parse_export_csv(read_text_tolerant(export_csv_path), run)
        except Exception as e:
            run.notes.append(f"export.csv の解析に失敗: {e}")

    # ログ上の候補行と保存済みタイトルを突き合わせ、saved を確定
    saved_titles = {f["title"] for f in run.exported_factors}
    for candidate in run.candidates:
        if candidate["saved"] is None:
            candidate["saved"] = candidate["title"] in saved_titles

    return run


# ---------------------------------------------------------------------------
# 試験ディレクトリ全体の解析
# ---------------------------------------------------------------------------

def load_runs_index(trial_dir: pathlib.Path) -> dict[str, dict]:
    """runs_index.csv を run_id → 行辞書で返す（無くてもよい）。"""
    path = trial_dir / "runs_index.csv"
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    try:
        reader = csv.DictReader(io.StringIO(read_text_tolerant(path)))
        for row in reader:
            run_id = (row.get("run_id") or "").strip()
            if run_id:
                rows[run_id] = row
    except Exception:
        return {}
    return rows


def discover_runs(trial_dir: pathlib.Path) -> list[RunData]:
    index = load_runs_index(trial_dir)
    runs_root = trial_dir / "runs"
    runs: list[RunData] = []
    if runs_root.is_dir():
        for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
            try:
                runs.append(load_run(run_dir, index.get(run_dir.name)))
            except Exception as e:
                broken = RunData(run_dir.name)
                broken.status = "parse_error"
                broken.notes.append(f"実行ディレクトリの解析に失敗: {e}")
                runs.append(broken)
    # インデックスにあるがディレクトリが無い実行（中断時）も記録
    known = {r.run_id for r in runs}
    for run_id, row in index.items():
        if run_id not in known:
            ghost = RunData(run_id)
            ghost.config = row.get("config", "") or ""
            ghost.phase = row.get("phase", "") or ""
            ghost.status = row.get("status", "") or "missing_dir"
            ghost.notes.append("runs_index.csv に記録があるがディレクトリ無し")
            runs.append(ghost)
    return runs


# --- runs.csv ---------------------------------------------------------------

RUNS_CSV_COLUMNS = [
    "run_id", "config", "langgraph", "quality_gate", "phase", "iteration",
    "order_index", "scenario_id", "scope", "level", "status",
    "elapsed_ms", "ai_returned", "created", "excluded_quality",
    "excluded_dedup", "rejected_by_gate", "regenerated_created",
    "retries", "decisions", "outcome", "workflow_mode", "avg_score",
    "ollama_calls", "ollama_total_ms", "ollama_load_ms",
    "ollama_prompt_eval_ms", "ollama_eval_ms",
    "ollama_prompt_tokens", "ollama_eval_tokens",
    "start_time", "end_time",
]


def _ollama_level_agg(run: RunData, level: Optional[int]) -> dict:
    """指定階層（None は全体）の Ollama メトリクス合計。"""
    metrics = [
        m for m in run.ollama_metrics
        if level is None or m.get("level") == level
    ]

    def agg(key: str) -> Optional[float]:
        values = [m.get(key) for m in metrics if m.get(key) is not None]
        return sum(values) if values else None

    return {
        "ollama_calls": len(metrics) or None,
        "ollama_total_ms": agg("total_duration_ms"),
        "ollama_load_ms": agg("load_duration_ms"),
        "ollama_prompt_eval_ms": agg("prompt_eval_duration_ms"),
        "ollama_eval_ms": agg("eval_duration_ms"),
        "ollama_prompt_tokens": agg("prompt_eval_count"),
        "ollama_eval_tokens": agg("eval_count"),
    }


def build_runs_rows(runs: list[RunData]) -> list[dict]:
    rows: list[dict] = []
    for run in runs:
        base = {
            "run_id": run.run_id,
            "config": run.config,
            "langgraph": run.langgraph,
            "quality_gate": run.quality_gate,
            "phase": run.phase,
            "iteration": run.iteration,
            "order_index": run.order_index,
            "scenario_id": run.scenario_id,
            "status": run.status,
            "start_time": run.start_time,
            "end_time": run.end_time,
        }
        for request in run.requests:
            row = dict(base)
            row.update({
                "scope": "request",
                "level": request.get("level"),
                "elapsed_ms": request.get("elapsed_ms"),
                "ai_returned": request.get("ai_returned"),
                "created": request.get("created"),
                "excluded_quality": request.get("excluded_quality"),
                "excluded_dedup": request.get("excluded_dedup"),
                "rejected_by_gate": request.get("rejected_by_gate"),
                "regenerated_created": request.get("regenerated_created"),
                "retries": request.get("retries"),
                "decisions": ",".join(request.get("decisions") or []),
                "outcome": request.get("outcome", ""),
                "workflow_mode": request.get("mode", ""),
                "avg_score": request.get("avg_score"),
            })
            row.update(_ollama_level_agg(run, request.get("level")))
            rows.append(row)
        # 実行合計行（scope=run_total）
        total_row = dict(base)
        total_row.update({
            "scope": "run_total",
            "level": "all",
            "elapsed_ms": run.total_elapsed_ms,
            "ai_returned": run.request_value_sum("ai_returned"),
            "created": run.request_value_sum("created"),
            "excluded_quality": run.request_value_sum("excluded_quality"),
            "excluded_dedup": run.request_value_sum("excluded_dedup"),
            "rejected_by_gate": run.request_value_sum("rejected_by_gate"),
            "regenerated_created": run.request_value_sum("regenerated_created"),
            "retries": run.retry_total,
            "decisions": ",".join(
                f"{k}:{v}" for k, v in sorted(run.final_decisions.items())
            ),
            "outcome": "",
            "workflow_mode": ";".join(sorted({
                r.get("mode", "") for r in run.requests if r.get("mode")
            })),
            "avg_score": run.avg_quality_score,
        })
        total_row.update(_ollama_level_agg(run, None))
        rows.append(total_row)
    return rows


# --- factor_quality.csv ------------------------------------------------------

FACTOR_CSV_COLUMNS = [
    "run_id", "config", "phase", "source", "level", "parent", "attempt",
    "title", "score", "severity", "excluded", "saved",
    "warnings", "critical_reasons", "quality_status", "user_judgement",
    # 人手評価用の空欄（docs/langgraph_comparison_test.md の評価項目）
    "human_validity", "human_specificity", "human_actionability",
    "human_duplication", "human_note",
]


def build_factor_rows(runs: list[RunData]) -> list[dict]:
    rows: list[dict] = []
    for run in runs:
        base = {"run_id": run.run_id, "config": run.config, "phase": run.phase}
        # ログ由来の候補（除外・警告・gate reject を含む）
        for candidate in run.candidates:
            row = dict(base)
            row.update(candidate)
            rows.append(row)
        # エクスポート由来の保存済み要因
        logged_titles = {c["title"] for c in run.candidates}
        for factor in run.exported_factors:
            row = dict(base)
            row.update(factor)
            # ログにも出た要因は重複が分かるよう source を変えるだけで残す
            if factor["title"] in logged_titles:
                row["source"] = "export(dup)"
            rows.append(row)
    return rows


# --- summary.md ---------------------------------------------------------------

def _config_sort_key(config: str) -> tuple:
    order = {"off-off": 0, "off-on": 1, "on-off": 2, "on-on": 3}
    return (order.get(config, 99), config)


def build_summary_md(trial_dir: pathlib.Path, runs: list[RunData]) -> str:
    measured = [r for r in runs if r.phase != "warmup" and r.requests]
    warmups = [r for r in runs if r.phase == "warmup"]
    configs = sorted({r.config for r in measured if r.config}, key=_config_sort_key)

    lines: list[str] = []
    lines.append("# LangGraph / Quality Gate 比較試験サマリ")
    lines.append("")
    lines.append(f"- 試験ディレクトリ: `{trial_dir.name}`")
    lines.append(f"- 実行数: 全 {len(runs)} 件（評価対象 {len(measured)} 件 / "
                 f"ウォームアップ {len(warmups)} 件）")
    error_runs = [r for r in runs if r.status and r.status not in ("ok", "")]
    if error_runs:
        lines.append(f"- 異常終了・不完全な実行: "
                     f"{', '.join(r.run_id for r in error_runs)}")
    lines.append("")
    lines.append("ウォームアップ実行は以下の集計から除外しています。")
    lines.append("")

    def config_runs(config: str) -> list[RunData]:
        return [r for r in measured if r.config == config]

    # --- 総処理時間 -----------------------------------------------------------
    lines.append("## 総処理時間（1実行あたり、全階層合計、ms）")
    lines.append("")
    lines.append("| 設定 | n | 平均 | 中央値 | 標準偏差 | 最小 | 最大 |")
    lines.append("|------|---|------|--------|----------|------|------|")
    for config in configs:
        values = [r.total_elapsed_ms for r in config_runs(config)
                  if r.total_elapsed_ms is not None]
        lines.append(
            f"| {config} | {len(values)} | {fmt(mean_or_none(values))} "
            f"| {fmt(median_or_none(values))} | {fmt(stdev_or_none(values))} "
            f"| {fmt(min(values) if values else None)} "
            f"| {fmt(max(values) if values else None)} |"
        )
    lines.append("")

    # --- 階層別処理時間 --------------------------------------------------------
    lines.append("## 階層別処理時間（リクエスト単位、平均 ms）")
    lines.append("")
    levels = sorted({
        req.get("level") for r in measured for req in r.requests
        if req.get("level") is not None
    })
    header = "| 設定 | " + " | ".join(f"レベル{lv}" for lv in levels) + " |"
    lines.append(header)
    lines.append("|------|" + "|".join(["------"] * len(levels)) + "|")
    for config in configs:
        cells = []
        for lv in levels:
            values = [
                req.get("elapsed_ms") for r in config_runs(config)
                for req in r.requests
                if req.get("level") == lv and req.get("elapsed_ms") is not None
            ]
            cells.append(fmt(mean_or_none(values)))
        lines.append(f"| {config} | " + " | ".join(cells) + " |")
    lines.append("")

    # --- 親要因別処理時間 -------------------------------------------------------
    lines.append("## 親要因別処理時間（親要因1件分の生成、平均 ms）")
    lines.append("")
    lines.append("生成される親要因名は実行ごとに変わり得るため、"
                 "同名の親要因が複数回出た場合のみ平均になります。")
    lines.append("")
    lines.append("| 設定 | レベル | 親要因 | 回数 | 平均 ms |")
    lines.append("|------|--------|--------|------|---------|")
    for config in configs:
        grouped: dict[tuple, list[int]] = defaultdict(list)
        for r in config_runs(config):
            for p in r.parent_timings:
                if p.get("elapsed_ms") is not None:
                    grouped[(p.get("level"), p.get("parent", ""))].append(p["elapsed_ms"])
        for (level, parent), values in sorted(grouped.items(),
                                              key=lambda kv: (kv[0][0] or 0, kv[0][1])):
            lines.append(
                f"| {config} | {fmt(level)} | {parent} | {len(values)} "
                f"| {fmt(mean_or_none(values))} |"
            )
    lines.append("")

    # --- Ollama 推論 ------------------------------------------------------------
    lines.append("## Ollama 推論時間・トークン数（1実行あたり平均）")
    lines.append("")
    lines.append("| 設定 | 呼出回数 | total_duration(ms) | prompt_eval(ms) | "
                 "eval(ms) | 入力トークン | 出力トークン |")
    lines.append("|------|----------|--------------------|-----------------|"
                 "----------|--------------|--------------|")
    for config in configs:
        runs_c = config_runs(config)
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                config,
                fmt(mean_or_none([len(r.ollama_metrics) or None for r in runs_c])),
                fmt(mean_or_none([r.ollama_sum("total_duration_ms") for r in runs_c])),
                fmt(mean_or_none([r.ollama_sum("prompt_eval_duration_ms") for r in runs_c])),
                fmt(mean_or_none([r.ollama_sum("eval_duration_ms") for r in runs_c])),
                fmt(mean_or_none([r.ollama_sum("prompt_eval_count") for r in runs_c])),
                fmt(mean_or_none([r.ollama_sum("eval_count") for r in runs_c])),
            )
        )
    lines.append("")
    lines.append("Ollama メトリクスが出力されない設定（ENABLE_GENERATION_METRICS=false "
                 "や mock プロバイダ）では「-」になります。")
    lines.append("")

    # --- 生成品質 ---------------------------------------------------------------
    lines.append("## 生成品質（1実行あたり平均）")
    lines.append("")
    lines.append("| 設定 | ai_returned | created | 品質チェック除外 | DB重複除外 | "
                 "rejected_by_gate | regenerated_created | 再生成回数 | "
                 "平均品質スコア(0-100) | workflowスコア(0-1) |")
    lines.append("|------|------------|---------|------------------|------------|"
                 "------------------|---------------------|------------|"
                 "----------------------|--------------------|")
    for config in configs:
        runs_c = config_runs(config)

        def m(key: str) -> Optional[float]:
            return mean_or_none([r.request_value_sum(key) for r in runs_c])

        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                config,
                fmt(m("ai_returned")), fmt(m("created")),
                fmt(m("excluded_quality")), fmt(m("excluded_dedup")),
                fmt(m("rejected_by_gate")), fmt(m("regenerated_created")),
                fmt(m("retries")),
                fmt(mean_or_none([r.avg_quality_score for r in runs_c])),
                fmt(mean_or_none([r.workflow_quality_score for r in runs_c]), 2),
            )
        )
    lines.append("")

    # --- decision 別件数 ----------------------------------------------------------
    lines.append("## decision 別件数（親要因単位の最終判定、評価対象実行の合計）")
    lines.append("")
    decision_keys = sorted({
        d for r in measured for d in r.final_decisions
    })
    if decision_keys:
        lines.append("| 設定 | " + " | ".join(decision_keys) + " |")
        lines.append("|------|" + "|".join(["------"] * len(decision_keys)) + "|")
        for config in configs:
            total: Counter = Counter()
            for r in config_runs(config):
                total.update(r.final_decisions)
            lines.append(
                f"| {config} | " +
                " | ".join(str(total.get(k, 0)) for k in decision_keys) + " |"
            )
    else:
        lines.append("（decision 情報のある実行がありません — LangGraph OFF のみの試験など）")
    lines.append("")
    lines.append("途中判定を含む decide 行の内訳（regenerate は再生成の発火回数）:")
    lines.append("")
    decide_keys = sorted({d for r in measured for d in r.decide_counts})
    if decide_keys:
        lines.append("| 設定 | " + " | ".join(decide_keys) + " |")
        lines.append("|------|" + "|".join(["------"] * len(decide_keys)) + "|")
        for config in configs:
            total = Counter()
            for r in config_runs(config):
                total.update(r.decide_counts)
            lines.append(
                f"| {config} | " +
                " | ".join(str(total.get(k, 0)) for k in decide_keys) + " |"
            )
    else:
        lines.append("（decide ログ行なし）")
    lines.append("")

    # --- 理由別件数 -----------------------------------------------------------------
    for title, attr in (("warning 理由別件数", "warning_reasons"),
                        ("critical 理由別件数", "critical_reasons")):
        lines.append(f"## {title}（評価対象実行の合計）")
        lines.append("")
        keys = sorted({
            k for r in measured for k in getattr(r, attr) if k
        })
        if keys:
            lines.append("| 理由 | " + " | ".join(configs) + " |")
            lines.append("|------|" + "|".join(["------"] * len(configs)) + "|")
            for key in keys:
                cells = []
                for config in configs:
                    total = sum(getattr(r, attr).get(key, 0)
                                for r in config_runs(config))
                    cells.append(str(total))
                lines.append(f"| {key} | " + " | ".join(cells) + " |")
        else:
            lines.append("（該当なし）")
        lines.append("")

    # --- 解析ノート -----------------------------------------------------------------
    notes = [(r.run_id, note) for r in runs for note in r.notes]
    lines.append("## 解析ノート（欠損・解析できなかった項目）")
    lines.append("")
    if notes:
        for run_id, note in notes:
            lines.append(f"- `{run_id}`: {note}")
    else:
        lines.append("（なし）")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def write_csv(path: pathlib.Path, columns: list[str], rows: list[dict]) -> None:
    # Excel(Windows) でそのまま開けるよう UTF-8 BOM で出力する
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: ("" if row.get(k) is None else row.get(k)) for k in columns
            })


def analyze_trial(trial_dir: pathlib.Path, out_dir: Optional[pathlib.Path] = None) -> int:
    if not trial_dir.is_dir():
        print(f"試験ディレクトリが見つかりません: {trial_dir}", file=sys.stderr)
        return 1
    out_dir = out_dir or (trial_dir / "analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = discover_runs(trial_dir)
    if not runs:
        print(f"実行データがありません（{trial_dir / 'runs'} が空）", file=sys.stderr)
        # それでも空の出力は作る（スクリプト連携を単純にするため）
        write_csv(out_dir / "runs.csv", RUNS_CSV_COLUMNS, [])
        write_csv(out_dir / "factor_quality.csv", FACTOR_CSV_COLUMNS, [])
        (out_dir / "summary.md").write_text(
            "# LangGraph / Quality Gate 比較試験サマリ\n\n実行データがありません。\n",
            encoding="utf-8",
        )
        return 0

    write_csv(out_dir / "runs.csv", RUNS_CSV_COLUMNS, build_runs_rows(runs))
    write_csv(out_dir / "factor_quality.csv", FACTOR_CSV_COLUMNS,
              build_factor_rows(runs))
    (out_dir / "summary.md").write_text(
        build_summary_md(trial_dir, runs), encoding="utf-8"
    )

    print(f"解析完了: {len(runs)} 実行")
    print(f"  {out_dir / 'runs.csv'}")
    print(f"  {out_dir / 'factor_quality.csv'}")
    print(f"  {out_dir / 'summary.md'}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="LangGraph/Quality Gate 比較試験ログの解析",
    )
    parser.add_argument("trial_dir", nargs="?",
                        help="run_langgraph_comparison.ps1 の試験出力ディレクトリ")
    parser.add_argument("--out", help="解析結果の出力先（既定: <trial_dir>/analysis）")
    parser.add_argument("--list-scenarios", action="store_true",
                        help="サンプルシナリオID一覧を表示して終了")
    parser.add_argument("--dump-scenario", metavar="ID",
                        help="指定シナリオを JSON で出力して終了")
    parser.add_argument("--scenario-file",
                        help="sample_scenarios.yaml のパス（既定: config/sample_scenarios.yaml）")
    args = parser.parse_args(argv)

    if args.list_scenarios:
        return cmd_list_scenarios(args.scenario_file)
    if args.dump_scenario:
        return cmd_dump_scenario(args.dump_scenario, args.scenario_file)
    if not args.trial_dir:
        parser.error("trial_dir を指定してください")
    return analyze_trial(
        pathlib.Path(args.trial_dir),
        pathlib.Path(args.out) if args.out else None,
    )


if __name__ == "__main__":
    sys.exit(main())

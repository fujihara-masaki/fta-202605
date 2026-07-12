"""比較試験解析スクリプト（scripts/analyze_langgraph_comparison.py）のテスト。

実 Ollama・実サーバーには一切アクセスせず、tests/fixtures/langgraph_comparison
配下のサンプルログ・サンプルCSVだけで解析処理を検証する。

fixture の構成（trial_sample）:
  - 001_off-off_warmup_01   ウォームアップ実行（集計から除外されること）
  - 002_off-off_measured_01 legacy 実行（メトリクス・除外・重複あり）
  - 003_on-on_measured_01   LangGraph+ゲート実行（部分再生成・gate reject あり）
  - 004_on-off_measured_01  欠損の多い古いログ（run_meta.json / gen_level*.json /
                            export.csv / generation_metrics なし）→ 例外なく解析
"""

import csv
import importlib.util
import json
import pathlib
import shutil

import pytest

_SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts" / "analyze_langgraph_comparison.py"
)
_FIXTURE_TRIAL = (
    pathlib.Path(__file__).resolve().parent
    / "fixtures" / "langgraph_comparison" / "trial_sample"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "analyze_langgraph_comparison", _SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyzer = _load_module()


@pytest.fixture()
def trial_dir(tmp_path):
    """空白を含むパスへ fixture をコピーして解析対象にする（Windows想定）。"""
    dest = tmp_path / "path with spaces" / "trial_sample"
    shutil.copytree(_FIXTURE_TRIAL, dest)
    return dest


@pytest.fixture()
def analyzed(trial_dir):
    rc = analyzer.analyze_trial(trial_dir)
    assert rc == 0
    return trial_dir / "analysis"


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# --- 出力ファイルの生成 -------------------------------------------------------

def test_outputs_created(analyzed):
    assert (analyzed / "runs.csv").exists()
    assert (analyzed / "factor_quality.csv").exists()
    assert (analyzed / "summary.md").exists()


def test_path_with_spaces(analyzed):
    # fixture 自体を空白入りパスへコピーして解析している
    assert " " in str(analyzed)
    assert (analyzed / "runs.csv").exists()


# --- runs.csv -----------------------------------------------------------------

def test_runs_csv_request_rows(analyzed):
    rows = _read_csv(analyzed / "runs.csv")
    legacy = [r for r in rows if r["run_id"] == "002_off-off_measured_01"
              and r["scope"] == "request"]
    assert len(legacy) == 2  # level 1 / level 2

    level1 = next(r for r in legacy if r["level"] == "1")
    assert level1["elapsed_ms"] == "21000"
    assert level1["created"] == "3"
    assert level1["ai_returned"] == "4"
    assert level1["excluded_quality"] == "1"
    assert level1["workflow_mode"] == "legacy"

    level2 = next(r for r in legacy if r["level"] == "2")
    assert level2["excluded_dedup"] == "1"
    # Ollama トークン集計（level2 は2回呼び出し: 280+300）
    assert level2["ollama_eval_tokens"] == "580"
    assert level2["ollama_calls"] == "2"


def test_runs_csv_run_total_row(analyzed):
    rows = _read_csv(analyzed / "runs.csv")
    total = next(r for r in rows if r["run_id"] == "002_off-off_measured_01"
                 and r["scope"] == "run_total")
    assert total["elapsed_ms"] == "55000"  # 21000 + 34000
    assert total["created"] == "8"
    assert total["ollama_calls"] == "3"
    assert total["ollama_eval_tokens"] == "930"  # 350 + 280 + 300


def test_runs_csv_gate_metrics(analyzed):
    rows = _read_csv(analyzed / "runs.csv")
    total = next(r for r in rows if r["run_id"] == "003_on-on_measured_01"
                 and r["scope"] == "run_total")
    assert total["rejected_by_gate"] == "1"
    assert total["regenerated_created"] == "1"
    assert total["retries"] == "2"  # level1: 1, level2: 1
    assert "accept_with_warning:2" in total["decisions"]
    assert "accept:1" in total["decisions"]


def test_runs_csv_warmup_included_as_rows(analyzed):
    # ウォームアップも runs.csv には出る（summary の集計からのみ除外）
    rows = _read_csv(analyzed / "runs.csv")
    warmup = [r for r in rows if r["run_id"] == "001_off-off_warmup_01"]
    assert warmup
    assert all(r["phase"] == "warmup" for r in warmup)


def test_degraded_old_log_does_not_crash(analyzed):
    # 004 は run_meta.json / gen_level*.json / export.csv / metrics なし
    rows = _read_csv(analyzed / "runs.csv")
    degraded = [r for r in rows if r["run_id"] == "004_on-off_measured_01"
                and r["scope"] == "request"]
    assert len(degraded) == 2
    level1 = next(r for r in degraded if r["level"] == "1")
    assert level1["elapsed_ms"] == "30000"
    # 古いログに無いフィールドは空欄になる（例外にならない）
    assert level1["rejected_by_gate"] == ""
    assert level1["ollama_eval_tokens"] == ""


# --- factor_quality.csv ---------------------------------------------------------

def test_factor_quality_contains_gate_reject(analyzed):
    rows = _read_csv(analyzed / "factor_quality.csv")
    rejects = [r for r in rows if r["source"] == "gate_reject"]
    assert len(rejects) == 1
    assert rejects[0]["title"] == "変更後の疎通確認不足"
    assert rejects[0]["saved"] == "False"
    assert "No評価済み要因と類似" in rejects[0]["critical_reasons"]


def test_factor_quality_candidate_saved_flag(analyzed):
    rows = _read_csv(analyzed / "factor_quality.csv")
    candidates = {
        r["title"]: r for r in rows
        if r["run_id"] == "003_on-on_measured_01"
        and r["source"] == "langgraph_candidate"
    }
    # 保存された要因はエクスポートCSVとの突き合わせで saved=True になる
    assert candidates["DNSの名前解決失敗"]["saved"] == "True"
    # 除外された言い換え候補は saved=False
    assert candidates["Webシステムにアクセスできない状態"]["saved"] == "False"
    assert candidates["Webシステムにアクセスできない状態"]["severity"] == "critical"


def test_factor_quality_has_human_evaluation_columns(analyzed):
    rows = _read_csv(analyzed / "factor_quality.csv")
    assert rows
    for column in ("human_validity", "human_specificity",
                   "human_actionability", "human_duplication", "human_note"):
        assert column in rows[0]
        assert all(r[column] == "" for r in rows)  # 人手記入用に空欄


def test_factor_quality_includes_legacy_exclusions(analyzed):
    rows = _read_csv(analyzed / "factor_quality.csv")
    legacy = [r for r in rows if r["run_id"] == "002_off-off_measured_01"]
    sources = {r["source"] for r in legacy}
    assert "legacy_exclude" in sources
    assert "legacy_warning" in sources
    assert "dedup_skip" in sources
    assert "export" in sources or "export(dup)" in sources


# --- summary.md -----------------------------------------------------------------

def test_summary_md_content(analyzed):
    text = (analyzed / "summary.md").read_text(encoding="utf-8")
    # 設定別集計
    assert "off-off" in text
    assert "on-on" in text
    assert "on-off" in text
    # 要求された集計指標の見出し
    assert "総処理時間" in text
    assert "階層別処理時間" in text
    assert "親要因別処理時間" in text
    assert "Ollama 推論時間・トークン数" in text
    assert "rejected_by_gate" in text
    assert "decision 別件数" in text
    assert "warning 理由別件数" in text
    assert "critical 理由別件数" in text
    # ウォームアップは除外と明記
    assert "ウォームアップ" in text
    # 理由ラベルの正規化（「…」の可変部分が落ちている）
    assert "親要因の言い換え" in text
    # 欠損ログの解析ノート
    assert "解析ノート" in text


def test_summary_md_excludes_warmup_from_totals(analyzed):
    text = (analyzed / "summary.md").read_text(encoding="utf-8")
    # off-off の計測実行は 1 件だけ（warmup の 60000ms は平均に入らない）
    for line in text.splitlines():
        if line.startswith("| off-off |"):
            cells = [c.strip() for c in line.split("|")]
            assert cells[2] == "1"       # n
            assert cells[3] == "55000.0"  # 平均 = 002 の合計のみ
            break
    else:
        pytest.fail("off-off の総処理時間の行が見つかりません")


# --- 異常系・補助モード -----------------------------------------------------------

def test_missing_trial_dir_returns_error(tmp_path, capsys):
    rc = analyzer.analyze_trial(tmp_path / "no such trial")
    assert rc == 1


def test_empty_trial_dir_creates_empty_outputs(tmp_path):
    trial = tmp_path / "empty trial"
    trial.mkdir()
    rc = analyzer.analyze_trial(trial)
    assert rc == 0
    assert (trial / "analysis" / "runs.csv").exists()
    assert (trial / "analysis" / "summary.md").exists()


def test_broken_files_do_not_crash(tmp_path):
    # 壊れた JSON・壊れた CSV・バイナリまがいのログでも例外終了しない
    trial = tmp_path / "broken trial"
    run_dir = trial / "runs" / "001_off-off_measured_01"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text("{not valid json", encoding="utf-8")
    (run_dir / "gen_level1.json").write_text("also broken", encoding="utf-8")
    (run_dir / "export.csv").write_bytes(b"\xff\xfe\x00broken")
    (run_dir / "server.err.log").write_text(
        "generate_factors workflow | analysis=1 level=1 langgraph=False "
        "quality_gate=False mode=legacy decisions=- regenerated=False "
        "retries=0 outcome=created created=4 elapsed_ms=1000\n",
        encoding="utf-8",
    )
    rc = analyzer.analyze_trial(trial)
    assert rc == 0
    rows = _read_csv(trial / "analysis" / "runs.csv")
    assert any(r["elapsed_ms"] == "1000" for r in rows)


def test_parse_kv_line_quoted_values():
    kv = analyzer.parse_kv_line(
        "decision=accept parent='DNS の 設定誤り' quality_score=0.85 elapsed_ms=1200"
    )
    assert kv["decision"] == "accept"
    assert kv["parent"] == "DNS の 設定誤り"
    assert kv["quality_score"] == "0.85"


def test_normalize_reason_strips_variable_parts():
    assert analyzer.normalize_reason("既存要因「外部DNSの障害」に類似") == "既存要因に類似"
    assert analyzer.normalize_reason("要因名が長すぎる（35文字）") == "要因名が長すぎる"
    assert analyzer.normalize_reason("汎用的すぎる要因名") == "汎用的すぎる要因名"


def test_dump_scenario_mode(capsys):
    rc = analyzer.cmd_dump_scenario("internet_web_access_failure", None)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["id"] == "internet_web_access_failure"
    assert data["top_event"]
    assert "system_context" in data


def test_dump_scenario_unknown_id(capsys):
    rc = analyzer.cmd_dump_scenario("no_such_scenario", None)
    assert rc == 1


def test_list_scenarios_mode(capsys):
    rc = analyzer.cmd_list_scenarios(None)
    assert rc == 0
    out = capsys.readouterr().out
    assert "internet_web_access_failure" in out

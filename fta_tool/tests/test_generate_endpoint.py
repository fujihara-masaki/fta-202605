"""
Endpoint-level tests for the /generate API.

- The existing response contract is unchanged and carries the additive
  quality_summary (Step 1).
- Step 1.5: a「+0件」result is explainable — all_candidates_excluded /
  outcome / reason_summary distinguish "LLM returned nothing" from
  "candidates were generated but the quality check rejected all of them".

Uses an isolated temp DB. The default MockAIProvider is used where a real
generation is wanted; a stub provider is injected where a specific
exclusion scenario is needed.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app import crud, models, schemas
from app.database import get_db
from app.main import app
from app.services.ai_provider import GeneratedFactor


class _StubProvider:
    """Returns a fixed list of candidates regardless of inputs."""

    def __init__(self, factors):
        self._factors = factors

    def generate_factors(self, **kwargs):
        return [
            GeneratedFactor(
                title=t, description=d, rationale="テスト", check_points=[],
            )
            for (t, d) in self._factors
        ]


def _use_stub(monkeypatch, factors):
    monkeypatch.setattr(main_module, "get_ai_provider", lambda: _StubProvider(factors))
    # Keep the per-call count retry deterministic / off for the stub.
    monkeypatch.setenv("FTA_RETRY_BELOW_MIN", "false")
    monkeypatch.setenv("FTA_RETRY_BELOW_TARGET", "false")


class _SeqStubProvider:
    """Returns the next scripted list per call (for workflow regeneration)."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = 0

    def generate_factors(self, **kwargs):
        idx = min(self.calls, len(self.scripts) - 1)
        self.calls += 1
        return [
            GeneratedFactor(title=t, description=d, rationale="t", check_points=[])
            for (t, d) in self.scripts[idx]
        ]


def _use_workflow_stub(monkeypatch, scripts, *, max_retries=1):
    provider = _SeqStubProvider(scripts)
    monkeypatch.setattr(main_module, "get_ai_provider", lambda: provider)
    monkeypatch.setenv("ENABLE_LANGGRAPH_GENERATION_WORKFLOW", "true")
    monkeypatch.setenv("LANGGRAPH_GENERATION_MAX_RETRIES", str(max_retries))
    monkeypatch.setenv("FTA_RETRY_BELOW_MIN", "false")
    return provider


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)  # default mock provider
    # Endpoint tests must not depend on the local .env: main.py loads it with
    # override=True at import time, so a developer's .env with the LangGraph
    # workflow / quality gate enabled would silently flip the path under test.
    # Default every test to the legacy path; workflow/gate tests opt back in
    # via _use_workflow_stub / their own monkeypatch.setenv (which run after
    # this fixture and therefore win).
    monkeypatch.setenv("ENABLE_LANGGRAPH_GENERATION_WORKFLOW", "false")
    monkeypatch.setenv("ENABLE_LANGGRAPH_QUALITY_GATE", "false")
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    # Seed one analysis with a top event.
    db = TestingSessionLocal()
    analysis = crud.create_analysis(
        db, schemas.AnalysisCreate(title="テスト分析", top_event="ログイン障害が発生した")
    )
    analysis_id = analysis.id
    db.close()

    with TestClient(app) as c:
        c.analysis_id = analysis_id
        c.SessionLocal = TestingSessionLocal
        yield c

    app.dependency_overrides.clear()


def _add_node(client, title, *, level=1, parent_id=None, judgement="yes"):
    db = client.SessionLocal()
    try:
        node = crud.create_node(db, client.analysis_id, {
            "parent_id": parent_id,
            "level": level,
            "title": title,
            "description": f"{title}の説明",
            "ai_generated": False,
            "user_judgement": judgement,
            "direct_cause_status": "unknown",
            "display_order": 0,
            "warning_flags": "",
        })
        return node.id
    finally:
        db.close()


def test_generate_level1_response_shape(client):
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/1",
        json={"parent_id": None},
    )
    assert res.status_code == 200
    data = res.json()

    # Existing response contract is preserved.
    for key in ("success", "message", "created", "skipped", "elapsed_ms", "parent_id"):
        assert key in data
    assert data["success"] is True
    assert data["created"] > 0

    # Additive quality summary (existing UI ignores unknown keys).
    assert "quality_summary" in data
    qs = data["quality_summary"]
    assert qs["scored_count"] == data["created"]
    assert isinstance(qs["judgment_counts"], dict)
    assert 0 <= qs["average_overall_score"] <= 100

    # Step 1.5 fields present on a normal success.
    assert qs["all_candidates_excluded"] is False
    assert qs["outcome"] in ("created", "partial")
    assert qs["ai_returned"] == qs["created"] + qs["excluded"]
    assert qs["created"] == data["created"]


# --- Step 1.5: all candidates excluded ------------------------------------

def test_all_candidates_excluded_parent_paraphrase(client, monkeypatch):
    """LLM returns a paraphrase of the parent → all excluded, explainable."""
    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    # Stub returns a single candidate identical to the parent title (E1).
    _use_stub(monkeypatch, [("認証基盤の問題", "認証基盤に問題がある可能性")])

    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    assert res.status_code == 200
    data = res.json()

    # Existing contract preserved; success stays True (not an error).
    assert data["success"] is True
    assert data["created"] == 0
    assert data["skipped"] == 1

    qs = data["quality_summary"]
    assert qs["ai_returned"] == 1
    assert qs["created"] == 0
    assert qs["excluded"] == 1
    assert qs["all_candidates_excluded"] is True
    assert qs["outcome"] == "all_excluded"
    assert "親要因の言い換え" in qs["reason_summary"]
    assert "品質チェック" in data["message"] and "除外" in data["message"]


def test_all_candidates_excluded_no_rated_similar(client, monkeypatch):
    """LLM returns a factor matching a No-rated factor → excluded as such."""
    parent_id = _add_node(client, "ネットワークの問題", level=1, judgement="yes")
    _add_node(client, "DNS設定の誤り", level=1, judgement="no")
    _use_stub(monkeypatch, [("DNS設定の誤り", "DNSの設定値が誤っている可能性")])

    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert qs["all_candidates_excluded"] is True
    assert qs["outcome"] == "all_excluded"
    assert "No評価済み要因との類似" in qs["reason_summary"]


def test_all_excluded_emits_log(client, monkeypatch, caplog):
    """A `quality_all_excluded` warning log line is emitted for ops."""
    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    _use_stub(monkeypatch, [("認証基盤の問題", "認証基盤に問題がある可能性")])

    with caplog.at_level("WARNING"):
        client.post(
            f"/analyses/{client.analysis_id}/generate/level/2",
            json={"parent_id": parent_id},
        )

    lines = [r.message for r in caplog.records if "quality_all_excluded" in r.message]
    assert lines, "expected a quality_all_excluded log line"
    assert "ai_returned=1" in lines[0]
    assert "親要因の言い換え" in lines[0]


# --- Step 1.5: LLM returned no candidate (distinct from all-excluded) ------

def test_no_candidates_returned(client, monkeypatch):
    parent_id = _add_node(client, "運用手順の不備", level=1, judgement="yes")
    _use_stub(monkeypatch, [])  # LLM returns nothing

    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert data["created"] == 0
    assert qs["ai_returned"] == 0
    assert qs["all_candidates_excluded"] is False
    assert qs["outcome"] == "no_candidates"
    assert qs["reason_summary"] == []
    assert "候補がありません" in data["message"]


# --- Step 2-1: LangGraph workflow path -------------------------------------

def test_flag_off_uses_legacy_path(client, monkeypatch):
    """Default (flag off): workflow=legacy, no regeneration, response intact."""
    monkeypatch.delenv("ENABLE_LANGGRAPH_GENERATION_WORKFLOW", raising=False)
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/1",
        json={"parent_id": None},
    )
    qs = res.json()["quality_summary"]
    assert qs["workflow"] == "legacy"
    assert qs["regenerated"] is False
    assert qs["retry_count"] == 0
    assert qs["workflow_error"] is None


def test_flag_on_workflow_created_no_regen(client, monkeypatch):
    """Flag on, good candidates first time → workflow used, no regeneration."""
    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    provider = _use_workflow_stub(monkeypatch, [
        [("証明書の有効期限切れ", "TLS証明書の有効期限を確認する"),
         ("DNS応答の遅延", "DNSサーバの応答時間を確認する")],
    ])
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert qs["workflow"] == "langgraph"
    assert qs["regenerated"] is False
    assert qs["retry_count"] == 0
    assert data["created"] == 2
    assert provider.calls == 1  # generated once, no regeneration


def test_flag_on_all_excluded_regenerates(client, monkeypatch):
    """Flag on, first round all excluded → regenerate once → created."""
    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    provider = _use_workflow_stub(monkeypatch, [
        [("認証基盤の問題", "認証基盤に問題がある可能性")],          # paraphrase → excluded
        [("証明書の有効期限切れ", "TLS証明書の有効期限を確認する")],  # good
    ])
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert qs["workflow"] == "langgraph"
    assert qs["regenerated"] is True
    assert qs["retry_count"] == 1
    assert data["created"] == 1
    assert provider.calls == 2  # initial + one regeneration


def test_flag_on_fallback_on_workflow_exception(client, monkeypatch):
    """If the workflow raises, main.py falls back to the legacy path."""
    parent_id = _add_node(client, "設定管理の不備", level=1, judgement="yes")
    # Legacy path will use this normal stub and succeed.
    monkeypatch.setattr(main_module, "get_ai_provider",
                        lambda: _StubProvider([("証明書の有効期限切れ", "TLS証明書の有効期限を確認する")]))
    monkeypatch.setenv("ENABLE_LANGGRAPH_GENERATION_WORKFLOW", "true")
    monkeypatch.setenv("FTA_RETRY_BELOW_MIN", "false")

    # Make the workflow blow up.
    import app.services.generation_workflow as gw

    def _boom(**kwargs):
        raise RuntimeError("workflow exploded")

    monkeypatch.setattr(gw, "run_generation_workflow", _boom)

    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert qs["workflow"] == "legacy_fallback"
    assert qs["workflow_error"] is not None
    assert "workflow exploded" in qs["workflow_error"]
    assert data["created"] == 1  # legacy path still produced the factor


# --- Step 3: quality gate through the endpoint ------------------------------

def test_step3_fields_present_and_gate_off_by_default(client, monkeypatch):
    """quality_summary carries the additive Step 3 fields; gate defaults off."""
    monkeypatch.delenv("ENABLE_LANGGRAPH_QUALITY_GATE", raising=False)
    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    provider = _use_workflow_stub(monkeypatch, [
        [("証明書の有効期限切れ", "TLS証明書の有効期限を確認する")],
    ])
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    qs = res.json()["quality_summary"]
    assert qs["quality_gate"] is False
    assert qs["decisions"] == ["accept"]
    assert provider.calls == 1


def test_step3_gate_on_low_quality_regenerates(client, monkeypatch):
    """Gate on + kept-but-low-scoring first round → regeneration branch."""
    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    provider = _use_workflow_stub(monkeypatch, [
        [("確認不足", "作業前後の確認が実施されていないか確認する")],  # kept, warned
        [("証明書の有効期限切れ", "TLS証明書の有効期限を確認する")],
    ])
    monkeypatch.setenv("ENABLE_LANGGRAPH_QUALITY_GATE", "true")
    monkeypatch.setenv("LANGGRAPH_QUALITY_THRESHOLD", "0.95")
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert qs["quality_gate"] is True
    assert qs["regenerated"] is True
    assert qs["retry_count"] == 1
    assert qs["decisions"] == ["accept"]
    assert data["created"] == 1
    assert provider.calls == 2


def test_step3_gate_on_budget_spent_accepts_best_attempt_with_warning(client, monkeypatch):
    """Retry budget spent below threshold → accept_with_warning, best attempt
    persisted (usable candidates are never dropped by the budget limit)."""
    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    provider = _use_workflow_stub(monkeypatch, [
        [("確認不足", "作業前後の確認が実施されていないか確認する")],  # kept, warned
        [("認証基盤の問題", "認証基盤に問題がある可能性")],            # all excluded
    ], max_retries=1)
    monkeypatch.setenv("ENABLE_LANGGRAPH_QUALITY_GATE", "true")
    monkeypatch.setenv("LANGGRAPH_QUALITY_THRESHOLD", "0.95")
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert qs["decisions"] == ["accept_with_warning"]
    assert qs["regenerated"] is True
    # Best attempt (the warned-but-kept candidate) was persisted, not dropped.
    assert data["created"] == 1
    assert qs["workflow_error"] is None
    assert provider.calls == 2


# --- Step 3.5: graded gate — rejection accounting / regeneration marker ------

def test_step35_gate_rejects_are_counted_as_quality_exclusions(client, monkeypatch):
    """再生成後も言い換えが残った候補は除外（reject）され、
    excluded_by_quality / reason_summary / rejected_by_gate に反映される。"""
    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    provider = _use_workflow_stub(monkeypatch, [
        [("証明書の有効期限切れ", "TLS証明書の有効期限を確認する"),
         ("認証基盤の問題", "認証基盤に問題がある可能性")],   # good + paraphrase
        [("認証基盤の不備", "認証基盤側の不備の可能性")],      # paraphrase again
    ], max_retries=1)
    monkeypatch.setenv("ENABLE_LANGGRAPH_QUALITY_GATE", "true")
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert qs["decisions"] == ["accept_with_warning"]
    assert data["created"] == 1                    # 良い候補は維持
    assert qs["rejected_by_gate"] == 1             # 言い換えは除外
    assert qs["excluded_by_quality"] == 1
    assert qs["ai_returned"] == 2
    assert "親要因の言い換え" in qs["reason_summary"]
    assert provider.calls == 2


def test_step35_regenerated_factor_gets_warning_flag_marker(client, monkeypatch):
    """再生成で生成された要因には warning_flags にマーカーが付き、
    CSVで「再生成」と判別できる。"""
    from app.services.factor_quality import REGENERATED_FLAG_LABEL

    parent_id = _add_node(client, "認証基盤の問題", level=1, judgement="yes")
    provider = _use_workflow_stub(monkeypatch, [
        [("認証基盤の問題", "認証基盤に問題がある可能性")],          # paraphrase → 再生成
        [("証明書の有効期限切れ", "TLS証明書の有効期限を確認する")],  # good
    ])
    monkeypatch.setenv("ENABLE_LANGGRAPH_QUALITY_GATE", "true")
    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    assert data["created"] == 1
    assert data["quality_summary"]["regenerated_created"] == 1
    assert provider.calls == 2

    db = client.SessionLocal()
    try:
        node = (
            db.query(models.Node)
            .filter(models.Node.parent_id == parent_id)
            .one()
        )
        assert REGENERATED_FLAG_LABEL in (node.warning_flags or "")
    finally:
        db.close()


# --- Step 2-A: DB-level dedup stays in main.py (not in evaluate_candidates) -

def test_db_dedup_handled_in_main(client, monkeypatch):
    """A candidate whose title already exists in the DB (same parent/level) is
    skipped via crud.node_title_exists in main.py and counted as a dedup
    exclusion — separate from quality exclusions."""
    parent_id = _add_node(client, "設定管理の不備", level=1, judgement="yes")
    # Pre-existing level-2 child under the parent.
    _add_node(client, "既存の子要因", level=2, parent_id=parent_id, judgement="unknown")
    # Stub returns the duplicate + one good new candidate.
    _use_stub(monkeypatch, [
        ("既存の子要因", "既存の子要因に関する説明"),
        ("証明書の有効期限切れ", "TLS証明書の有効期限を確認する"),
    ])

    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert data["created"] == 1
    assert qs["excluded_by_dedup"] == 1
    assert qs["excluded_by_quality"] == 0
    assert qs["outcome"] == "partial"


# --- Step 1.5: normal partial (some created, some excluded) ----------------

def test_partial_created_and_excluded(client, monkeypatch):
    parent_id = _add_node(client, "設定管理の不備", level=1, judgement="yes")
    # One good candidate + one parent paraphrase (excluded).
    _use_stub(monkeypatch, [
        ("証明書の有効期限切れ", "TLS証明書の有効期限が切れていないか確認する"),
        ("設定管理の不備", "設定管理に不備がある可能性"),
    ])

    res = client.post(
        f"/analyses/{client.analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    data = res.json()
    qs = data["quality_summary"]
    assert data["created"] == 1
    assert qs["ai_returned"] == 2
    assert qs["created"] == 1
    assert qs["excluded"] == 1
    assert qs["all_candidates_excluded"] is False
    assert qs["outcome"] == "partial"

"""
Tests for the analysis-context input / edit UX:

- Normal (hand-entered) creation saves system_context / incident_context.
- Creation without context keeps the legacy behavior (analysis_context == "").
- The new-analysis form shows the context fields as visible inputs (the
  sample-scenario apply writes into them, not into hidden fields).
- The detail page renders the saved context and the dedicated update API
  (POST /analyses/{id}/context) trims, preserves demo_points and unknown
  keys, and safely handles empty / broken / legacy-shaped JSON.
- The freshly-updated context is what reaches the AI provider and the
  LangGraph workflow on the next generation call.
- JSON / Markdown exports keep working with a hand-edited context.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app import crud, models, schemas
from app.database import get_db
from app.main import app
from app.services.ai_provider import GeneratedFactor


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)  # default mock provider
    # Independent of a developer's .env (loaded with override=True at import
    # time): pin the legacy path; the LangGraph test opts back in explicitly.
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

    with TestClient(app) as c:
        c.SessionLocal = TestingSessionLocal
        yield c

    app.dependency_overrides.clear()


def _create_analysis(client, *, analysis_context="", top_event="ログイン障害が発生した"):
    db = client.SessionLocal()
    try:
        analysis = crud.create_analysis(db, schemas.AnalysisCreate(
            title="テスト分析", top_event=top_event, analysis_context=analysis_context,
        ))
        return analysis.id
    finally:
        db.close()


def _get_stored_context(client, analysis_id):
    db = client.SessionLocal()
    try:
        return crud.get_analysis(db, analysis_id).analysis_context
    finally:
        db.close()


def _add_yes_node(client, analysis_id, title):
    db = client.SessionLocal()
    try:
        node = crud.create_node(db, analysis_id, {
            "parent_id": None,
            "level": 1,
            "title": title,
            "description": f"{title}の説明",
            "ai_generated": False,
            "user_judgement": "yes",
            "direct_cause_status": "unknown",
            "display_order": 0,
            "warning_flags": "",
        })
        return node.id
    finally:
        db.close()


# --- POST /analyses: normal creation ----------------------------------------

def test_create_analysis_saves_context(client):
    res = client.post("/analyses", data={
        "title": "手入力分析",
        "top_event": "ログイン障害が発生した",
        "system_context": "  Webサーバ2台構成  ",
        "incident_context": "  9時から全ユーザー影響  ",
    }, follow_redirects=False)
    assert res.status_code == 303

    analysis_id = int(res.headers["location"].rstrip("/").split("/")[-1])
    stored = json.loads(_get_stored_context(client, analysis_id))
    assert stored["system_context"] == "Webサーバ2台構成"
    assert stored["incident_context"] == "9時から全ユーザー影響"
    assert stored["demo_points"] == ""


def test_create_analysis_without_context_keeps_legacy_behavior(client):
    res = client.post("/analyses", data={
        "title": "コンテキストなし分析",
        "top_event": "障害が発生した",
    }, follow_redirects=False)
    assert res.status_code == 303

    analysis_id = int(res.headers["location"].rstrip("/").split("/")[-1])
    assert _get_stored_context(client, analysis_id) == ""
    # Detail page still renders (empty-context state shows the add affordance).
    page = client.get(f"/analyses/{analysis_id}")
    assert page.status_code == 200
    assert "分析コンテキスト" in page.text
    assert "未入力" in page.text


# --- New-analysis form: visible fields (sample apply targets them) -----------

def test_new_analysis_form_shows_visible_context_fields(client):
    res = client.get("/analyses/new")
    assert res.status_code == 200
    # system/incident are visible labelled textareas, no longer hidden inputs.
    assert 'name="system_context"' in res.text
    assert 'name="incident_context"' in res.text
    assert "システム構成・対象範囲" in res.text
    assert "障害発生時の状況・観測事実" in res.text
    assert '<input type="hidden" id="systemContextInput"' not in res.text
    assert '<input type="hidden" id="incidentContextInput"' not in res.text
    # applySample writes into the visible fields by these ids.
    assert 'id="systemContextInput"' in res.text
    assert 'id="incidentContextInput"' in res.text
    # demo_points stays a hidden field (only filled by the sample apply).
    if "SAMPLE_SCENARIOS" in res.text:
        assert '<input type="hidden" id="demoPointsInput" name="demo_points"' in res.text
        assert "getElementById('systemContextInput').value = sample.system_context" in res.text


# --- Detail page: display ----------------------------------------------------

def test_detail_page_renders_saved_context(client):
    ctx = {
        "system_context": "認証システムはWeb2台構成",
        "incident_context": "9時から500エラー",
        "demo_points": "デモ観点X",
    }
    analysis_id = _create_analysis(
        client, analysis_context=json.dumps(ctx, ensure_ascii=False))
    res = client.get(f"/analyses/{analysis_id}")
    assert res.status_code == 200
    assert "認証システムはWeb2台構成" in res.text
    assert "9時から500エラー" in res.text
    assert "入力済み" in res.text
    # demo_points is kept server-side only, not surfaced as an input.
    assert "デモ観点X" not in res.text


def test_detail_page_safe_on_broken_context_json(client):
    analysis_id = _create_analysis(client, analysis_context="{broken json")
    res = client.get(f"/analyses/{analysis_id}")
    assert res.status_code == 200
    assert "分析コンテキスト" in res.text


# --- POST /analyses/{id}/context ---------------------------------------------

def test_update_context_trims_and_persists(client):
    analysis_id = _create_analysis(client)
    res = client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": "  新しい構成  \n",
        "incident_context": "\t新しい状況 ",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["system_context"] == "新しい構成"
    assert data["incident_context"] == "新しい状況"

    stored = json.loads(_get_stored_context(client, analysis_id))
    assert stored["system_context"] == "新しい構成"
    assert stored["incident_context"] == "新しい状況"

    # Re-display: the detail page shows the updated values.
    page = client.get(f"/analyses/{analysis_id}")
    assert "新しい構成" in page.text
    assert "新しい状況" in page.text


def test_update_context_preserves_demo_points_and_unknown_keys(client):
    ctx = {
        "system_context": "旧構成",
        "incident_context": "旧状況",
        "demo_points": "デモ観点は残す",
        "future_key": {"nested": True},
    }
    analysis_id = _create_analysis(
        client, analysis_context=json.dumps(ctx, ensure_ascii=False))

    res = client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": "新構成",
        "incident_context": "新状況",
    })
    assert res.status_code == 200

    stored = json.loads(_get_stored_context(client, analysis_id))
    assert stored["system_context"] == "新構成"
    assert stored["incident_context"] == "新状況"
    assert stored["demo_points"] == "デモ観点は残す"
    assert stored["future_key"] == {"nested": True}


def test_update_context_partial_payload_keeps_other_field(client):
    ctx = {"system_context": "構成A", "incident_context": "状況B", "demo_points": ""}
    analysis_id = _create_analysis(
        client, analysis_context=json.dumps(ctx, ensure_ascii=False))

    res = client.post(f"/analyses/{analysis_id}/context",
                      json={"system_context": "構成A2"})
    assert res.status_code == 200
    stored = json.loads(_get_stored_context(client, analysis_id))
    assert stored["system_context"] == "構成A2"
    assert stored["incident_context"] == "状況B"


def test_update_context_recovers_from_broken_json(client):
    analysis_id = _create_analysis(client, analysis_context="{broken json")
    res = client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": "復旧後の構成",
        "incident_context": "",
    })
    assert res.status_code == 200
    stored = json.loads(_get_stored_context(client, analysis_id))
    assert stored["system_context"] == "復旧後の構成"
    assert stored["incident_context"] == ""


def test_update_context_recovers_from_legacy_non_dict_json(client):
    analysis_id = _create_analysis(client, analysis_context='["legacy", "list"]')
    res = client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": "構成のみ",
        "incident_context": "",
    })
    assert res.status_code == 200
    stored = json.loads(_get_stored_context(client, analysis_id))
    assert stored["system_context"] == "構成のみ"


def test_update_context_all_empty_stores_empty_string(client):
    ctx = {"system_context": "構成", "incident_context": "状況", "demo_points": ""}
    analysis_id = _create_analysis(
        client, analysis_context=json.dumps(ctx, ensure_ascii=False))
    res = client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": "   ",
        "incident_context": "",
    })
    assert res.status_code == 200
    assert res.json()["system_context"] == ""
    # Same stored shape as an analysis created without context.
    assert _get_stored_context(client, analysis_id) == ""


def test_update_context_non_string_values_are_emptied(client):
    analysis_id = _create_analysis(client)
    res = client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": 123,
        "incident_context": None,
    })
    assert res.status_code == 200
    assert res.json() == {"success": True, "system_context": "", "incident_context": ""}
    assert _get_stored_context(client, analysis_id) == ""


def test_update_context_not_found(client):
    res = client.post("/analyses/99999/context", json={"system_context": "x"})
    assert res.status_code == 404


# --- Generation: the latest saved context reaches provider / workflow --------

class _CaptureProvider:
    def __init__(self):
        self.calls = []

    def generate_factors(self, **kwargs):
        self.calls.append(kwargs)
        return [GeneratedFactor(
            title="証明書の有効期限切れ",
            description="TLS証明書の有効期限を確認する",
            rationale="テスト", check_points=[],
        )]


def test_updated_context_is_passed_to_ai_provider(client, monkeypatch):
    analysis_id = _create_analysis(client, analysis_context=json.dumps({
        "system_context": "旧構成", "incident_context": "旧状況",
        "demo_points": "デモ観点",
    }, ensure_ascii=False))

    client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": "最新の構成",
        "incident_context": "最新の状況",
    })

    provider = _CaptureProvider()
    monkeypatch.setattr(main_module, "get_ai_provider", lambda: provider)
    monkeypatch.setenv("FTA_RETRY_BELOW_MIN", "false")

    res = client.post(f"/analyses/{analysis_id}/generate/level/1", json={})
    assert res.status_code == 200
    assert res.json()["created"] == 1

    passed = provider.calls[0]["context"]["analysis_context"]
    assert passed["system_context"] == "最新の構成"
    assert passed["incident_context"] == "最新の状況"
    assert passed["demo_points"] == "デモ観点"


def test_updated_context_is_passed_to_langgraph_workflow(client, monkeypatch):
    analysis_id = _create_analysis(client)
    parent_id = _add_yes_node(client, analysis_id, "認証基盤の問題")

    client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": "LangGraphに渡す構成",
        "incident_context": "LangGraphに渡す状況",
    })

    import app.services.generation_workflow as gw
    captured = {}

    def _capture_workflow(**kwargs):
        captured.update(kwargs)
        return gw.WorkflowResult(
            candidates=[GeneratedFactor(
                title="証明書の有効期限切れ",
                description="TLS証明書の有効期限を確認する",
                rationale="テスト", check_points=[],
            )],
            outcome="created", regenerated=False, retry_count=0,
            decision="accept",
        )

    monkeypatch.setattr(gw, "run_generation_workflow", _capture_workflow)
    monkeypatch.setenv("ENABLE_LANGGRAPH_GENERATION_WORKFLOW", "true")

    res = client.post(
        f"/analyses/{analysis_id}/generate/level/2",
        json={"parent_id": parent_id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["quality_summary"]["workflow"] == "langgraph"
    assert data["created"] == 1
    assert captured["analysis_context"]["system_context"] == "LangGraphに渡す構成"
    assert captured["analysis_context"]["incident_context"] == "LangGraphに渡す状況"


def test_generation_with_broken_context_json_passes_empty_dict(client, monkeypatch):
    analysis_id = _create_analysis(client, analysis_context="{broken json")
    provider = _CaptureProvider()
    monkeypatch.setattr(main_module, "get_ai_provider", lambda: provider)
    monkeypatch.setenv("FTA_RETRY_BELOW_MIN", "false")

    res = client.post(f"/analyses/{analysis_id}/generate/level/1", json={})
    assert res.status_code == 200
    assert res.json()["created"] == 1
    assert provider.calls[0]["context"]["analysis_context"] == {}


# --- Export regression after a context update --------------------------------

def test_exports_reflect_updated_context(client):
    analysis_id = _create_analysis(client, analysis_context=json.dumps({
        "system_context": "旧構成", "incident_context": "旧状況",
        "demo_points": "デモ観点キープ",
    }, ensure_ascii=False))
    client.post(f"/analyses/{analysis_id}/context", json={
        "system_context": "更新後の構成",
        "incident_context": "更新後の状況",
    })

    res_json = client.get(f"/analyses/{analysis_id}/export/json")
    assert res_json.status_code == 200
    exported = json.loads(res_json.text)
    assert exported["analysis_context"]["system_context"] == "更新後の構成"
    assert exported["analysis_context"]["incident_context"] == "更新後の状況"
    assert exported["analysis_context"]["demo_points"] == "デモ観点キープ"

    res_md = client.get(f"/analyses/{analysis_id}/export/markdown")
    assert res_md.status_code == 200
    headings = [line for line in res_md.text.splitlines() if line.startswith("## ")]
    assert "## 分析コンテキスト" in headings
    assert "## 分析コンテキスト（サンプルシナリオ）" not in headings
    assert "更新後の構成" in res_md.text
    assert "更新後の状況" in res_md.text


def test_export_markdown_hand_entered_context_uses_neutral_heading(client):
    analysis_id = _create_analysis(client, analysis_context=json.dumps({
        "system_context": "手入力した構成（サンプルシナリオとの比較用）",
        "incident_context": "手入力した障害状況",
        "demo_points": "",
    }, ensure_ascii=False))

    res_md = client.get(f"/analyses/{analysis_id}/export/markdown")
    assert res_md.status_code == 200
    headings = [line for line in res_md.text.splitlines() if line.startswith("## ")]
    assert "## 分析コンテキスト" in headings
    assert "## 分析コンテキスト（サンプルシナリオ）" not in headings
    assert "手入力した構成（サンプルシナリオとの比較用）" in res_md.text


def test_export_markdown_context_with_demo_points_keeps_demo_output(client):
    analysis_id = _create_analysis(client, analysis_context=json.dumps({
        "system_context": "デモ用構成",
        "incident_context": "デモ用障害状況",
        "demo_points": "確認すべきデモ観点",
    }, ensure_ascii=False))

    res_md = client.get(f"/analyses/{analysis_id}/export/markdown")
    assert res_md.status_code == 200
    headings = [line for line in res_md.text.splitlines() if line.startswith("## ")]
    assert "## 分析コンテキスト" in headings
    assert "## 分析コンテキスト（サンプルシナリオ）" not in headings
    assert "### デモ観点" in res_md.text.splitlines()
    assert "確認すべきデモ観点" in res_md.text


def test_exports_unchanged_without_context(client):
    analysis_id = _create_analysis(client)
    res_json = client.get(f"/analyses/{analysis_id}/export/json")
    assert res_json.status_code == 200
    assert json.loads(res_json.text)["analysis_context"] is None
    res_md = client.get(f"/analyses/{analysis_id}/export/markdown")
    assert res_md.status_code == 200
    headings = [line for line in res_md.text.splitlines() if line.startswith("## ")]
    assert "## 分析コンテキスト" not in headings
    assert "## 分析コンテキスト（サンプルシナリオ）" not in headings

"""
Endpoint tests for the UI/UX improvement work:

- GET /nodes/{id}: the detail modal loads the saved values from the server
  instead of resetting memo / evidence / prevention to blanks (which used to
  overwrite the stored values on save).
- POST /analyses/{id}/delete: analyses can be removed from the list page;
  child nodes are removed with them.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models, schemas
from app.database import get_db
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
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


def _add_node(client, title, *, level=1, parent_id=None, **extra):
    db = client.SessionLocal()
    try:
        node = crud.create_node(db, client.analysis_id, {
            "parent_id": parent_id,
            "level": level,
            "title": title,
            "description": f"{title}の説明",
            "ai_generated": False,
            "user_judgement": "unknown",
            "direct_cause_status": "unknown",
            "display_order": 0,
            "warning_flags": "",
            **extra,
        })
        return node.id
    finally:
        db.close()


# --- GET /nodes/{id} -------------------------------------------------------

def test_get_node_returns_all_detail_fields(client):
    node_id = _add_node(
        client, "設定ミス",
        memo="運用メモ", evidence="ログに設定変更の記録",
        prevention_idea="変更レビューを必須化",
        direct_cause_status="likely", direct_cause_comment="時系列が一致",
        warning_flags="既存要因「設定誤り」に類似",
    )
    res = client.get(f"/nodes/{node_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == node_id
    assert data["title"] == "設定ミス"
    assert data["description"] == "設定ミスの説明"
    assert data["memo"] == "運用メモ"
    assert data["evidence"] == "ログに設定変更の記録"
    assert data["prevention_idea"] == "変更レビューを必須化"
    assert data["direct_cause_status"] == "likely"
    assert data["direct_cause_comment"] == "時系列が一致"
    assert data["warning_flags"] == "既存要因「設定誤り」に類似"
    assert data["level"] == 1
    assert data["parent_id"] is None


def test_get_node_not_found(client):
    res = client.get("/nodes/99999")
    assert res.status_code == 404


def test_detail_roundtrip_preserves_saved_fields(client):
    """Loading via GET then saving the same values back must not lose data."""
    node_id = _add_node(client, "電源断", memo="重要メモ", evidence="根拠A")
    loaded = client.get(f"/nodes/{node_id}").json()
    res = client.post(f"/nodes/{node_id}/update", json={
        "title": loaded["title"],
        "description": loaded["description"],
        "memo": loaded["memo"],
        "direct_cause_status": loaded["direct_cause_status"],
        "direct_cause_comment": loaded["direct_cause_comment"],
        "evidence": loaded["evidence"],
        "prevention_idea": loaded["prevention_idea"],
    })
    assert res.status_code == 200
    after = client.get(f"/nodes/{node_id}").json()
    assert after["memo"] == "重要メモ"
    assert after["evidence"] == "根拠A"


# --- POST /analyses/{id}/delete --------------------------------------------

def test_delete_analysis_removes_analysis_and_nodes(client):
    parent_id = _add_node(client, "一次要因A")
    _add_node(client, "二次要因A1", level=2, parent_id=parent_id)

    res = client.post(f"/analyses/{client.analysis_id}/delete")
    assert res.status_code == 200
    assert res.json() == {"success": True}

    db = client.SessionLocal()
    try:
        assert crud.get_analysis(db, client.analysis_id) is None
        assert crud.get_nodes_by_analysis(db, client.analysis_id) == []
    finally:
        db.close()

    # Detail page for the deleted analysis is now a 404.
    assert client.get(f"/analyses/{client.analysis_id}").status_code == 404


def test_delete_analysis_not_found(client):
    res = client.post("/analyses/99999/delete")
    assert res.status_code == 404

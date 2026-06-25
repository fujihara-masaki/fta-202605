"""
Endpoint-level test: the /generate API response shape is unchanged and now
also carries the additive quality_summary (Step 1).

Uses the default MockAIProvider (AI_PROVIDER unset) and an isolated temp DB.
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
    monkeypatch.delenv("AI_PROVIDER", raising=False)  # default mock provider
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
        yield c

    app.dependency_overrides.clear()


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

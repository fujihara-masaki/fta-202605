"""
Route-level tests for analysis creation and the analysis-detail screen.

Focus areas (this change set):
  - normal hand-entered analysis still works (no sample fields)
  - applying a sample stores analysis_context (top_event + 3 context blocks)
  - the FTA top-event node uses the short top_event only
  - the analysis-detail screen renders the collapsible 分析コンテキスト section
  - the detail screen hides the context section for normal analyses
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client():
    # StaticPool keeps a single shared connection so the in-memory schema
    # created here is visible to every session opened during the request.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c._SessionLocal = TestingSessionLocal  # expose for assertions
        yield c
    app.dependency_overrides.clear()


def _get_analysis(client, analysis_id):
    db = client._SessionLocal()
    try:
        return db.get(models.Analysis, analysis_id)
    finally:
        db.close()


def test_normal_analysis_has_empty_context(client):
    """サンプルを利用しない通常分析は従来通り作成でき、analysis_context は空。"""
    resp = client.post(
        "/analyses",
        data={"title": "通常分析", "top_event": "システムで障害が発生した"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    analysis_id = int(resp.headers["location"].rstrip("/").split("/")[-1])

    analysis = _get_analysis(client, analysis_id)
    assert analysis.title == "通常分析"
    assert analysis.top_event == "システムで障害が発生した"
    assert (analysis.analysis_context or "") == ""


def test_sample_analysis_stores_full_context(client):
    """サンプル適用時は top_event は短文ノード、全体は analysis_context に保存される。"""
    long_system = "システム構成の長い説明。" * 10
    resp = client.post(
        "/analyses",
        data={
            "title": "サンプル分析",
            "top_event": "在宅勤務者がVPN接続後に社内業務システムへ接続できない",
            "system_context": long_system,
            "incident_context": "複数の在宅勤務者から接続できないとの連絡があった",
            "demo_points": "VPN、認証、DNS、ファイアウォールの観点",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    analysis_id = int(resp.headers["location"].rstrip("/").split("/")[-1])

    analysis = _get_analysis(client, analysis_id)
    # FTA top node uses the short top_event only — never the long context
    assert analysis.top_event == "在宅勤務者がVPN接続後に社内業務システムへ接続できない"
    assert long_system not in analysis.top_event

    ctx = json.loads(analysis.analysis_context)
    assert ctx["top_event"] == analysis.top_event
    assert ctx["system_context"] == long_system
    assert ctx["incident_context"] == "複数の在宅勤務者から接続できないとの連絡があった"
    assert ctx["demo_points"] == "VPN、認証、DNS、ファイアウォールの観点"


def test_detail_screen_shows_context_section(client):
    """サンプルから作成した分析の詳細画面で analysis_context を確認できる。"""
    resp = client.post(
        "/analyses",
        data={
            "title": "サンプル分析",
            "top_event": "VPN接続後に社内システムへ接続できない",
            "system_context": "利用者端末、VPN装置、認証基盤、社内DNSで構成される",
            "incident_context": "一部利用者で社内DNS名の名前解決に失敗している",
            "demo_points": "VPN、認証、DNS、経路制御の観点",
        },
        follow_redirects=False,
    )
    analysis_id = int(resp.headers["location"].rstrip("/").split("/")[-1])

    page = client.get(f"/analyses/{analysis_id}")
    assert page.status_code == 200
    body = page.text
    assert "分析コンテキスト" in body
    assert "利用者端末、VPN装置、認証基盤、社内DNSで構成される" in body
    assert "一部利用者で社内DNS名の名前解決に失敗している" in body
    assert "VPN、認証、DNS、経路制御の観点" in body


def test_detail_screen_hides_context_for_normal_analysis(client):
    """通常分析の詳細画面には分析コンテキストのセクションを表示しない。"""
    resp = client.post(
        "/analyses",
        data={"title": "通常分析", "top_event": "障害が発生した"},
        follow_redirects=False,
    )
    analysis_id = int(resp.headers["location"].rstrip("/").split("/")[-1])

    page = client.get(f"/analyses/{analysis_id}")
    assert page.status_code == 200
    assert "analysis-context-section" not in page.text

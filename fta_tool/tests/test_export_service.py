import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Analysis, Node
from app.services.export_service import export_json, export_csv, export_markdown
import json


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_analysis(db):
    analysis = Analysis(title="テスト分析", top_event="〇〇システムでログイン障害が発生した")
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    node1 = Node(
        analysis_id=analysis.id,
        parent_id=None,
        level=1,
        title="認証基盤に問題があった",
        description="認証システムに何らかの問題が発生した可能性",
        ai_generated=True,
        user_judgement="yes",
        direct_cause_status="unknown",
        display_order=0,
    )
    db.add(node1)
    db.commit()
    db.refresh(node1)

    node2 = Node(
        analysis_id=analysis.id,
        parent_id=node1.id,
        level=2,
        title="AD連携に失敗していた",
        description="Active Directory連携の障害の可能性",
        ai_generated=True,
        user_judgement="yes",
        direct_cause_status="likely",
        direct_cause_comment="直接的な原因の可能性が高い",
        display_order=0,
    )
    db.add(node2)
    db.commit()

    node3 = Node(
        analysis_id=analysis.id,
        parent_id=None,
        level=1,
        title="ネットワーク経路に問題があった",
        description="ネットワーク障害の可能性",
        ai_generated=True,
        user_judgement="no",
        direct_cause_status="unknown",
        display_order=1,
    )
    db.add(node3)
    db.commit()

    return analysis


def test_export_json(db, sample_analysis):
    result = export_json(db, sample_analysis.id)
    data = json.loads(result)
    assert data["title"] == "テスト分析"
    assert data["top_event"] == "〇〇システムでログイン障害が発生した"
    assert len(data["nodes"]) == 3


def test_export_csv(db, sample_analysis):
    result = export_csv(db, sample_analysis.id)
    lines = result.strip().split("\n")
    assert len(lines) >= 4  # header + 3 nodes
    assert "認証基盤に問題があった" in result
    assert "AD連携に失敗していた" in result


def test_export_markdown(db, sample_analysis):
    result = export_markdown(db, sample_analysis.id)
    assert "# FTA分析結果" in result
    assert "## 頂上事象" in result
    assert "〇〇システムでログイン障害が発生した" in result
    assert "認証基盤に問題があった" in result
    assert "[Yes]" in result
    assert "[No]" in result
    assert "## FTAツリー" in result


def test_no_duplicate_nodes(db, sample_analysis):
    """Test that duplicate node titles under the same parent are not allowed via crud."""
    from app.crud import node_title_exists
    exists = node_title_exists(db, sample_analysis.id, None, 1, "認証基盤に問題があった")
    assert exists is True
    not_exists = node_title_exists(db, sample_analysis.id, None, 1, "存在しない要因")
    assert not_exists is False

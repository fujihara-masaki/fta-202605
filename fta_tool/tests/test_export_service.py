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


def test_export_json_includes_analysis_context(db):
    ctx = {
        "system_context": "システム構成テキスト",
        "incident_context": "障害状況テキスト",
        "demo_points": "デモ観点テキスト",
    }
    analysis = Analysis(
        title="サンプル分析", top_event="サンプルの頂上事象",
        analysis_context=json.dumps(ctx, ensure_ascii=False),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    data = json.loads(export_json(db, analysis.id))
    assert data["analysis_context"] == ctx


def test_export_json_analysis_context_none_when_absent(db, sample_analysis):
    data = json.loads(export_json(db, sample_analysis.id))
    assert data["analysis_context"] is None


def test_export_markdown_includes_analysis_context(db):
    ctx = {
        "system_context": "システム構成テキスト",
        "incident_context": "障害状況テキスト",
        "demo_points": "デモ観点テキスト",
    }
    analysis = Analysis(
        title="サンプル分析", top_event="サンプルの頂上事象",
        analysis_context=json.dumps(ctx, ensure_ascii=False),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    result = export_markdown(db, analysis.id)
    assert "分析コンテキスト" in result
    assert "システム構成テキスト" in result
    assert "障害状況テキスト" in result
    assert "デモ観点テキスト" in result


def test_export_markdown_no_context_section_when_absent(db, sample_analysis):
    result = export_markdown(db, sample_analysis.id)
    assert "分析コンテキスト" not in result


def test_export_csv_unaffected_by_analysis_context(db):
    """既存のCSV列位置（親ID・要確認フラグ・警告理由含む）は変わらない。
    品質ステータス列は後方互換のため末尾にのみ追加される。"""
    ctx = {"system_context": "X", "incident_context": "Y", "demo_points": "Z"}
    analysis = Analysis(
        title="サンプル分析", top_event="サンプルの頂上事象",
        analysis_context=json.dumps(ctx, ensure_ascii=False),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    result = export_csv(db, analysis.id)
    header = result.strip().split("\n")[0]
    assert header == (
        "ID,レベル,タイトル,説明,親ID,親要因,AI生成,ユーザ評価,直接要因ステータス,"
        "直接要因コメント,根拠,再発防止策,メモ,要確認フラグ,警告理由,品質ステータス"
    )


def test_export_csv_quality_status_column(db):
    """品質ステータス列: 警告のみ / 再生成 / 再生成（警告あり）を区別できる。"""
    from app.services.factor_quality import REGENERATED_FLAG_LABEL

    analysis = Analysis(title="品質ステータス確認", top_event="頂上事象")
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    rows = [
        ("警告なし要因", ""),
        ("警告のみ要因", "既存要因「X」に類似"),
        ("再生成要因", REGENERATED_FLAG_LABEL),
        ("再生成警告要因", f"汎用的すぎる要因名; {REGENERATED_FLAG_LABEL}"),
    ]
    for i, (title, flags) in enumerate(rows):
        db.add(Node(
            analysis_id=analysis.id, parent_id=None, level=1,
            title=title, description="説明", ai_generated=True,
            user_judgement="unknown", direct_cause_status="unknown",
            display_order=i, warning_flags=flags,
        ))
    db.commit()

    lines = export_csv(db, analysis.id).strip().split("\n")
    status_by_title = {}
    import csv as _csv
    import io as _io
    for row in list(_csv.reader(_io.StringIO("\n".join(lines))))[1:]:
        status_by_title[row[2]] = row[-1]
    assert status_by_title["警告なし要因"] == ""
    assert status_by_title["警告のみ要因"] == "警告のみ"
    assert status_by_title["再生成要因"] == "再生成"
    assert status_by_title["再生成警告要因"] == "再生成（警告あり）"


def test_no_duplicate_nodes(db, sample_analysis):
    """Test that duplicate node titles under the same parent are not allowed via crud."""
    from app.crud import node_title_exists
    exists = node_title_exists(db, sample_analysis.id, None, 1, "認証基盤に問題があった")
    assert exists is True
    not_exists = node_title_exists(db, sample_analysis.id, None, 1, "存在しない要因")
    assert not_exists is False

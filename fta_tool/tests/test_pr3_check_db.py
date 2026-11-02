"""The databases for the manual check of PR-3 on Windows
(scripts/pr3_check_db.py, docs/manual-check-pr3.md).

* a folder that holds anything is refused and left as it was (the database
  the tool is normally used with is never opened);
* normal: what checks 1-10 need — an analysis without factors, three levels,
  Yes parents for ③ and ④, a quality warning, saved details; no
  inconsistent parent link; the edit screen opens;
* anomaly: every category of J-25, with the deletion answers the guide
  describes; the edit screen opens for both analyses.
"""

from __future__ import annotations

import importlib.util
import pathlib
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, detail_view
from app.database import get_db
from app.detail_view import (
    CYCLE,
    FOREIGN_PARENT,
    LEVEL_MISMATCH,
    MISSING_PARENT,
    OK,
    REASON_FOREIGN_DESCENDANT,
    SELF_PARENT,
    UPPER,
)
from app.main import app

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "pr3_check_db.py"
FACTOR_COUNTS = {"1": 4, "2": 3, "3": 2, "additional": 2}


@pytest.fixture()
def script():
    spec = importlib.util.spec_from_file_location("pr3_check_db", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def made(script, kind: str, folder: pathlib.Path):
    db, path = script.new_database(folder)
    try:
        result = script.BUILDERS[kind](db)
    finally:
        db.close()
    session_factory = sessionmaker(bind=create_engine(f"sqlite:///{path}"))
    return result, session_factory


def view_of(session_factory, analysis_id: int) -> detail_view.DetailView:
    db = session_factory()
    try:
        analysis = crud.get_analysis(db, analysis_id)
        nodes = crud.get_nodes_by_analysis(db, analysis_id)
        links = detail_view.CrossAnalysisLinks(*crud.get_cross_analysis_links(db, analysis_id))
        return detail_view.build_detail_view(analysis, nodes, links, factor_counts=FACTOR_COUNTS)
    finally:
        db.close()


def pages_open(session_factory, analysis_ids) -> list[int]:
    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            return [client.get(f"/analyses/{analysis_id}").status_code for analysis_id in analysis_ids]
    finally:
        app.dependency_overrides.clear()


def test_a_folder_that_holds_anything_is_refused(script, tmp_path):
    folder = tmp_path / "used"
    folder.mkdir()
    existing = folder / "fta_tool.db"
    existing.write_bytes(b"the usual database")
    with pytest.raises(SystemExit):
        script.main(["normal", str(folder)])
    with pytest.raises(SystemExit):
        script.main(["anomaly", str(folder)])
    assert existing.read_bytes() == b"the usual database"
    assert [p.name for p in folder.iterdir()] == ["fta_tool.db"]


def test_the_command_makes_a_new_folder(script, tmp_path, capsys):
    folder = tmp_path / "new" / "pr3-normal"
    assert script.main(["normal", str(folder)]) == 0
    assert [p.name for p in folder.iterdir()] == ["fta_tool.db"]
    out = capsys.readouterr().out
    assert f"作成しました：{folder.resolve() / 'fta_tool.db'}" in out
    assert "分析 ID 1：PR3確認：要因なし" in out and "分析 ID 2：PR3確認：三次まで" in out


def test_normal_database_has_what_the_checks_need(script, tmp_path):
    result, session_factory = made(script, "normal", tmp_path / "pr3-normal")
    empty, full = result["analyses"]["要因なし"], result["analyses"]["三次まで"]

    assert view_of(session_factory, empty).nodes == []
    view = view_of(session_factory, full)
    assert {v.kind for v in view.nodes} == {OK}
    assert not view.anomalies
    assert Counter(v.level for v in view.nodes) == {1: 20, 2: 10, 3: 7}
    assert view.targets[2]["count"] == 3 and view.targets[2]["excluded"] == 0
    assert view.targets[3]["count"] == 3 and view.targets[3]["excluded"] == 0
    factors = result["factors"]
    assert view.by_id[factors["二次01-2"]].warning_text == script.WARNING_TEXT
    assert [v.id for v in view.nodes if v.warning_text] == [factors["二次01-2"]]
    assert view.by_id[factors["一次01"]].has_memo
    assert all(v.delete_allowed for v in view.nodes)
    assert pages_open(session_factory, (empty, full)) == [200, 200]


def test_anomaly_database_has_every_category(script, tmp_path):
    result, session_factory = made(script, "anomaly", tmp_path / "pr3-anomaly")
    main, other = result["analyses"]["不整合"], result["analyses"]["別の分析"]
    ids = result["factors"]

    view = view_of(session_factory, main)
    by = view.by_id
    assert {v.kind for v in view.nodes} == {OK, UPPER, SELF_PARENT, CYCLE, FOREIGN_PARENT,
                                             MISSING_PARENT, LEVEL_MISMATCH}
    assert by[ids["親不在"]].kind == MISSING_PARENT
    assert by[ids["別分析の親"]].kind == FOREIGN_PARENT
    assert by[ids["自己参照"]].kind == SELF_PARENT
    assert by[ids["循環P"]].kind == CYCLE and by[ids["循環Q"]].kind == CYCLE
    assert by[ids["階層不一致"]].kind == LEVEL_MISMATCH
    for key in ("親不在の下", "別分析の親の下", "循環の下"):
        assert by[ids[key]].kind == UPPER, key

    # Deletion as the guide describes it (判断2).
    assert by[ids["親不在"]].delete_allowed
    assert by[ids["親不在"]].delete_scope == 2  # the factor and the one below it
    for key in ("正常な二次", "正常な一次"):
        assert not by[ids[key]].delete_allowed, key
        assert by[ids[key]].delete_reason == REASON_FOREIGN_DESCENDANT, key
    for key in ("別分析の親", "自己参照", "循環P", "循環Q", "階層不一致"):
        assert not by[ids[key]].delete_allowed, key

    other_view = view_of(session_factory, other)
    assert other_view.by_id[ids["別の分析から付く"]].kind == FOREIGN_PARENT
    assert pages_open(session_factory, (main, other)) == [200, 200]

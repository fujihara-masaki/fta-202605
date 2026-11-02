"""S-11 regression tests: the delete APIs check the scope on the server
(docs/pr8-s11-s12-options.md section 6; plan section 11 S-11).

``POST /analyses/{id}/delete`` and ``POST /nodes/{id}/delete`` walk what the
delete would remove (crud.check_delete_scope) and refuse it with HTTP 409 and
a Japanese reason — changing nothing — when a factor of another analysis is
in the scope (directly or further below), a factor names itself as parent,
parent links loop, or the walk cannot be completed. A normal delete removes
exactly what it removed before; a missing target is still 404.

Every test makes its data in a temporary SQLite database of its own (never
the user's); broken links are written directly. "Changes nothing" is checked
on a full dump of both tables (every column of every row). The requests on
looping data are sent from a child process with a time limit
(tests/guarded_requests.py), so a delete that does not end cannot stop the
test run. The real-browser checks that the reason reaches the list and edit
screens are tests/e2e/test_s11_s12_refusals.py (S11-DELETE-REFUSED).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import crud, models, schemas
from app.database import get_db
from app.main import app
from tests import guarded_requests


class Env:
    def __init__(self, engine, session_factory, client, tmp_path):
        self.engine = engine
        self.Session = session_factory
        self.client = client
        self.tmp_path = tmp_path
        self.db_path = tmp_path / "s11.db"
        self._count = 0

    def analysis(self, title: str = "分析") -> int:
        db = self.Session()
        try:
            return crud.create_analysis(db, schemas.AnalysisCreate(title=title, top_event="頂上事象")).id
        finally:
            db.close()

    def node(self, analysis_id: int, level: int, parent_id=None, *, title=None) -> int:
        self._count += 1
        values = {
            "analysis_id": analysis_id, "parent_id": parent_id, "level": level,
            "title": title or f"要因{self._count}", "description": "", "ai_generated": False,
            "user_judgement": "unknown", "direct_cause_status": "unknown", "display_order": 0,
            "memo": "", "warning_flags": "",
        }
        with self.engine.begin() as conn:
            return conn.execute(models.Node.__table__.insert().values(**values)).inserted_primary_key[0]

    def set_parent(self, node_id: int, parent_id) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE nodes SET parent_id = :p WHERE id = :id"), {"p": parent_id, "id": node_id})

    def ids(self, analysis_id=None) -> set[int]:
        sql = "SELECT id FROM nodes" + ("" if analysis_id is None else " WHERE analysis_id = :a")
        with self.engine.connect() as conn:
            return {row[0] for row in conn.execute(text(sql), {"a": analysis_id})}

    def analyses(self) -> set[int]:
        with self.engine.connect() as conn:
            return {row[0] for row in conn.execute(text("SELECT id FROM analyses"))}

    def dump(self) -> tuple:
        """Every row of both tables, every column."""
        with self.engine.connect() as conn:
            return (
                tuple(tuple(r) for r in conn.execute(text("SELECT * FROM analyses ORDER BY id"))),
                tuple(tuple(r) for r in conn.execute(text("SELECT * FROM nodes ORDER BY id"))),
            )

    def guarded(self, *urls: str) -> list[dict]:
        """POST each url from a child process with a time limit."""
        result = guarded_requests.run(self.tmp_path / "child", self.db_path, [{"url": u} for u in urls])
        return result.responses


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    engine = create_engine(f"sqlite:///{tmp_path / 's11.db'}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Env(engine, session_factory, client, tmp_path)
    app.dependency_overrides.clear()
    engine.dispose()


def refused(response, reason: str) -> None:
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": reason}


# ----- normal deletes and 404 (unchanged) ------------------------------------

def test_S11_node_delete_removes_exactly_the_subtree(env):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    second = env.node(a, 2, root)
    third = env.node(a, 3, second)
    sibling = env.node(a, 2, root)
    other = env.node(b, 1)
    before = env.ids()

    response = env.client.post(f"/nodes/{second}/delete")
    assert response.status_code == 200 and response.json() == {"success": True}
    assert before - env.ids() == {second, third}
    assert {root, sibling, other} <= env.ids()


def test_S11_analysis_delete_removes_the_analysis_and_all_its_factors_only(env):
    a = env.analysis("A")
    b = env.analysis("B")
    r1 = env.node(a, 1)
    r2 = env.node(a, 2, r1)
    env.node(a, 3, r2)
    env.node(a, 1)
    missing = env.node(a, 2, 99999)  # a missing parent does not block the analysis delete
    env.node(a, 3, missing)
    kept = {env.node(b, 1), env.node(b, 2, 99998)}
    db = env.Session()
    try:
        listed = crud.count_nodes_by_analysis(db)[a]  # the count the list's dialog shows
    finally:
        db.close()

    response = env.client.post(f"/analyses/{a}/delete")
    assert response.status_code == 200 and response.json() == {"success": True}
    assert env.analyses() == {b}
    assert env.ids(a) == set() and env.ids() == kept
    assert listed == 6


def test_S11_analysis_without_factors_is_deleted(env):
    a = env.analysis("空")
    assert env.client.post(f"/analyses/{a}/delete").status_code == 200
    assert a not in env.analyses()


def test_S11_missing_targets_are_still_404(env):
    a = env.analysis("A")
    env.node(a, 1)
    before = env.dump()
    response = env.client.post("/nodes/987654/delete")
    assert response.status_code == 404 and response.json() == {"detail": "ノードが見つかりません"}
    response = env.client.post("/analyses/987654/delete")
    assert response.status_code == 404 and response.json() == {"detail": "分析が見つかりません"}
    assert env.dump() == before


# ----- a factor of another analysis in the scope ------------------------------

def test_S11_node_delete_refused_for_a_direct_descendant_of_another_analysis(env):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    middle = env.node(a, 2, root)
    env.node(a, 3, middle)
    env.node(b, 3, middle)  # B's factor whose parent is A's middle
    before = env.dump()

    for target in (middle, root):
        refused(env.client.post(f"/nodes/{target}/delete"), crud.delete_reason_foreign("node", 1))
        assert env.dump() == before


def test_S11_node_delete_refused_for_an_indirect_descendant_of_another_analysis(env):
    a = env.analysis("A")
    b = env.analysis("B")
    c = env.analysis("C")
    root = env.node(a, 1)
    middle = env.node(a, 2, root)
    leaf = env.node(a, 3, middle)
    b1 = env.node(b, 1, leaf)  # B below A's grandchild …
    env.node(b, 2, b1)         # … with a child of its own in B
    env.node(c, 3, b1)         # … and one in C
    safe = env.node(a, 1)
    before = env.dump()

    for target in (leaf, middle, root):
        refused(env.client.post(f"/nodes/{target}/delete"), crud.delete_reason_foreign("node", 3))
        assert env.dump() == before
    # The factor of B itself lies in B with only descendants of B and C: its
    # own analysis is B, so C's factor below blocks it.
    refused(env.client.post(f"/nodes/{b1}/delete"), crud.delete_reason_foreign("node", 1))
    assert env.dump() == before
    assert env.client.post(f"/nodes/{safe}/delete").status_code == 200  # the rest still works


def test_S11_analysis_delete_refused_for_direct_and_indirect_descendants_elsewhere(env):
    x = env.analysis("X")
    y = env.analysis("Y")
    x1 = env.node(x, 1)
    x2 = env.node(x, 2, x1)
    y_direct = env.node(y, 2, x1)
    env.node(y, 3, y_direct)       # indirect: below Y's factor below X
    env.node(y, 1)                 # unrelated factor of Y
    before = env.dump()

    refused(env.client.post(f"/analyses/{x}/delete"), crud.delete_reason_foreign("analysis", 2))
    assert env.dump() == before

    # Only the deeper link left: still refused, nothing changes.
    env.set_parent(y_direct, x2)
    before = env.dump()
    refused(env.client.post(f"/analyses/{x}/delete"), crud.delete_reason_foreign("analysis", 2))
    assert env.dump() == before
    assert env.analyses() == {x, y}


# ----- self-reference and cycles (child process with a time limit) -------------

def test_S11_self_reference_is_refused_for_both_deletes(env):
    a = env.analysis("A")
    keep = env.node(a, 1)
    self_ref = env.node(a, 2)
    env.set_parent(self_ref, self_ref)
    env.node(a, 3, self_ref)
    before = env.dump()

    node, analysis = env.guarded(f"/nodes/{self_ref}/delete", f"/analyses/{a}/delete")
    assert node == {"status": 409, "body": {"detail": crud.delete_reason_self_parent("node")}}
    assert analysis == {"status": 409, "body": {"detail": crud.delete_reason_self_parent("analysis")}}
    assert env.dump() == before
    assert keep in env.ids()


def test_S11_cycles_are_refused_for_both_deletes(env):
    a = env.analysis("A")
    b = env.analysis("B")
    p = env.node(a, 2)
    q = env.node(a, 1, p)
    env.set_parent(p, q)                 # p ⇄ q
    r = env.node(a, 3, p)                # below the cycle
    u = env.node(a, 1)
    v = env.node(a, 2, u)
    w = env.node(a, 3, v)
    env.set_parent(u, w)                 # u → w → v → u: three factors
    other = env.node(b, 1)
    before = env.dump()

    responses = env.guarded(f"/nodes/{p}/delete", f"/nodes/{q}/delete", f"/nodes/{v}/delete",
                            f"/analyses/{a}/delete")
    for response in responses[:3]:
        assert response == {"status": 409, "body": {"detail": crud.delete_reason_cycle("node")}}
    assert responses[3] == {"status": 409, "body": {"detail": crud.delete_reason_cycle("analysis")}}
    assert env.dump() == before

    # A factor below the cycle (not on it) is deleted with exactly its subtree.
    response = env.client.post(f"/nodes/{r}/delete")
    assert response.status_code == 200
    assert env.ids() == {p, q, u, v, w, other}


def test_S11_a_cycle_across_analyses_is_refused(env):
    x = env.analysis("X")
    y = env.analysis("Y")
    x1 = env.node(x, 1)
    y1 = env.node(y, 2, x1)
    env.set_parent(x1, y1)  # X's factor and Y's factor name each other
    before = env.dump()

    node, analysis = env.guarded(f"/nodes/{x1}/delete", f"/analyses/{x}/delete")
    assert node == {"status": 409, "body": {"detail": crud.delete_reason_cycle("node")}}
    assert analysis == {"status": 409, "body": {"detail": crud.delete_reason_cycle("analysis")}}
    assert env.dump() == before


# ----- the walk cannot be completed ---------------------------------------------

def test_S11_a_walk_that_cannot_be_completed_is_refused(env, monkeypatch):
    a = env.analysis("A")
    root = env.node(a, 1)
    middle = env.node(a, 2, root)
    leaf = env.node(a, 3, middle)
    before = env.dump()

    # Fault injection: the walk may visit two factors.
    monkeypatch.setattr(crud, "_delete_scope_limit", lambda db: 2)
    refused(env.client.post(f"/nodes/{root}/delete"), crud.DELETE_REASON_INCOMPLETE)
    refused(env.client.post(f"/analyses/{a}/delete"), crud.DELETE_REASON_INCOMPLETE)
    assert env.dump() == before
    assert env.client.post(f"/nodes/{middle}/delete").status_code == 200  # two factors: completed
    assert env.ids() == {root} and leaf not in env.ids()


def test_S11_failed_lookups_are_refused(env, monkeypatch):
    a = env.analysis("A")
    root = env.node(a, 1)
    before = env.dump()

    def fail(db):
        raise OperationalError("SELECT count(*) FROM nodes", {}, Exception("injected"))

    monkeypatch.setattr(crud, "_delete_scope_limit", fail)
    refused(env.client.post(f"/nodes/{root}/delete"), crud.DELETE_REASON_LOOKUP_FAILED)
    refused(env.client.post(f"/analyses/{a}/delete"), crud.DELETE_REASON_LOOKUP_FAILED)
    assert env.dump() == before


# ----- data changed between the check and the delete -----------------------------

@pytest.mark.parametrize("change", ["child_same_analysis", "child_other_analysis", "loop"])
def test_S11_a_change_between_the_check_and_the_delete_is_refused(env, monkeypatch, change):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    middle = env.node(a, 2, root)
    original = crud.check_delete_scope

    def check_then_change(db, analysis_id, target, node_id=None):
        scope = original(db, analysis_id, target, node_id=node_id)
        # Another request commits right after the check (another connection).
        if change == "child_same_analysis":
            env.node(a, 3, middle)
        elif change == "child_other_analysis":
            env.node(b, 3, middle)
        else:
            env.set_parent(root, middle)
        return scope

    monkeypatch.setattr(crud, "check_delete_scope", check_then_change)
    response = env.client.post(f"/nodes/{root}/delete")
    refused(response, crud.DELETE_REASON_CHANGED)
    assert {root, middle} <= env.ids()          # nothing of the checked scope was removed
    assert len(env.ids()) == (2 if change == "loop" else 3)


def test_S11_a_factor_added_to_the_analysis_after_the_check_is_refused(env, monkeypatch):
    a = env.analysis("A")
    env.node(a, 1)
    original = crud.check_delete_scope

    def check_then_add(db, analysis_id, target, node_id=None):
        scope = original(db, analysis_id, target, node_id=node_id)
        env.node(a, 1, title="確認の後に追加された要因")
        return scope

    monkeypatch.setattr(crud, "check_delete_scope", check_then_add)
    refused(env.client.post(f"/analyses/{a}/delete"), crud.DELETE_REASON_CHANGED)
    assert a in env.analyses() and len(env.ids(a)) == 2


# ----- the reasons ------------------------------------------------------------------

def test_S11_reasons_are_japanese_and_say_nothing_was_deleted():
    reasons = [
        crud.delete_reason_foreign("node", 1), crud.delete_reason_foreign("analysis", 2),
        crud.delete_reason_self_parent("node"), crud.delete_reason_self_parent("analysis"),
        crud.delete_reason_cycle("node"), crud.delete_reason_cycle("analysis"),
        crud.DELETE_REASON_INCOMPLETE, crud.DELETE_REASON_LOOKUP_FAILED, crud.DELETE_REASON_CHANGED,
    ]
    assert all("何も削除していません。" in reason for reason in reasons)
    assert crud.delete_reason_foreign("node", 1) == (
        "この要因の子孫に別の分析の要因が1件含まれます。削除すると別の分析の要因も削除されるため、何も削除していません。")
    assert crud.delete_reason_foreign("analysis", 2).startswith("この分析の要因の子孫に別の分析の要因が2件含まれます。")

"""T-07 (plan 8.9): parent-link categories, walks that always end, and when
the edit screen offers 削除 (J-25, plan 5.9.5; the user's decisions of
2026-09-29, 判断2・判断3).

Every test builds its data in a temporary SQLite database of its own (an
isolated test database, never the user's). Broken parent links cannot be
made through the API, so they are inserted directly.

What is checked:

* each category is told apart: missing parent, parent in another analysis,
  self-reference, cycle, level mismatch (every variant), and 「上位に不整合
  あり」 below each of them; walks over cyclic data end, and every factor is
  placed exactly once, never deeper than three levels;
* deletion is offered only for a consistent factor, a missing-parent factor
  or one with an inconsistent ancestor, and only when the whole subtree the
  delete API would remove was walked (no depth limit), stays inside the
  analysis and has no factor of another analysis anywhere below — directly
  or deeper; the ancestors of such a factor are not offered either. A walk
  that cannot be completed, or lookups that failed, mean no deletion; after
  failed lookups the page still opens from the factors already read (none
  is read again, one removed meanwhile does not make it fail);
* for the deletable categories, the existing delete API removes exactly the
  factor and its descendants (the scope the screen computed), also when
  level-mismatched factors are among the descendants (the user's additional
  decision of 2026-09-29); those factors are never offered themselves;
* how the existing delete API behaves where the screen does not offer
  deletion (a factor of another analysis below; self-reference; cycle) is
  recorded as the current behaviour, not as a guarantee: the API itself is
  not changed and not made safe by these checks;
* generation / manual-add parents exclude inconsistent factors and those
  with an inconsistent ancestor;
* the lookups are two queries whatever the number of factors.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app import crud, detail_view, models, schemas
from app.database import get_db
from app.detail_view import (
    CYCLE,
    FOREIGN_PARENT,
    LEVEL_MISMATCH,
    MISSING_PARENT,
    OK,
    SELF_PARENT,
    UNVERIFIED_PARENT,
    UPPER,
)
from app.main import app

FACTOR_COUNTS = {"1": 4, "2": 3, "3": 2, "additional": 2}


class Env:
    def __init__(self, engine, session_factory, client):
        self.engine = engine
        self.Session = session_factory
        self.client = client
        self._count = 0

    def analysis(self, title: str = "分析") -> int:
        db = self.Session()
        try:
            return crud.create_analysis(db, schemas.AnalysisCreate(title=title, top_event="頂上事象")).id
        finally:
            db.close()

    def node(self, analysis_id: int, level: int, parent_id=None, *, title=None, judgement="unknown") -> int:
        self._count += 1
        values = {
            "analysis_id": analysis_id,
            "parent_id": parent_id,
            "level": level,
            "title": title or f"要因{self._count}",
            "description": "",
            "ai_generated": False,
            "user_judgement": judgement,
            "direct_cause_status": "unknown",
            "display_order": 0,
            "memo": "",
            "warning_flags": "",
        }
        with self.engine.begin() as conn:
            result = conn.execute(models.Node.__table__.insert().values(**values))
            return result.inserted_primary_key[0]

    def set_parent(self, node_id: int, parent_id) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE nodes SET parent_id = :p WHERE id = :id"), {"p": parent_id, "id": node_id})

    def ids(self) -> set[int]:
        with self.engine.connect() as conn:
            return {row[0] for row in conn.execute(text("SELECT id FROM nodes"))}

    def view(self, analysis_id: int, *, scope_limit=None) -> detail_view.DetailView:
        db = self.Session()
        try:
            analysis = crud.get_analysis(db, analysis_id)
            nodes = crud.get_nodes_by_analysis(db, analysis_id)
            parents, children = crud.get_cross_analysis_links(db, analysis_id)
            links = detail_view.CrossAnalysisLinks(parents, children)
            return detail_view.build_detail_view(
                analysis, nodes, links, factor_counts=FACTOR_COUNTS, scope_limit=scope_limit)
        finally:
            db.close()

    def delete(self, node_id: int) -> int:
        return self.client.post(f"/nodes/{node_id}/delete").status_code


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    engine = create_engine(f"sqlite:///{tmp_path / 'integrity.db'}", connect_args={"check_same_thread": False})
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
        yield Env(engine, session_factory, client)
    app.dependency_overrides.clear()
    engine.dispose()


def displayed(view: detail_view.DetailView) -> list[tuple[int, int]]:
    """(id, depth) of every factor as the screen places it."""
    found = []

    def walk(items, depth):
        for item in items:
            found.append((item.id, depth))
            walk(item.children, depth + 1)

    walk(view.roots + view.anomalies, 1)
    return found


# ----- categories -------------------------------------------------------------

def test_T07_every_category_is_told_apart(env):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    second = env.node(a, 2, root)
    third = env.node(a, 3, second)
    missing = env.node(a, 2, 99999)
    below_missing = env.node(a, 3, missing)
    other = env.node(b, 1)
    foreign = env.node(a, 2, other)
    below_foreign = env.node(a, 3, foreign)
    self_ref = env.node(a, 2)
    env.set_parent(self_ref, self_ref)
    below_self = env.node(a, 3, self_ref)
    p = env.node(a, 2)
    q = env.node(a, 1, p)
    env.set_parent(p, q)  # p (二次) -> q (一次) -> p
    below_cycle = env.node(a, 2, q)
    skipped = env.node(a, 3, root)  # 三次 directly below 一次
    below_skipped = env.node(a, 3, skipped)  # 三次 below 三次: also a level mismatch
    no_parent = env.node(a, 2)
    odd = env.node(a, 5)
    level1_with_parent = env.node(a, 1, root)
    level1_missing = env.node(a, 1, 88888)

    view = env.view(a)
    kind = {v.id: v.kind for v in view.nodes}
    label = {v.id: v.label for v in view.nodes}

    assert kind[root] == kind[second] == kind[third] == OK
    assert (kind[missing], label[missing]) == (MISSING_PARENT, "（親が見つかりません：ID 99999）")
    assert (kind[foreign], label[foreign]) == (FOREIGN_PARENT, f"（別の分析の要因を親にしています：ID {other}）")
    assert (kind[self_ref], label[self_ref]) == (SELF_PARENT, "（自分自身を親にしています）")
    assert kind[p] == kind[q] == CYCLE
    assert label[p] == label[q] == "（親子関係が循環しています）"
    assert view.by_id[q].issues == (CYCLE, LEVEL_MISMATCH)  # 一次要因 with a parent as well
    assert (kind[skipped], label[skipped]) == (LEVEL_MISMATCH, "（階層が合いません：親は一次）")
    assert (kind[below_skipped], label[below_skipped]) == (LEVEL_MISMATCH, "（階層が合いません：親は三次）")
    assert (kind[no_parent], label[no_parent]) == (LEVEL_MISMATCH, "（階層が合いません：親がありません）")
    assert (kind[odd], label[odd]) == (LEVEL_MISMATCH, "（階層が合いません：階層5）")
    assert label[level1_with_parent] == "（階層が合いません：一次要因に親があります）"
    assert view.by_id[level1_missing].issues == (MISSING_PARENT, LEVEL_MISMATCH)

    # Consistent itself, below an inconsistent ancestor: 「上位に不整合あり」,
    # shown under the nearest inconsistent ancestor.
    for below, ancestor in ((below_missing, missing), (below_foreign, foreign),
                            (below_self, self_ref), (below_cycle, q)):
        assert kind[below] == UPPER
        assert view.by_id[below].anomaly_root == ancestor
        assert label[below] == "（上位の要因の親子関係に不整合があります）"
        assert [child.id for child in view.by_id[ancestor].children] == [below]

    # Never the top event: the table's parent column names the problem (C-09).
    assert view.by_id[missing].parent_display == "（親が見つかりません：ID 99999）"
    assert view.by_id[root].parent_display == "（頂上事象）"
    assert view.by_id[below_missing].parent_display == view.by_id[missing].title
    assert [v.id for v in view.roots] == [root]
    assert {v.id for v in view.anomalies} == {
        missing, foreign, self_ref, p, q, skipped, below_skipped, no_parent, odd,
        level1_with_parent, level1_missing,
    }
    assert view.anomaly_count == len(view.anomalies) + 4  # plus the four 「上位に不整合あり」


def test_T07_walks_end_and_every_factor_is_placed_once(env):
    a = env.analysis("A")
    root = env.node(a, 1)
    # A long cycle, a self-reference and a two-factor cycle.
    ring = [env.node(a, 2) for _ in range(6)]
    for index, node_id in enumerate(ring):
        env.set_parent(node_id, ring[(index + 1) % len(ring)])
    lone = env.node(a, 3)
    env.set_parent(lone, lone)
    x = env.node(a, 2)
    y = env.node(a, 2, x)
    env.set_parent(x, y)
    # A chain deeper than three levels (each link a level mismatch).
    chain = [root]
    for _ in range(8):
        chain.append(env.node(a, 3, chain[-1]))

    view = env.view(a)
    placed = displayed(view)
    assert sorted(node_id for node_id, _ in placed) == sorted(v.id for v in view.nodes)
    assert max(depth for _, depth in placed) <= 3
    assert {v.id for v in view.nodes if v.kind == CYCLE} == set(ring) | {x, y}
    assert view.by_id[lone].kind == SELF_PARENT

    # The page itself renders (the old template until the screen is migrated).
    assert env.client.get(f"/analyses/{a}").status_code == 200


def test_T07_deletion_walk_reports_loops_instead_of_running_forever():
    children = {1: [2], 2: [3], 3: [1]}
    assert detail_view.deletion_scope(1, children, {}, limit=100) is None
    assert detail_view.deletion_scope(7, {7: [7]}, {}, limit=100) is None  # self-reference
    assert detail_view.deletion_scope(1, {1: [2, 3]}, {3: (9,)}, limit=100) == (3, 1)


# ----- deletion: offered ------------------------------------------------------

def test_T07_consistent_factors_are_deletable_with_their_whole_subtree(env):
    a = env.analysis("A")
    root = env.node(a, 1)
    second = env.node(a, 2, root)
    third = env.node(a, 3, second)
    sibling = env.node(a, 1)

    view = env.view(a)
    assert view.by_id[root].delete_allowed and view.by_id[root].delete_scope == 3
    assert view.by_id[third].delete_allowed and view.by_id[third].delete_scope == 1
    assert all(v.delete_reason == "" for v in view.nodes)

    before = env.ids()
    assert env.delete(second) == 200
    assert before - env.ids() == {second, third}
    assert sibling in env.ids()


def test_T07_missing_parent_is_deletable_and_the_api_removes_exactly_its_subtree(env):
    a = env.analysis("A")
    keep = env.node(a, 1)
    missing = env.node(a, 2, 99999)
    child = env.node(a, 3, missing)
    # A level-mismatched descendant is part of the same subtree.
    grandchild = env.node(a, 3, child)

    view = env.view(a)
    assert view.by_id[missing].kind == MISSING_PARENT
    assert view.by_id[missing].delete_allowed
    assert view.by_id[missing].delete_scope == 3
    assert not view.by_id[grandchild].delete_allowed  # itself a level mismatch

    before = env.ids()
    assert env.delete(missing) == 200
    assert before - env.ids() == {missing, child, grandchild}
    assert keep in env.ids()


@pytest.mark.parametrize("ancestor_kind", ["missing", "foreign", "self", "cycle", "level"])
def test_T07_below_an_inconsistent_ancestor_is_deletable_and_removes_only_its_subtree(env, ancestor_kind):
    a = env.analysis("A")
    b = env.analysis("B")
    top = env.node(a, 1)
    if ancestor_kind == "missing":
        ancestor = env.node(a, 1, 99999)  # 一次 with a missing parent (also a level mismatch)
    elif ancestor_kind == "foreign":
        ancestor = env.node(a, 1, env.node(b, 1))
    elif ancestor_kind == "self":
        ancestor = env.node(a, 1)
        env.set_parent(ancestor, ancestor)
    elif ancestor_kind == "cycle":
        partner = env.node(a, 2)
        ancestor = env.node(a, 1, partner)
        env.set_parent(partner, ancestor)
    else:
        ancestor = env.node(a, 1, top)  # 一次 with a parent
    below = env.node(a, 2, ancestor)
    below_child = env.node(a, 3, below)

    view = env.view(a)
    assert view.by_id[below].kind == UPPER
    assert view.by_id[below].delete_allowed and view.by_id[below].delete_scope == 2
    assert not view.by_id[ancestor].delete_allowed
    assert view.by_id[ancestor].delete_reason == detail_view.REASON_NOT_VERIFIED

    before = env.ids()
    assert env.delete(below) == 200
    assert before - env.ids() == {below, below_child}
    assert ancestor in env.ids()


def test_T07_level_mismatch_descendants_go_with_a_deletable_factor_and_nothing_else(env):
    # The user's additional decision of 2026-09-29 (with the approval to open
    # the PR): a factor whose own category is deletable (consistent, 上位に
    # 不整合あり, missing parent) may be deleted with level-mismatched factors
    # among its descendants, when every descendant was walked and none belongs
    # to another analysis; the mismatched factors are never offered themselves,
    # and an incomplete walk or a factor of another analysis below still takes
    # the offer away (failed lookups: test_T07_failed_lookups_...).
    a = env.analysis("A")
    b = env.analysis("B")
    r = env.node(a, 1)  # consistent 一次
    r_child = env.node(a, 2, r)
    r_grandchild = env.node(a, 3, r_child)
    r_mismatch = env.node(a, 3, r)  # 三次 below a 一次
    r_mismatch_child = env.node(a, 3, r_mismatch)  # 三次 below a 三次
    m = env.node(a, 2, 99999)  # missing parent
    m_mismatch = env.node(a, 2, m)  # 二次 below a 二次
    m_upper = env.node(a, 3, m_mismatch)  # its own link is consistent
    m_deep = env.node(a, 3, m_upper)  # 三次 below a 三次, four levels below m
    z = env.node(a, 1, 99998)  # 一次 with a missing parent: never deletable
    u = env.node(a, 2, z)  # 上位に不整合あり
    u_mismatch = env.node(a, 2, u)  # 二次 below a 二次
    r4 = env.node(a, 1)  # consistent, but a factor of B hangs below its mismatch
    x4 = env.node(a, 3, r4)
    stranger = env.node(b, 3, x4)
    keep = env.node(a, 1)
    keep_child = env.node(a, 2, keep)
    other_root = env.node(b, 1)
    other_child = env.node(b, 2, other_root)

    view = env.view(a)
    scopes = {
        r: {r, r_child, r_grandchild, r_mismatch, r_mismatch_child},
        m: {m, m_mismatch, m_upper, m_deep},
        u: {u, u_mismatch},
    }
    assert (view.by_id[r].kind, view.by_id[m].kind, view.by_id[u].kind) == (OK, MISSING_PARENT, UPPER)
    for start, scope in scopes.items():
        assert view.by_id[start].delete_allowed, start
        assert view.by_id[start].delete_scope == len(scope), start
    # The level-mismatched factors (and Z) are not deletable themselves.
    for node_id in (r_mismatch, r_mismatch_child, m_mismatch, m_deep, u_mismatch, x4, z):
        assert LEVEL_MISMATCH in view.by_id[node_id].issues, node_id
        assert not view.by_id[node_id].delete_allowed, node_id
        assert view.by_id[node_id].delete_reason == detail_view.REASON_NOT_VERIFIED
    # A factor of another analysis below a mismatched descendant blocks the start.
    assert not view.by_id[r4].delete_allowed
    assert view.by_id[r4].delete_reason == detail_view.REASON_FOREIGN_DESCENDANT
    # So does a walk that cannot see every descendant.
    limited = env.view(a, scope_limit=4)
    assert not limited.by_id[r].delete_allowed
    assert limited.by_id[r].delete_reason == detail_view.REASON_SCOPE_INCOMPLETE

    # The unchanged delete API removes exactly the scope the screen computed.
    before = env.ids()
    for start, scope in scopes.items():
        current = env.ids()
        assert env.delete(start) == 200
        assert current - env.ids() == scope, start
    assert before - env.ids() == set().union(*scopes.values())
    assert {z, r4, x4, stranger, keep, keep_child, other_root, other_child} <= env.ids()


# ----- deletion: not offered ---------------------------------------------------

def test_T07_categories_the_plan_keeps_undeletable_stay_undeletable(env):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    self_ref = env.node(a, 2)
    env.set_parent(self_ref, self_ref)
    p = env.node(a, 2)
    q = env.node(a, 1, p)
    env.set_parent(p, q)
    foreign = env.node(a, 2, env.node(b, 1))
    skipped = env.node(a, 3, root)
    no_parent = env.node(a, 2)
    odd = env.node(a, 0)
    level1_missing = env.node(a, 1, 99999)

    view = env.view(a)
    for node_id in (self_ref, p, q, foreign, skipped, no_parent, odd, level1_missing):
        assert not view.by_id[node_id].delete_allowed, node_id
        assert view.by_id[node_id].delete_reason == detail_view.REASON_NOT_VERIFIED


def test_T07_existing_delete_api_on_self_reference_and_cycle_is_recorded_not_relied_on(env):
    # Current behaviour of the unchanged API (the screen never sends these):
    # the ORM refuses the circular delete, the request fails and nothing is
    # removed. Recorded as a fact, not as a safety guarantee.
    a = env.analysis("A")
    self_ref = env.node(a, 2)
    env.set_parent(self_ref, self_ref)
    p = env.node(a, 2)
    q = env.node(a, 1, p)
    env.set_parent(p, q)
    before = env.ids()
    assert env.delete(self_ref) == 500
    assert env.delete(p) == 500
    assert env.ids() == before


def test_T07_a_factor_of_another_analysis_directly_below_blocks_it_and_its_ancestors(env):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    middle = env.node(a, 2, root)
    leaf = env.node(a, 3, middle)
    sibling = env.node(a, 2, root)
    other_root = env.node(a, 1)
    stranger = env.node(b, 3, middle)  # a factor of B whose parent is A's middle

    view = env.view(a)
    for node_id in (middle, root):
        assert not view.by_id[node_id].delete_allowed, node_id
        assert view.by_id[node_id].delete_reason == detail_view.REASON_FOREIGN_DESCENDANT
    # The factor itself is consistent: no exception for that.
    assert view.by_id[middle].kind == OK and view.by_id[root].kind == OK
    for node_id in (leaf, sibling, other_root):
        assert view.by_id[node_id].delete_allowed, node_id

    # Why: the unchanged delete API follows parent_id into the other analysis
    # (recorded current behaviour; the screen does not send this request).
    assert env.delete(middle) == 200
    assert stranger not in env.ids()


def test_T07_a_factor_of_another_analysis_deeper_below_blocks_every_ancestor(env):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    middle = env.node(a, 2, root)
    leaf = env.node(a, 3, middle)
    env.node(b, 3, leaf)  # below the grandchild of root

    view = env.view(a)
    for node_id in (leaf, middle, root):
        assert not view.by_id[node_id].delete_allowed, node_id
        assert view.by_id[node_id].delete_reason == detail_view.REASON_FOREIGN_DESCENDANT


def test_T07_the_walk_is_not_cut_at_the_display_depth(env):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    chain = [root]
    for _ in range(6):  # six levels below root, each link a level mismatch
        chain.append(env.node(a, 3, chain[-1]))

    view = env.view(a)
    assert view.by_id[root].delete_allowed
    assert view.by_id[root].delete_scope == 7  # the whole chain, beyond depth 3

    env.node(b, 3, chain[-1])  # a factor of B below the deepest link
    view = env.view(a)
    assert not view.by_id[root].delete_allowed
    assert view.by_id[root].delete_reason == detail_view.REASON_FOREIGN_DESCENDANT


def test_T07_other_analysis_below_a_missing_parent_or_upper_factor_blocks_them(env):
    a = env.analysis("A")
    b = env.analysis("B")
    missing = env.node(a, 2, 99999)
    below = env.node(a, 3, missing)
    env.node(b, 3, below)

    view = env.view(a)
    assert view.by_id[below].kind == UPPER
    for node_id in (missing, below):
        assert not view.by_id[node_id].delete_allowed
        assert view.by_id[node_id].delete_reason == detail_view.REASON_FOREIGN_DESCENDANT


def test_T07_a_walk_that_cannot_be_completed_means_no_deletion(env):
    a = env.analysis("A")
    root = env.node(a, 1)
    middle = env.node(a, 2, root)
    leaf = env.node(a, 3, middle)

    view = env.view(a, scope_limit=2)  # fault injection: the walk may visit two factors
    assert not view.by_id[root].delete_allowed
    assert view.by_id[root].delete_reason == detail_view.REASON_SCOPE_INCOMPLETE
    assert view.by_id[middle].delete_allowed and view.by_id[leaf].delete_allowed

    view = env.view(a, scope_limit=0)
    assert not any(v.delete_allowed for v in view.nodes)
    assert {v.delete_reason for v in view.nodes} == {detail_view.REASON_SCOPE_INCOMPLETE}


def test_T07_failed_lookups_mean_no_deletion_and_the_page_still_opens(env, monkeypatch):
    a = env.analysis("A")
    b = env.analysis("B")
    root = env.node(a, 1)
    foreign = env.node(a, 2, env.node(b, 1))

    def fail(db, analysis_id):
        raise RuntimeError("lookup failed (test)")

    monkeypatch.setattr(crud, "get_cross_analysis_links", fail)
    db = env.Session()
    try:
        analysis = crud.get_analysis(db, a)
        view = main_module._edit_view(db, analysis, crud.get_nodes_by_analysis(db, a))
    finally:
        db.close()
    assert view.lookups_ok is False and view.data["lookupsOk"] is False
    assert not any(v.delete_allowed for v in view.nodes)
    assert {v.delete_reason for v in view.nodes} == {detail_view.REASON_LOOKUP_FAILED}
    # A parent outside the analysis cannot be told apart without the lookup.
    assert view.by_id[foreign].kind == UNVERIFIED_PARENT
    assert view.by_id[root].kind == OK
    assert env.client.get(f"/analyses/{a}").status_code == 200



def test_T07_failed_lookups_do_not_read_the_factors_again(env, monkeypatch):
    """After failed lookups the page is built from the factors already read:
    none is read again one by one, and one removed meanwhile (another tab)
    does not turn the page into an error."""
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    small = env.analysis("小")
    env.node(small, 1)
    large = env.analysis("大")
    root = env.node(large, 1)
    for _ in range(30):
        env.node(large, 2, root)
    removed = env.node(large, 2, root)

    def fail(db, analysis_id):
        if analysis_id == large:  # removed after the factors were read
            other = env.Session()
            try:
                other.query(models.Node).filter(models.Node.id == removed).delete()
                other.commit()
            finally:
                other.close()
        raise RuntimeError("lookup failed (test)")

    monkeypatch.setattr(crud, "get_cross_analysis_links", fail)
    counts = []
    event.listen(env.engine, "before_cursor_execute", record)
    try:
        for analysis_id in (small, large):
            statements.clear()
            response = env.client.get(f"/analyses/{analysis_id}")
            assert response.status_code == 200, response.text[:300]
            counts.append(sum(1 for s in statements
                              if s.lstrip().upper().startswith("SELECT") and "nodes" in s))
    finally:
        event.remove(env.engine, "before_cursor_execute", record)
    assert counts[0] == counts[1], counts

# ----- parents of generation and manual add (判断3) ------------------------------

def test_T07_generation_parents_exclude_inconsistent_factors(env):
    a = env.analysis("A")
    yes1 = env.node(a, 1, judgement="yes")
    yes2 = env.node(a, 1, judgement="yes")
    no1 = env.node(a, 1, judgement="no")
    level2 = env.node(a, 2, yes1, judgement="yes")
    level3 = env.node(a, 3, level2, judgement="yes")
    broken = env.node(a, 1, yes2, judgement="yes")  # 一次 with a parent
    below_broken = env.node(a, 2, broken, judgement="yes")  # 上位に不整合あり
    missing = env.node(a, 2, 99999, judgement="yes")

    view = env.view(a)
    for node_id in (yes1, yes2, no1, level2):
        assert view.by_id[node_id].can_parent, node_id  # No / unevaluated parents stay usable
    assert not view.by_id[level3].can_parent
    assert view.by_id[level3].parent_reason == detail_view.PARENT_REASON_LEVEL3
    for node_id in (broken, below_broken, missing):
        assert not view.by_id[node_id].can_parent
        assert view.by_id[node_id].parent_reason == detail_view.PARENT_REASON_INCONSISTENT
    # Yes parents usable for the next level vs excluded as inconsistent.
    assert view.targets[2] == {"count": 2, "excluded": 1}
    assert view.targets[3] == {"count": 1, "excluded": 2}


# ----- the lookups ------------------------------------------------------------------

def test_T07_lookups_are_two_queries_whatever_the_number_of_factors(env):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    a = env.analysis("A")
    b = env.analysis("B")
    few = [env.node(a, 1)]
    many_analysis = env.analysis("C")
    parent = env.node(many_analysis, 1)
    for _ in range(60):
        env.node(many_analysis, 2, parent)
    env.node(many_analysis, 2, 77777)
    env.node(b, 2, few[0])

    event.listen(env.engine, "before_cursor_execute", record)
    try:
        for analysis_id in (a, many_analysis):
            statements.clear()
            db = env.Session()
            try:
                parents, children = crud.get_cross_analysis_links(db, analysis_id)
            finally:
                db.close()
            selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
            assert len(selects) == 2, selects
    finally:
        event.remove(env.engine, "before_cursor_execute", record)

    db = env.Session()
    try:
        parents, children = crud.get_cross_analysis_links(db, a)
    finally:
        db.close()
    assert parents == {}
    assert list(children) == [few[0]]


def test_T07_the_edit_page_asks_the_same_number_of_queries_whatever_the_size(env):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    small = env.analysis("小")
    env.node(small, 1)
    large = env.analysis("大")
    root = env.node(large, 1)
    for index in range(40):
        middle = env.node(large, 2, root)
        env.node(large, 3, middle)
    env.node(large, 2, 55555)  # a missing parent: the lookups still run once

    counts = []
    event.listen(env.engine, "before_cursor_execute", record)
    try:
        for analysis_id in (small, large):
            statements.clear()
            assert env.client.get(f"/analyses/{analysis_id}").status_code == 200
            counts.append(sum(1 for s in statements if s.lstrip().upper().startswith("SELECT")))
    finally:
        event.remove(env.engine, "before_cursor_execute", record)
    assert counts[0] == counts[1], counts

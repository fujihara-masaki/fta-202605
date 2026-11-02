"""S-12 regression tests: the parent path of generation always ends
(docs/pr8-s11-s12-options.md section 6; plan section 11 S-12).

``POST /analyses/{id}/generate/level/{n}`` builds the path from each parent
up to its 一次要因 recording what it visited, at most PARENT_PATH_LIMIT
factors (app/main.py _parent_path). Until S-12 a parent on a cycle or below
one made the request never end (measured on 254f826: no answer within 20
seconds).

* With parent_id: a parent that names itself, lies on a cycle or below one,
  or whose path exceeds the limit is refused in the existing failure form
  (success false, message, created 0, skipped 0, …) — the AI is not called
  and no factor is created. Not a 409.
* Without parent_id (二次・三次): Yes parents with an inconsistent link or
  ancestor (as on the edit screen, detail_view.inconsistent_ids) are left
  out; the others are generated as before. With every parent left out the
  answer names the reason and the number left out.
* Normal parents, the counts, the quality check, additional generation and
  the LangGraph workflow are unchanged.

Every test uses a temporary SQLite database of its own and a stub AI that
records its calls (no real LLM). Requests on looping data are sent from a
child process with a time limit (tests/guarded_requests.py), so a request
that does not end fails the test without stopping the run; pure walks run in
a daemon thread with a time limit.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app import crud, detail_view, models, schemas
from app.database import get_db
from app.main import (
    PARENT_PATH_LIMIT,
    PATH_PROBLEM_CYCLE,
    PATH_PROBLEM_LIMIT,
    PATH_PROBLEM_SELF,
    _parent_path,
    app,
)
from app.services.ai_provider import GeneratedFactor
from tests import guarded_requests

WALK_TIMEOUT = 5  # seconds for a pure walk on looping data


def ends_within(fn, seconds: float = WALK_TIMEOUT):
    """fn() in a daemon thread; fail if it has not returned in time."""
    box: dict = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        pytest.fail(f"{seconds} 秒以内に終わりませんでした")
    if "error" in box:
        raise box["error"]
    return box["value"]


class RecordingStub:
    def __init__(self):
        self.calls: list[dict] = []

    def generate_factors(self, **kwargs):
        self.calls.append({"parent_factor": kwargs.get("parent_factor"), "parent_path": kwargs.get("parent_path"),
                           "additional": (kwargs.get("context") or {}).get("additional")})
        n = len(self.calls)
        return [GeneratedFactor(title=f"{base}（{n}）", description="スタブの説明", rationale="stub", check_points=[])
                for base in guarded_requests.STUB_TITLES]


class Env:
    def __init__(self, engine, session_factory, client, tmp_path, stub):
        self.engine = engine
        self.Session = session_factory
        self.client = client
        self.tmp_path = tmp_path
        self.db_path = tmp_path / "s12.db"
        self.stub = stub
        self._count = 0
        self._children = 0

    def analysis(self, title: str = "分析") -> int:
        db = self.Session()
        try:
            return crud.create_analysis(db, schemas.AnalysisCreate(title=title, top_event="ログインできない")).id
        finally:
            db.close()

    def node(self, analysis_id: int, level: int, parent_id=None, *, title=None, judgement="yes") -> int:
        self._count += 1
        values = {
            "analysis_id": analysis_id, "parent_id": parent_id, "level": level,
            "title": title or f"親候補{self._count}", "description": "", "ai_generated": False,
            "user_judgement": judgement, "direct_cause_status": "unknown", "display_order": 0,
            "memo": "", "warning_flags": "",
        }
        with self.engine.begin() as conn:
            return conn.execute(models.Node.__table__.insert().values(**values)).inserted_primary_key[0]

    def set_parent(self, node_id: int, parent_id) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE nodes SET parent_id = :p WHERE id = :id"), {"p": parent_id, "id": node_id})

    def dump(self) -> tuple:
        with self.engine.connect() as conn:
            return tuple(tuple(r) for r in conn.execute(text("SELECT * FROM nodes ORDER BY id")))

    def children(self, parent_id) -> list[str]:
        with self.engine.connect() as conn:
            return [r[0] for r in conn.execute(
                text("SELECT title FROM nodes WHERE parent_id = :p ORDER BY id"), {"p": parent_id})]

    def generate(self, analysis_id: int, level: int, **body):
        return self.client.post(f"/analyses/{analysis_id}/generate/level/{level}", json=body)

    def guarded(self, analysis_id: int, level: int, bodies: list[dict], **kwargs):
        """The requests from a child process with a time limit."""
        self._children += 1
        url = f"/analyses/{analysis_id}/generate/level/{level}"
        return guarded_requests.run(self.tmp_path / f"child{self._children}", self.db_path,
                                    [{"url": url, "json": body} for body in bodies], **kwargs)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    for name, value in guarded_requests.PINNED_ENV.items():
        monkeypatch.setenv(name, value)
    engine = create_engine(f"sqlite:///{tmp_path / 's12.db'}", connect_args={"check_same_thread": False})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    stub = RecordingStub()
    monkeypatch.setattr(main_module, "get_ai_provider", lambda: stub)
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield Env(engine, session_factory, client, tmp_path, stub)
    app.dependency_overrides.clear()
    engine.dispose()


def refused_message(title: str, problem: str) -> str:
    return (f"指定された親要因「{title}」は親子関係に不整合があるため（{problem}）、"
            "この親の下には要因を生成できません。AIは呼び出さず、要因は作成していません。")


def expect_refused(response: dict, parent_id: int, title: str, problem: str) -> None:
    assert response["status"] == 200
    assert response["body"] == {
        "success": False,
        "message": refused_message(title, problem),
        "created": 0,
        "skipped": 0,
        "elapsed_ms": 0,
        "parent_id": parent_id,
        "excluded_parents": 1,
    }


# ----- the walk (pure) ----------------------------------------------------------

def _n(node_id, parent_id, title=None):
    return SimpleNamespace(id=node_id, parent_id=parent_id, title=title or f"N{node_id}")


def test_S12_parent_path_of_normal_parents_is_unchanged():
    nodes = {1: _n(1, None, "一次"), 2: _n(2, 1, "二次"), 3: _n(3, 2, "三次")}
    assert _parent_path(nodes[1], nodes) == (["一次"], None)
    assert _parent_path(nodes[2], nodes) == (["一次", "二次"], None)
    assert _parent_path(nodes[3], nodes) == (["一次", "二次", "三次"], None)  # three factors: the limit itself
    # A parent outside the analysis ends the path, as before (S-1 is not S-12).
    outside = {5: _n(5, 999, "親が分析の外")}
    assert _parent_path(outside[5], outside) == (["親が分析の外"], None)
    assert PARENT_PATH_LIMIT == 3


def test_S12_parent_path_detects_self_reference_cycles_and_the_limit():
    nodes = {
        1: _n(1, 1),            # self-reference
        2: _n(2, 1),            # below a self-reference
        3: _n(3, 4), 4: _n(4, 3),  # 3 ⇄ 4
        5: _n(5, 3),            # below the cycle
        6: _n(6, 7), 7: _n(7, 8), 8: _n(8, 9), 9: _n(9, None),  # four factors, no loop
    }
    assert ends_within(lambda: _parent_path(nodes[1], nodes)) == (None, PATH_PROBLEM_SELF)
    assert ends_within(lambda: _parent_path(nodes[2], nodes)) == (None, PATH_PROBLEM_SELF)
    assert ends_within(lambda: _parent_path(nodes[3], nodes)) == (None, PATH_PROBLEM_CYCLE)
    assert ends_within(lambda: _parent_path(nodes[5], nodes)) == (None, PATH_PROBLEM_CYCLE)
    assert ends_within(lambda: _parent_path(nodes[6], nodes)) == (None, PATH_PROBLEM_LIMIT)
    long_cycle = {i: _n(i, i % 50 + 1) for i in range(1, 51)}  # 50 factors in one loop
    assert ends_within(lambda: _parent_path(long_cycle[1], long_cycle)) == (None, PATH_PROBLEM_LIMIT)


def test_S12_inconsistent_ids_match_the_edit_screen():
    def node(node_id, parent_id, level):
        return SimpleNamespace(id=node_id, parent_id=parent_id, level=level, title=f"N{node_id}",
                               description="", user_judgement="yes", direct_cause_status="unknown",
                               ai_generated=False, warning_flags="", memo="")

    nodes = [node(1, None, 1), node(2, 1, 2), node(3, 3, 1), node(4, 3, 2), node(5, 6, 1), node(6, 5, 2),
             node(7, 999, 1), node(8, None, 2), node(9, 7, 2)]
    found = ends_within(lambda: detail_view.inconsistent_ids(nodes))
    assert found == {3, 4, 5, 6, 7, 8, 9}
    view = detail_view.build_detail_view(SimpleNamespace(id=1), nodes, detail_view.CrossAnalysisLinks({}, {}),
                                         factor_counts={})
    assert {v.id for v in view.nodes if not v.can_parent and v.level < 3} == found


# ----- with parent_id ---------------------------------------------------------------

def test_S12_normal_parents_generate_as_before(env):
    a = env.analysis()
    p = env.node(a, 1, title="認証サーバーの障害")
    q = env.node(a, 2, p, title="証明書の期限切れ")

    second = env.generate(a, 2, parent_id=p).json()
    third = env.generate(a, 3, parent_id=q).json()
    additional = env.generate(a, 3, parent_id=q, additional=True).json()
    for body in (second, third, additional):
        assert body["success"] is True and body["created"] == 2, body
        assert "excluded_parents" not in body
        assert set(body) == {"success", "message", "created", "skipped", "elapsed_ms", "parent_id", "quality_summary"}
    assert second["message"] == "2件の要因を生成しました"
    assert [c["parent_path"] for c in env.stub.calls] == [
        ["認証サーバーの障害"], ["認証サーバーの障害", "証明書の期限切れ"], ["認証サーバーの障害", "証明書の期限切れ"]]
    assert env.stub.calls[2]["additional"] is True
    assert len(env.children(p)) == 3 and len(env.children(q)) == 4


def test_S12_existing_failure_forms_are_unchanged(env):
    a = env.analysis()
    body = env.generate(a, 2, parent_id=987654).json()
    assert body == {"success": False, "message": "生成対象の親要因がありません（Yes評価の要因がありません）",
                    "created": 0, "skipped": 0, "elapsed_ms": 0, "parent_id": 987654}
    body = env.generate(a, 2).json()  # no Yes parent at all
    assert body["message"] == "生成対象の親要因がありません（Yes評価の要因がありません）"
    assert "excluded_parents" not in body
    assert env.stub.calls == []


def test_S12_a_path_over_the_limit_is_refused_without_the_ai(env):
    a = env.analysis()
    top = env.node(a, 1, title="最上位")
    upper = env.node(a, 1, top, title="一次の下の一次")
    middle = env.node(a, 2, upper, title="中間")
    parent = env.node(a, 2, middle, title="上限を超える親")
    before = env.dump()

    result = env.guarded(a, 3, [{"parent_id": parent}, {"parent_id": parent, "additional": True}])
    for response in result.responses:
        expect_refused(response, parent, "上限を超える親", PATH_PROBLEM_LIMIT)
    assert result.ai_calls == [] and env.dump() == before


def test_S12_self_reference_parent_is_refused_without_the_ai(env):
    a = env.analysis()
    good = env.node(a, 1, title="正常な親")
    self_ref = env.node(a, 1, title="自己参照の親")
    env.set_parent(self_ref, self_ref)
    below = env.node(a, 2, self_ref, title="自己参照の下の親")
    before = env.dump()

    result = env.guarded(a, 2, [{"parent_id": self_ref}, {"parent_id": self_ref, "additional": True}])
    result3 = env.guarded(a, 3, [{"parent_id": below}])
    for response in result.responses:
        expect_refused(response, self_ref, "自己参照の親", PATH_PROBLEM_SELF)
    expect_refused(result3.responses[0], below, "自己参照の下の親", PATH_PROBLEM_SELF)
    assert result.ai_calls == [] and result3.ai_calls == []
    assert env.dump() == before
    assert env.generate(a, 2, parent_id=good).json()["created"] == 2  # the analysis still works


def test_S12_parents_on_and_below_a_cycle_are_refused_without_the_ai(env):
    a = env.analysis()
    p = env.node(a, 1, title="循環上の一次")
    q = env.node(a, 2, p, title="循環上の二次")
    env.set_parent(p, q)  # p ⇄ q
    r = env.node(a, 2, p, title="循環の下の二次")
    before = env.dump()

    on_cycle = env.guarded(a, 3, [{"parent_id": q}, {"parent_id": q, "additional": True}])
    for response in on_cycle.responses:
        expect_refused(response, q, "循環上の二次", PATH_PROBLEM_CYCLE)
    level2 = env.guarded(a, 2, [{"parent_id": p}])
    expect_refused(level2.responses[0], p, "循環上の一次", PATH_PROBLEM_CYCLE)
    below = env.guarded(a, 3, [{"parent_id": r}])
    expect_refused(below.responses[0], r, "循環の下の二次", PATH_PROBLEM_CYCLE)
    assert on_cycle.ai_calls == level2.ai_calls == below.ai_calls == []
    assert env.dump() == before


def test_S12_cycle_is_refused_with_the_langgraph_workflow_on(env):
    a = env.analysis()
    p = env.node(a, 1, title="循環上の一次")
    q = env.node(a, 2, p, title="循環上の二次")
    env.set_parent(p, q)
    before = env.dump()

    result = env.guarded(a, 3, [{"parent_id": q}],
                         env_overrides={"ENABLE_LANGGRAPH_GENERATION_WORKFLOW": "true",
                                        "ENABLE_LANGGRAPH_QUALITY_GATE": "true"})
    expect_refused(result.responses[0], q, "循環上の二次", PATH_PROBLEM_CYCLE)
    assert result.ai_calls == [] and env.dump() == before


# ----- without parent_id -------------------------------------------------------------

def test_S12_without_parent_id_normal_parents_are_all_generated_as_before(env):
    a = env.analysis()
    p1 = env.node(a, 1, title="正常な一次A")
    p2 = env.node(a, 1, title="正常な一次B")
    env.node(a, 1, title="Noの一次", judgement="no")

    body = env.generate(a, 2).json()
    assert body["success"] is True and body["created"] == 4
    assert body["message"] == "4件の要因を生成しました"
    assert "excluded_parents" not in body
    assert [c["parent_factor"] for c in env.stub.calls] == ["正常な一次A", "正常な一次B"]
    assert len(env.children(p1)) == 2 and len(env.children(p2)) == 2


def test_S12_without_parent_id_inconsistent_parents_are_left_out(env):
    a = env.analysis()
    b = env.analysis("別の分析")
    good = env.node(a, 1, title="正常な一次")
    self_ref = env.node(a, 1, title="自己参照の一次")
    env.set_parent(self_ref, self_ref)
    c1 = env.node(a, 1, title="循環上の一次")
    c2 = env.node(a, 2, c1, title="循環上の二次", judgement="no")
    env.set_parent(c1, c2)
    env.node(a, 1, env.node(b, 1, title="別の分析の一次"), title="別分析を親にする一次")
    env.node(a, 1, judgement="no", title="Noの一次")
    before = env.dump()

    result = env.guarded(a, 2, [{}])
    body = result.responses[0]["body"]
    assert result.responses[0]["status"] == 200
    assert body["success"] is True and body["created"] == 2
    assert body["excluded_parents"] == 3
    assert body["message"] == "2件の要因を生成しました（親子関係に不整合がある親要因3件は対象外にしました）"
    assert [c["parent_factor"] for c in result.ai_calls] == ["正常な一次"]
    after = env.dump()
    created = [row for row in after if row not in before]
    assert len(after) == len(before) + 2 and set(before) <= set(after)
    assert {row[2] for row in created} == {good}  # nothing below an excluded parent


def test_S12_without_parent_id_parents_below_an_inconsistent_ancestor_are_left_out(env):
    a = env.analysis()
    p = env.node(a, 1, title="正常な一次", judgement="no")
    ok = env.node(a, 2, p, title="正常な二次")
    s = env.node(a, 1, title="自己参照の一次", judgement="no")
    env.set_parent(s, s)
    upper = env.node(a, 2, s, title="上位に不整合ありの二次")
    c1 = env.node(a, 1, title="循環の一次", judgement="no")
    c2 = env.node(a, 2, c1, title="循環上の二次")
    env.set_parent(c1, c2)
    below = env.node(a, 2, c1, title="循環の下の二次")
    before = env.dump()

    result = env.guarded(a, 3, [{}])
    body = result.responses[0]["body"]
    assert body["success"] is True and body["created"] == 2 and body["excluded_parents"] == 3
    assert [c["parent_factor"] for c in result.ai_calls] == ["正常な二次"]
    assert [c["parent_path"] for c in result.ai_calls] == [["正常な一次", "正常な二次"]]
    created = [row for row in env.dump() if row not in before]
    assert len(created) == 2 and {row[2] for row in created} == {ok}
    assert {upper, c2, below}.isdisjoint({row[2] for row in created})


def test_S12_without_parent_id_all_parents_left_out_names_the_reason_and_count(env):
    a = env.analysis()
    self_ref = env.node(a, 1, title="自己参照の一次")
    env.set_parent(self_ref, self_ref)
    c1 = env.node(a, 1, title="循環上の一次")
    c2 = env.node(a, 2, c1, title="循環上の二次")
    env.set_parent(c1, c2)
    before = env.dump()

    result = env.guarded(a, 2, [{}, {"additional": True}])
    for response in result.responses:
        assert response["status"] == 200
        assert response["body"] == {
            "success": False,
            "message": ("生成対象の親要因がありません：Yes評価の一次要因2件は、"
                        "すべて親子関係に不整合があるため対象外にしました（AIは呼び出していません）。"),
            "created": 0, "skipped": 0, "elapsed_ms": 0, "parent_id": None, "excluded_parents": 2,
        }
    level3 = env.guarded(a, 3, [{}])
    assert level3.responses[0]["body"]["excluded_parents"] == 1
    assert "Yes評価の二次要因1件は" in level3.responses[0]["body"]["message"]
    assert result.ai_calls == level3.ai_calls == []
    assert env.dump() == before

from datetime import datetime
from typing import Iterable, Literal, Optional
from sqlalchemy import func, select
from sqlalchemy.exc import CircularDependencyError, SQLAlchemyError
from sqlalchemy.orm import Session
from . import models, schemas
from .detail_view import nodes_on_cycles


def get_analyses(db: Session):
    return db.query(models.Analysis).order_by(models.Analysis.updated_at.desc()).all()


def count_nodes_by_analysis(db: Session) -> dict[int, int]:
    """Number of factors per analysis, in one grouped query.

    Used by the list page's delete confirmation (the count is the value at
    the time the list was rendered). Analyses without factors are absent.
    """
    rows = (
        db.query(models.Node.analysis_id, func.count(models.Node.id))
        .group_by(models.Node.analysis_id)
        .all()
    )
    return {analysis_id: count for analysis_id, count in rows}


def get_analysis(db: Session, analysis_id: int):
    return db.query(models.Analysis).filter(models.Analysis.id == analysis_id).first()


def create_analysis(db: Session, analysis: schemas.AnalysisCreate):
    db_analysis = models.Analysis(
        title=analysis.title,
        top_event=analysis.top_event,
        analysis_context=analysis.analysis_context,
    )
    db.add(db_analysis)
    db.commit()
    db.refresh(db_analysis)
    return db_analysis


def update_title(db: Session, analysis_id: int, title: str):
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db_analysis.title = title
        db_analysis.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_analysis)
    return db_analysis


def update_top_event(db: Session, analysis_id: int, top_event: str):
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db_analysis.top_event = top_event
        db_analysis.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_analysis)
    return db_analysis


def update_analysis_context(db: Session, analysis_id: int, analysis_context: str):
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db_analysis.analysis_context = analysis_context
        db_analysis.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_analysis)
    return db_analysis


def delete_analysis(db: Session, analysis_id: int):
    """Delete the analysis with all its factors and their descendants.

    S-11: the scope is checked first (check_delete_scope); a refused delete
    raises DeleteRefused and changes nothing. None if there is no analysis.
    """
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        scope = check_delete_scope(db, analysis_id, "analysis")
        db.delete(db_analysis)
        _commit_checked_delete(db, scope, analysis_id=analysis_id)
    return db_analysis


def get_nodes_by_analysis(db: Session, analysis_id: int):
    return (
        db.query(models.Node)
        .filter(models.Node.analysis_id == analysis_id)
        .order_by(models.Node.level, models.Node.display_order, models.Node.id)
        .all()
    )


def get_cross_analysis_links(db: Session, analysis_id: int):
    """Links between this analysis's factors and factors of other analyses.

    Read-only; always exactly two queries, whatever the number of factors
    (the edit screen's parent-link check, J-25 / plan 5.9.5):

    1. parents elsewhere — id, analysis_id of the factors that factors of
       this analysis name as parent but that belong to another analysis:
       ``WHERE analysis_id != :id AND id IN (SELECT parent_id FROM nodes
       WHERE analysis_id = :id AND parent_id IS NOT NULL)``
    2. children elsewhere — id, parent_id of the factors of other analyses
       whose parent is a factor of this analysis:
       ``WHERE analysis_id != :id AND parent_id IN (SELECT id FROM nodes
       WHERE analysis_id = :id)``

    Returns ({parent id: its analysis id}, {factor id: (child ids elsewhere)}).
    """
    Node = models.Node
    own_parent_ids = select(Node.parent_id).where(
        Node.analysis_id == analysis_id, Node.parent_id.is_not(None))
    parent_rows = (
        db.query(Node.id, Node.analysis_id)
        .filter(Node.analysis_id != analysis_id, Node.id.in_(own_parent_ids))
        .all()
    )
    own_ids = select(Node.id).where(Node.analysis_id == analysis_id)
    child_rows = (
        db.query(Node.id, Node.parent_id)
        .filter(Node.analysis_id != analysis_id, Node.parent_id.in_(own_ids))
        .order_by(Node.id)
        .all()
    )
    children: dict[int, list[int]] = {}
    for child_id, parent_id in child_rows:
        children.setdefault(parent_id, []).append(child_id)
    return (
        {node_id: owner for node_id, owner in parent_rows},
        {parent_id: tuple(ids) for parent_id, ids in children.items()},
    )


def get_node(db: Session, node_id: int):
    return db.query(models.Node).filter(models.Node.id == node_id).first()


def create_node(db: Session, analysis_id: int, node_data: dict) -> models.Node:
    db_node = models.Node(
        analysis_id=analysis_id,
        **node_data,
    )
    db.add(db_node)
    db.commit()
    db.refresh(db_node)
    # update analysis updated_at
    analysis = get_analysis(db, analysis_id)
    if analysis:
        analysis.updated_at = datetime.utcnow()
        db.commit()
    return db_node


def update_node(db: Session, node_id: int, update_data: schemas.NodeUpdate):
    db_node = get_node(db, node_id)
    if db_node:
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(db_node, key, value)
        db_node.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_node)
    return db_node


def delete_node(db: Session, node_id: int):
    """Delete the factor and its descendants.

    S-11: the scope is checked first (check_delete_scope); a refused delete
    raises DeleteRefused and changes nothing. None if there is no factor.
    """
    db_node = get_node(db, node_id)
    if db_node:
        scope = check_delete_scope(db, db_node.analysis_id, "node", node_id=db_node.id)
        db.delete(db_node)
        _commit_checked_delete(db, scope)
    return db_node


# ----- S-11: the scope of a delete, checked on the server ---------------------
#
# The ORM removes a factor together with every factor whose parent_id leads to
# it (models.Node.children, cascade "all, delete-orphan"), in any analysis, and
# an analysis together with all its factors and theirs. Before S-11 a delete
# therefore also removed factors of other analyses hanging below (HTTP 200),
# and failed with HTTP 500 on a self-reference or a cycle. Now the scope is
# walked first, without a depth limit and recording what was visited, and the
# delete is refused (DeleteRefused → HTTP 409 with the reason) when
#
#   * a factor of another analysis is in the scope,
#   * a factor in the scope names itself as parent, or parent links in the
#     scope form a cycle,
#   * the walk cannot be completed (more factors than the table holds, or the
#     lookups fail).
#
# The delete itself then runs in the same session: the ORM's cascade must mark
# exactly the factors that were checked, and after the DELETE statements (the
# write lock of SQLite is held from then until the commit) no factor may be
# left whose parent, or (analysis delete) whose analysis, was deleted. If the
# data changed between the check and the delete so that either fails, the
# transaction is rolled back and the delete refused as well. Not covered: a
# change committed after this delete (e.g. a factor added below a factor that
# no longer exists: S-1), and repairing inconsistent data.

DELETE_SCOPE_CHUNK = 500  # ids per IN (...) query, below SQLite's variable limit

_SUBJECT = {"node": "この要因", "analysis": "この分析"}
_DONE = "何も削除していません。"


def delete_reason_foreign(target: str, count: int) -> str:
    owner = "この要因の子孫" if target == "node" else "この分析の要因の子孫"
    return (f"{owner}に別の分析の要因が{count}件含まれます。"
            f"削除すると別の分析の要因も削除されるため、{_DONE}")


def delete_reason_self_parent(target: str) -> str:
    return (f"{_SUBJECT[target]}と一緒に削除される範囲に、自分自身を親にしている要因があります（親子関係の不整合）。"
            f"安全に削除できないため、{_DONE}")


def delete_reason_cycle(target: str) -> str:
    return (f"{_SUBJECT[target]}と一緒に削除される範囲で、親子関係が循環しています（親子関係の不整合）。"
            f"安全に削除できないため、{_DONE}")


DELETE_REASON_INCOMPLETE = f"削除される範囲をすべて確認できませんでした。安全に削除できないため、{_DONE}"
DELETE_REASON_LOOKUP_FAILED = f"削除される範囲を確認するための情報を取得できませんでした。安全に削除できないため、{_DONE}"
DELETE_REASON_CHANGED = (f"確認の途中で削除される範囲が変わりました。{_DONE}"
                         "画面を再読み込みしてから、もう一度操作してください。")


class DeleteRefused(Exception):
    """The delete was refused and nothing was changed (HTTP 409)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _chunks(ids: list[int]) -> Iterable[list[int]]:
    for start in range(0, len(ids), DELETE_SCOPE_CHUNK):
        yield ids[start:start + DELETE_SCOPE_CHUNK]


def _delete_scope_limit(db: Session) -> int:
    """At most this many factors can be in a scope: every factor there is.

    A walk that would visit more has met data changing under it and is not
    completed. (A separate function so tests can inject a smaller limit.)
    """
    return db.query(func.count(models.Node.id)).scalar() or 0


def check_delete_scope(db: Session, analysis_id: int, target: Literal["node", "analysis"],
                       node_id: Optional[int] = None) -> set[int]:
    """Ids of the factors the delete would remove, or DeleteRefused.

    target "node": `node_id` and its descendants; "analysis": every factor of
    `analysis_id` and their descendants. `analysis_id` is the analysis the
    scope must stay in (for a factor, its own analysis). Read only.
    """
    Node = models.Node
    columns = (Node.id, Node.analysis_id, Node.parent_id)
    try:
        limit = _delete_scope_limit(db)
        if target == "node":
            start = db.query(*columns).filter(Node.id == node_id).all()
        else:
            start = db.query(*columns).filter(Node.analysis_id == analysis_id).all()
        scope = {row.id: row for row in start}
        if len(scope) > limit:
            raise DeleteRefused(DELETE_REASON_INCOMPLETE)
        frontier = list(scope)
        while frontier:
            found = []
            for chunk in _chunks(frontier):
                found.extend(db.query(*columns).filter(Node.parent_id.in_(chunk)).order_by(Node.id).all())
            frontier = []
            for row in found:
                if row.id in scope:  # reached again: judged below (self-reference, cycle)
                    continue
                scope[row.id] = row
                if len(scope) > limit:
                    raise DeleteRefused(DELETE_REASON_INCOMPLETE)
                frontier.append(row.id)
    except SQLAlchemyError:
        raise DeleteRefused(DELETE_REASON_LOOKUP_FAILED) from None

    if any(row.parent_id == row.id for row in scope.values()):
        raise DeleteRefused(delete_reason_self_parent(target))
    if nodes_on_cycles(scope.values(), scope):
        raise DeleteRefused(delete_reason_cycle(target))
    foreign = sum(1 for row in scope.values() if row.analysis_id != analysis_id)
    if foreign:
        raise DeleteRefused(delete_reason_foreign(target, foreign))
    return set(scope)


def _commit_checked_delete(db: Session, scope: set[int], *, analysis_id: Optional[int] = None) -> None:
    """Commit the delete marked in `db` only if it removes exactly `scope`."""
    marked = {obj.id for obj in db.deleted if isinstance(obj, models.Node)}
    if marked != scope:
        db.rollback()
        raise DeleteRefused(DELETE_REASON_CHANGED)
    try:
        db.flush()
    except CircularDependencyError:  # a loop made after the check
        db.rollback()
        raise DeleteRefused(DELETE_REASON_CHANGED) from None
    Node = models.Node
    left = []
    ids = sorted(scope)
    for chunk in _chunks(ids):
        left.extend(db.query(Node.id).filter(Node.parent_id.in_(chunk)).limit(1).all())
    if analysis_id is not None:
        left.extend(db.query(Node.id).filter(Node.analysis_id == analysis_id).limit(1).all())
    if left:
        db.rollback()
        raise DeleteRefused(DELETE_REASON_CHANGED)
    db.commit()


def node_title_exists(db: Session, analysis_id: int, parent_id: Optional[int], level: int, title: str) -> bool:
    query = db.query(models.Node).filter(
        models.Node.analysis_id == analysis_id,
        models.Node.level == level,
        models.Node.title == title,
    )
    if parent_id is not None:
        query = query.filter(models.Node.parent_id == parent_id)
    else:
        query = query.filter(models.Node.parent_id.is_(None))
    return query.first() is not None

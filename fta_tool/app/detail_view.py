"""View data for the analysis edit screen (plan 3.4, 5.9.5; J-25).

Pure functions: analysis_detail in main.py passes the analysis's factors and
the result of two read-only lookups (crud.get_cross_analysis_links); nothing
here touches the database. build_detail_view returns

* the category of every factor's parent link (plan 5.9.5): consistent,
  missing parent, parent in another analysis, self-reference, cycle, level
  mismatch, or consistent itself below an inconsistent ancestor
  (「上位に不整合あり」);
* whether the factor may be the parent of generation and manual add: never a
  factor with an inconsistent link or an inconsistent ancestor (J-25; the
  user's decision of 2026-09-29, 判断3);
* whether the edit screen offers 削除 for the factor, and why not (判断2).
  The existing delete API removes the factor and everything whose parent_id
  leads to it, in any analysis. The whole subtree is therefore walked without
  a depth limit, and deletion is offered only when the walk completes, no
  factor of another analysis hangs anywhere below, the lookups succeeded and
  the factor itself is not in a category the plan keeps undeletable. This is
  the screen's own check on the data as fetched for the page; it does not
  make the delete API itself safe;
* the structure the template renders (the consistent tree, the group of
  factors with inconsistent links, the parent groups of each step) and the
  JSON summary embedded in the page.

Every walk records what it has visited, so a cycle in the data always ends
it; display structures are additionally bounded at three levels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

OK = "ok"
UPPER = "upper"
SELF_PARENT = "self_parent"
CYCLE = "cycle"
FOREIGN_PARENT = "foreign_parent"
MISSING_PARENT = "missing_parent"
UNVERIFIED_PARENT = "unverified_parent"
LEVEL_MISMATCH = "level_mismatch"

# Primary category when a factor's own link has several problems.
ISSUE_ORDER = (SELF_PARENT, CYCLE, FOREIGN_PARENT, MISSING_PARENT, UNVERIFIED_PARENT, LEVEL_MISMATCH)

# Categories the edit screen never offers to delete (plan 5.9.5, 判断2-4).
# UNVERIFIED_PARENT only occurs when the lookups failed, and then nothing is
# offered for deletion anyway.
UNDELETABLE = frozenset({SELF_PARENT, CYCLE, FOREIGN_PARENT, UNVERIFIED_PARENT, LEVEL_MISMATCH})

MAX_DISPLAY_DEPTH = 3

LEVEL_NAMES = {1: "一次", 2: "二次", 3: "三次"}
JUDGEMENT_LABELS = {"yes": "Yes", "no": "No", "unknown": "未評価"}
DIRECT_CAUSE_LABELS = {
    "likely": "可能性高",
    "unlikely": "可能性低",
    "direct": "直接要因",
    "not_direct": "直接要因でない",
}

UPPER_LABEL = "（上位の要因の親子関係に不整合があります）"

REASON_NOT_VERIFIED = "安全に削除できるか確認できていないため、この画面では削除できません。"
REASON_LOOKUP_FAILED = "削除される範囲を確認するための情報を取得できなかったため、この画面では削除できません。"
REASON_SCOPE_INCOMPLETE = "削除される範囲をすべて確認できなかったため、この画面では削除できません。"
REASON_FOREIGN_DESCENDANT = (
    "この要因の子孫に別の分析の要因が含まれるため、この画面では削除できません"
    "（削除すると別の分析の要因も削除されます）。"
)
PARENT_REASON_INCONSISTENT = "親子関係に不整合があるため、この要因の下には要因を追加・生成できません。"
PARENT_REASON_LEVEL3 = "三次要因の下には要因を追加できません。"


def level_name(level: int) -> str:
    return LEVEL_NAMES.get(level, f"階層{level}")


@dataclass(frozen=True)
class CrossAnalysisLinks:
    """What crud.get_cross_analysis_links found outside this analysis."""

    # parent id referenced by a factor of this analysis -> the analysis it belongs to
    parents_elsewhere: dict[int, int]
    # factor id of this analysis -> ids of factors of other analyses whose parent it is
    children_elsewhere: dict[int, tuple[int, ...]]


@dataclass
class NodeView:
    id: int
    parent_id: Optional[int]
    level: int
    title: str
    description: str
    judgement: str
    direct_cause: str
    ai_generated: bool
    warning_text: str
    has_memo: bool
    kind: str = OK
    issues: tuple[str, ...] = ()
    label: str = ""
    notes: tuple[str, ...] = ()
    anomaly_root: Optional[int] = None
    can_parent: bool = False
    parent_reason: str = ""
    delete_allowed: bool = False
    delete_reason: str = ""
    delete_scope: Optional[int] = None  # factors of this analysis the delete would remove
    parent_display: str = ""
    children: list["NodeView"] = field(default_factory=list)

    @property
    def judgement_label(self) -> str:
        return JUDGEMENT_LABELS.get(self.judgement, self.judgement)

    @property
    def direct_cause_label(self) -> str:
        return DIRECT_CAUSE_LABELS.get(self.direct_cause, "")

    @property
    def level_name(self) -> str:
        return level_name(self.level)


@dataclass
class DetailView:
    nodes: list[NodeView]  # every factor, in the order of crud.get_nodes_by_analysis
    by_id: dict[int, NodeView]
    roots: list[NodeView]  # consistent 一次要因 (the consistent tree starts here)
    level_nodes: dict[int, list[NodeView]]  # consistent factors per level 1-3
    anomalies: list[NodeView]  # factors whose own link is inconsistent (entries of the group)
    anomaly_count: int  # factors in the group, including 「上位に不整合あり」
    step_counts: dict[int, dict[str, int]]
    targets: dict[int, dict[str, int]]  # generated level -> Yes parents usable / excluded
    lookups_ok: bool
    data: dict


# ----- parent-link categories ------------------------------------------------

def nodes_on_cycles(nodes: Iterable, by_id: dict) -> set[int]:
    """Ids of factors whose parent links (inside the analysis) loop back to
    themselves: self-references and longer cycles. Each factor is walked at
    most once, so the result is found in linear time and always ends."""
    state: dict[int, int] = {}  # 1 = on the current walk, 2 = finished
    on_cycle: set[int] = set()
    for start in nodes:
        if start.id in state:
            continue
        path: list[int] = []
        position: dict[int, int] = {}
        current: Optional[int] = start.id
        while current is not None and current in by_id and current not in state:
            state[current] = 1
            position[current] = len(path)
            path.append(current)
            parent_id = by_id[current].parent_id
            current = parent_id if parent_id in by_id else None
        if current is not None and state.get(current) == 1:
            on_cycle.update(path[position[current]:])
        for node_id in path:
            state[node_id] = 2
    return on_cycle


def _level_problem(node, by_id: dict) -> Optional[str]:
    level = node.level
    if level not in LEVEL_NAMES:
        return f"（階層が合いません：階層{level}）"
    parent_id = node.parent_id
    if level == 1:
        return None if parent_id is None else "（階層が合いません：一次要因に親があります）"
    if parent_id is None:
        return "（階層が合いません：親がありません）"
    parent = by_id.get(parent_id)
    if parent is None:
        return None  # judged as a missing parent / a parent in another analysis
    if parent.level != level - 1:
        return f"（階層が合いません：親は{level_name(parent.level)}）"
    return None


def own_issues(node, by_id: dict, on_cycle: set[int], links: Optional[CrossAnalysisLinks]):
    """(issues, texts) of the factor's own parent link, in ISSUE_ORDER."""
    found: dict[str, str] = {}
    parent_id = node.parent_id
    if parent_id is not None and parent_id == node.id:
        found[SELF_PARENT] = "（自分自身を親にしています）"
    elif node.id in on_cycle:
        found[CYCLE] = "（親子関係が循環しています）"
    if parent_id is not None and parent_id != node.id and parent_id not in by_id:
        if links is None:
            found[UNVERIFIED_PARENT] = f"（親を確認できませんでした：ID {parent_id}）"
        elif parent_id in links.parents_elsewhere:
            found[FOREIGN_PARENT] = f"（別の分析の要因を親にしています：ID {parent_id}）"
        else:
            found[MISSING_PARENT] = f"（親が見つかりません：ID {parent_id}）"
    level_text = _level_problem(node, by_id)
    if level_text:
        found[LEVEL_MISMATCH] = level_text
    issues = tuple(issue for issue in ISSUE_ORDER if issue in found)
    return issues, tuple(found[issue] for issue in issues)


def _inconsistent_ancestor(node_id: int, by_id: dict, issues_of: dict[int, tuple]) -> Optional[int]:
    """Nearest ancestor whose own link is inconsistent (None if there is none)."""
    seen = {node_id}
    current = by_id[node_id]
    while True:
        parent_id = current.parent_id
        if parent_id is None or parent_id not in by_id:
            return None
        if parent_id in seen:  # a loop is itself an inconsistency
            return parent_id
        seen.add(parent_id)
        if issues_of[parent_id]:
            return parent_id
        current = by_id[parent_id]


# ----- deletion scope --------------------------------------------------------

def deletion_scope(root_id: int, children_of: dict[int, list[int]],
                   children_elsewhere: dict[int, tuple[int, ...]], limit: int):
    """Walk everything the delete API would remove together with `root_id`,
    without a depth limit.

    `children_of` holds the children inside the analysis (a self-reference
    included); `children_elsewhere` the children in other analyses. Returns
    (factors of this analysis in the scope, factors of other analyses hanging
    directly below them), or None when the walk could not be completed: a
    factor reached twice (the links loop) or more factors than `limit`.
    """
    seen: set[int] = set()
    stack = [root_id]
    foreign = 0
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            return None
        seen.add(node_id)
        if len(seen) > limit:
            return None
        foreign += len(children_elsewhere.get(node_id, ()))
        stack.extend(children_of.get(node_id, ()))
    return len(seen), foreign


# ----- view ------------------------------------------------------------------

def _node_view(node) -> NodeView:
    return NodeView(
        id=node.id,
        parent_id=node.parent_id,
        level=node.level,
        title=node.title or "",
        description=node.description or "",
        judgement=node.user_judgement or "unknown",
        direct_cause=node.direct_cause_status or "unknown",
        ai_generated=bool(node.ai_generated),
        warning_text=node.warning_flags or "",
        has_memo=bool((node.memo or "").strip()),
    )


def _place_for_display(ordered: list[NodeView], views: dict[int, NodeView]) -> tuple[list[NodeView], list[NodeView]]:
    """Attach consistent links as display children; return (roots, entries).

    Roots are the consistent 一次要因, entries the factors whose own link is
    inconsistent. A factor that would end up deeper than three levels, or not
    reachable from a root or an entry, is shown as an entry of its own, so
    nothing is hidden and every display walk stays bounded.
    """
    for view in ordered:
        view.children = []
    for view in ordered:
        if view.kind in (OK, UPPER) and view.parent_id is not None \
                and view.parent_id != view.id and view.parent_id in views:
            views[view.parent_id].children.append(view)
    roots = [v for v in ordered if v.kind == OK and v.level == 1 and v.parent_id is None]
    entries = [v for v in ordered if v.issues]

    placed: set[int] = set()
    queue = [(v, 1) for v in roots + entries]
    while queue:
        view, depth = queue.pop()
        if view.id in placed:
            continue
        placed.add(view.id)
        kept = []
        for child in view.children:
            if depth + 1 <= MAX_DISPLAY_DEPTH and child.id not in placed:
                kept.append(child)
                queue.append((child, depth + 1))
        view.children = kept
    for view in ordered:
        if view.id not in placed:
            entries.append(view)
            placed.add(view.id)
            view.children = []
    order = {v.id: index for index, v in enumerate(ordered)}
    entries.sort(key=lambda v: order[v.id])
    return roots, entries


def build_detail_view(analysis, nodes: list, links: Optional[CrossAnalysisLinks], *,
                      factor_counts: dict[str, int], scope_limit: Optional[int] = None) -> DetailView:
    """Everything the edit screen shows about the factors.

    `nodes` in the order of crud.get_nodes_by_analysis; `links` is None when
    the lookups failed (then nothing is offered for deletion and parents
    outside the analysis cannot be told apart). `scope_limit` caps the
    deletion walk (default: the number of factors, which a complete walk
    inside the analysis can never exceed).
    """
    by_id = {node.id: node for node in nodes}
    on_cycle = nodes_on_cycles(nodes, by_id)
    issues_of: dict[int, tuple[str, ...]] = {}
    texts_of: dict[int, tuple[str, ...]] = {}
    for node in nodes:
        issues_of[node.id], texts_of[node.id] = own_issues(node, by_id, on_cycle, links)

    children_of: dict[int, list[int]] = {}
    for node in nodes:
        if node.parent_id is not None and node.parent_id in by_id:
            children_of.setdefault(node.parent_id, []).append(node.id)
    children_elsewhere = links.children_elsewhere if links is not None else {}
    limit = len(nodes) if scope_limit is None else scope_limit

    ordered: list[NodeView] = []
    views: dict[int, NodeView] = {}
    for node in nodes:
        view = _node_view(node)
        issues = issues_of[node.id]
        if issues:
            view.kind, view.issues, view.notes = issues[0], issues, texts_of[node.id]
            view.label = view.notes[0]
        else:
            root = _inconsistent_ancestor(node.id, by_id, issues_of)
            if root is not None:
                view.kind, view.anomaly_root = UPPER, root
                view.label = UPPER_LABEL
                view.notes = (UPPER_LABEL,)

        # Parent of generation / manual add (判断3).
        if view.kind != OK:
            view.parent_reason = PARENT_REASON_INCONSISTENT
        elif view.level >= 3:
            view.parent_reason = PARENT_REASON_LEVEL3
        else:
            view.can_parent = True

        # Deletion (判断2).
        if links is None:
            view.delete_reason = REASON_LOOKUP_FAILED
        elif set(issues) & UNDELETABLE:
            view.delete_reason = REASON_NOT_VERIFIED
        else:
            scope = deletion_scope(node.id, children_of, children_elsewhere, limit)
            if scope is None:
                view.delete_reason = REASON_SCOPE_INCOMPLETE
            elif scope[1] > 0:
                view.delete_reason = REASON_FOREIGN_DESCENDANT
            else:
                view.delete_allowed, view.delete_scope = True, scope[0]

        # Parent column of the table (C-09: never 「（頂上事象）」 for a broken link).
        if view.kind in (OK, UPPER):
            view.parent_display = "（頂上事象）" if node.parent_id is None else by_id[node.parent_id].title
        else:
            view.parent_display = view.label

        ordered.append(view)
        views[node.id] = view

    roots, anomalies = _place_for_display(ordered, views)
    level_nodes = {level: [v for v in ordered if v.kind == OK and v.level == level] for level in (1, 2, 3)}
    step_counts = {
        level: {
            "total": len(items),
            "unevaluated": sum(1 for v in items if v.judgement not in ("yes", "no")),
        }
        for level, items in level_nodes.items()
    }
    targets = {}
    for level in (2, 3):
        yes = [v for v in ordered if v.level == level - 1 and v.judgement == "yes"]
        targets[level] = {
            "count": sum(1 for v in yes if v.can_parent),
            "excluded": sum(1 for v in yes if not v.can_parent),
        }

    data = {
        "version": 1,
        "analysisId": analysis.id,
        "factorCounts": dict(factor_counts),
        "lookupsOk": links is not None,
        "nodes": [
            {
                "id": v.id,
                "parentId": v.parent_id,
                "level": v.level,
                "title": v.title,
                "description": v.description,
                "judgement": v.judgement,
                "directCause": v.direct_cause,
                "ai": v.ai_generated,
                "warning": bool(v.warning_text),
                "memo": v.has_memo,
                "kind": v.kind,
                "label": v.label,
                "notes": list(v.notes),
                "anomalyRoot": v.anomaly_root,
                "canParent": v.can_parent,
                "parentReason": v.parent_reason,
                "delete": {"allowed": v.delete_allowed, "reason": v.delete_reason},
            }
            for v in ordered
        ],
    }

    return DetailView(
        nodes=ordered,
        by_id=views,
        roots=roots,
        level_nodes=level_nodes,
        anomalies=anomalies,
        anomaly_count=sum(1 for v in ordered if v.kind != OK),
        step_counts=step_counts,
        targets=targets,
        lookups_ok=links is not None,
        data=data,
    )

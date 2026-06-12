import csv
import io
import json
from typing import Any

from sqlalchemy.orm import Session

from .. import crud, models


def build_tree(nodes: list[models.Node]) -> dict[int, list[models.Node]]:
    """Build parent->children map."""
    tree: dict[int, list[models.Node]] = {}
    for node in nodes:
        parent_key = node.parent_id if node.parent_id is not None else -1
        tree.setdefault(parent_key, [])
        tree[parent_key].append(node)
    return tree


def export_json(db: Session, analysis_id: int) -> str:
    analysis = crud.get_analysis(db, analysis_id)
    if not analysis:
        return json.dumps({"error": "Analysis not found"})

    nodes = crud.get_nodes_by_analysis(db, analysis_id)

    def node_to_dict(node: models.Node) -> dict[str, Any]:
        return {
            "id": node.id,
            "parent_id": node.parent_id,
            "level": node.level,
            "title": node.title,
            "description": node.description,
            "ai_generated": node.ai_generated,
            "user_judgement": node.user_judgement,
            "direct_cause_status": node.direct_cause_status,
            "direct_cause_comment": node.direct_cause_comment,
            "evidence": node.evidence,
            "prevention_idea": node.prevention_idea,
            "memo": node.memo,
            "warning_flags": node.warning_flags or "",
            "display_order": node.display_order,
        }

    analysis_context = None
    if analysis.analysis_context:
        try:
            analysis_context = json.loads(analysis.analysis_context)
        except (ValueError, TypeError):
            analysis_context = None

    data = {
        "id": analysis.id,
        "title": analysis.title,
        "top_event": analysis.top_event,
        "analysis_context": analysis_context,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "updated_at": analysis.updated_at.isoformat() if analysis.updated_at else None,
        "nodes": [node_to_dict(n) for n in nodes],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def export_csv(db: Session, analysis_id: int) -> str:
    analysis = crud.get_analysis(db, analysis_id)
    if not analysis:
        return ""

    nodes = crud.get_nodes_by_analysis(db, analysis_id)
    node_map = {n.id: n for n in nodes}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "レベル", "タイトル", "説明", "親ID", "親要因",
        "AI生成", "ユーザ評価", "直接要因ステータス",
        "直接要因コメント", "根拠", "再発防止策", "メモ",
        "要確認フラグ", "警告理由"
    ])

    level_labels = {0: "頂上事象", 1: "一次要因", 2: "二次要因", 3: "三次要因"}
    judgement_labels = {"unknown": "未評価", "yes": "Yes", "no": "No"}
    status_labels = {
        "unknown": "未評価",
        "likely": "直接要因の可能性高",
        "unlikely": "直接要因の可能性低",
        "direct": "直接要因",
        "not_direct": "直接要因でない",
    }

    for node in nodes:
        parent_title = node_map[node.parent_id].title if node.parent_id and node.parent_id in node_map else ""
        warning = node.warning_flags or ""
        writer.writerow([
            node.id,
            level_labels.get(node.level, str(node.level)),
            node.title,
            node.description,
            node.parent_id if node.parent_id else "",
            parent_title,
            "AI生成" if node.ai_generated else "手動",
            judgement_labels.get(node.user_judgement, node.user_judgement),
            status_labels.get(node.direct_cause_status, node.direct_cause_status),
            node.direct_cause_comment,
            node.evidence,
            node.prevention_idea,
            node.memo,
            "要確認" if warning else "",
            warning,
        ])

    return output.getvalue()


def export_markdown(db: Session, analysis_id: int) -> str:
    analysis = crud.get_analysis(db, analysis_id)
    if not analysis:
        return "# エラー\n分析が見つかりません。"

    nodes = crud.get_nodes_by_analysis(db, analysis_id)
    tree = build_tree(nodes)

    lines = []
    lines.append(f"# FTA分析結果")
    lines.append("")
    lines.append(f"## 頂上事象")
    lines.append(f"{analysis.top_event}")
    lines.append("")

    if analysis.analysis_context:
        try:
            ctx = json.loads(analysis.analysis_context)
        except (ValueError, TypeError):
            ctx = None
        if ctx:
            lines.append("## 分析コンテキスト（サンプルシナリオ）")
            if ctx.get("system_context"):
                lines.append("### システム構成")
                lines.append(ctx["system_context"].strip())
                lines.append("")
            if ctx.get("incident_context"):
                lines.append("### 障害発生時の状況")
                lines.append(ctx["incident_context"].strip())
                lines.append("")
            if ctx.get("demo_points"):
                lines.append("### デモ観点")
                lines.append(ctx["demo_points"].strip())
                lines.append("")

    lines.append(f"## FTAツリー")
    lines.append("")

    judgement_labels = {"unknown": "未評価", "yes": "Yes", "no": "No"}
    status_labels = {
        "unknown": "",
        "likely": "直接要因の可能性が高い",
        "unlikely": "直接要因の可能性が低い",
        "direct": "直接要因",
        "not_direct": "直接要因でない",
    }

    def render_node(node: models.Node, indent: int):
        prefix = "  " * indent + "- "
        level_label = {1: "一次要因", 2: "二次要因", 3: "三次要因"}.get(node.level, "要因")
        judgement = judgement_labels.get(node.user_judgement, "")
        lines.append(f"{prefix}{level_label}: {node.title} [{judgement}]")
        if node.direct_cause_status and node.direct_cause_status != "unknown":
            status_label = status_labels.get(node.direct_cause_status, "")
            if status_label:
                lines.append("  " * (indent + 1) + f"- 直接要因評価: {status_label}")
        if node.direct_cause_comment:
            lines.append("  " * (indent + 1) + f"- コメント: {node.direct_cause_comment}")
        if node.prevention_idea:
            lines.append("  " * (indent + 1) + f"- 再発防止策: {node.prevention_idea}")

        children = tree.get(node.id, [])
        for child in sorted(children, key=lambda n: (n.display_order, n.id)):
            render_node(child, indent + 1)

    lines.append(f"- 頂上事象: {analysis.top_event}")
    top_level_nodes = tree.get(-1, [])
    for node in sorted(top_level_nodes, key=lambda n: (n.display_order, n.id)):
        render_node(node, 1)

    return "\n".join(lines)

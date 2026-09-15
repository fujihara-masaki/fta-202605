from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from . import models, schemas


def get_analyses(db: Session):
    return db.query(models.Analysis).order_by(models.Analysis.updated_at.desc()).all()


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
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db.delete(db_analysis)
        db.commit()
    return db_analysis


def get_nodes_by_analysis(db: Session, analysis_id: int):
    return (
        db.query(models.Node)
        .filter(models.Node.analysis_id == analysis_id)
        .order_by(models.Node.level, models.Node.display_order, models.Node.id)
        .all()
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
    db_node = get_node(db, node_id)
    if db_node:
        db.delete(db_node)
        db.commit()
    return db_node


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

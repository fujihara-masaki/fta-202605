from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, backref
from .database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    top_event = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    nodes = relationship("Node", back_populates="analysis", cascade="all, delete-orphan")


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("nodes.id"), nullable=True)
    level = Column(Integer, nullable=False)  # 0=top, 1=first, 2=second, 3=third
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    ai_generated = Column(Boolean, default=False)
    user_judgement = Column(String(20), default="unknown")  # unknown, yes, no
    direct_cause_status = Column(String(20), default="unknown")  # unknown, likely, unlikely, direct, not_direct
    direct_cause_comment = Column(Text, default="")
    evidence = Column(Text, default="")
    prevention_idea = Column(Text, default="")
    display_order = Column(Integer, default=0)
    memo = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    analysis = relationship("Analysis", back_populates="nodes")
    children = relationship(
        "Node",
        backref=backref("parent", remote_side=[id]),
        foreign_keys=[parent_id],
    )

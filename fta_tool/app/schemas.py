from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AnalysisCreate(BaseModel):
    title: str
    top_event: str = ""
    # Optional sample-scenario context (JSON string). Empty for normal
    # hand-entered analyses.
    analysis_context: str = ""


class AnalysisUpdate(BaseModel):
    title: Optional[str] = None
    top_event: Optional[str] = None


class TopEventUpdate(BaseModel):
    top_event: str


class NodeCreate(BaseModel):
    title: str
    description: str = ""
    parent_id: Optional[int] = None
    level: int = 1


class NodeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    user_judgement: Optional[str] = None
    direct_cause_status: Optional[str] = None
    direct_cause_comment: Optional[str] = None
    evidence: Optional[str] = None
    prevention_idea: Optional[str] = None
    memo: Optional[str] = None


class GenerateRequest(BaseModel):
    parent_id: Optional[int] = None

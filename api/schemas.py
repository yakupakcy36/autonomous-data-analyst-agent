"""Pydantic v2 schemas for the Autonomous Data Analyst Agent API."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500, description="Natural language analytics inquiry")
    sql_override: Optional[str] = Field(default=None, description="Optional raw SQL to run through state machine")


class AuditRequest(BaseModel):
    sql: str = Field(..., description="Raw SQL statement to audit for security and safety")


class StateTrajectoryItem(BaseModel):
    from_state: str
    to_state: str
    action: str
    details: Dict[str, Any]


class AgentResponse(BaseModel):
    run_id: str
    status: str
    question: str
    final_sql: str
    query_plan: Optional[Dict[str, Any]]
    data: Optional[List[Dict[str, Any]]]
    statistical_profile: Optional[Dict[str, Any]]
    row_count: int
    insight_summary: str
    trajectory: List[StateTrajectoryItem]
    retries_count: int
    elapsed_ms: float


class AuditResponse(BaseModel):
    is_allowed: bool
    requires_human_approval: bool
    risk_level: str
    detected_reasons: List[str]


class SchemaResponse(BaseModel):
    tables: Dict[str, List[str]]

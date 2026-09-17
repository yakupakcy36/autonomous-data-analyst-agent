"""FastAPI application for the Autonomous Data Analyst Agent with HITL Checkpointing."""

from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, status

from src.config import DEFAULT_AGENT_CONFIG
from src.database import DatabaseSandbox
from src.agent import AutonomousDataAnalystAgent
from src.safety import SQLSafetyGuard
from api.schemas import (
    QuestionRequest,
    AuditRequest,
    AgentResponse,
    AuditResponse,
    SchemaResponse,
)

sandbox: Optional[DatabaseSandbox] = None
agent: Optional[AutonomousDataAnalystAgent] = None
safety_guard: Optional[SQLSafetyGuard] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global sandbox, agent, safety_guard
    sandbox = DatabaseSandbox()
    agent = AutonomousDataAnalystAgent(sandbox=sandbox, config=DEFAULT_AGENT_CONFIG)
    safety_guard = SQLSafetyGuard(config=DEFAULT_AGENT_CONFIG)
    yield


app = FastAPI(
    title="Autonomous Data Analyst Agent & Self-Healing SQL API",
    description=(
        "Production API running cyclic finite state machine agents with EXPLAIN QUERY PLAN validation, "
        "multi-pattern self-healing SQL execution, statistical data profiling, and stateful "
        "Human-in-the-Loop (HITL) checkpoint approval."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["Diagnostics"])
def health():
    return {
        "status": "healthy",
        "agent_ready": agent is not None,
        "database_connected": sandbox is not None,
        "pending_hitl_checkpoints": len(agent.hitl_checkpoints) if agent else 0,
    }


@app.get("/schema", response_model=SchemaResponse, tags=["Metadata"])
def get_database_schema():
    if sandbox is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sandbox not initialized")
    return SchemaResponse(tables=sandbox.get_schema())


@app.post("/query", response_model=AgentResponse, tags=["Agent Execution"])
def run_agent_query(req: QuestionRequest):
    """Executes inquiry through autonomous cyclic state machine (with optional SQL override)."""
    if agent is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent not initialized")

    res = agent.run(req.question, initial_sql_override=req.sql_override)
    return AgentResponse(**res.__dict__)


@app.post("/runs/{run_id}/approve", response_model=AgentResponse, tags=["Human-in-the-Loop (HITL)"])
def approve_hitl_checkpoint(run_id: str):
    """Resume and commit a paused HITL mutation checkpoint."""
    if agent is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent not initialized")
    try:
        res = agent.approve_hitl_run(run_id)
        return AgentResponse(**res.__dict__)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"HITL run_id '{run_id}' not found")


@app.post("/audit", response_model=AuditResponse, tags=["Safety Audit"])
def audit_sql_query(req: AuditRequest):
    if safety_guard is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Safety guard not initialized")

    report = safety_guard.audit(req.sql)
    return AuditResponse(**report.__dict__)

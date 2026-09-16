"""Autonomous Data Analyst Agent with cyclic state graph, query plan analysis, and HITL checkpointing."""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.config import DEFAULT_AGENT_CONFIG, AgentConfig
from src.database import DatabaseSandbox
from src.safety import SQLSafetyGuard, SafetyAuditReport
from src.generator import SQLGeneratorAndHealer
from src.profiler import DataResultProfiler


class AgentState(str, Enum):
    INIT = "INIT"
    GENERATE = "GENERATE"
    AUDIT = "AUDIT"
    EXPLAIN_PLAN = "EXPLAIN_PLAN"
    EXECUTE = "EXECUTE"
    SELF_HEAL = "SELF_HEAL"
    SYNTHESIZE = "SYNTHESIZE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    HITL_PAUSED = "HITL_PAUSED"


@dataclass
class StateTransition:
    from_state: AgentState
    to_state: AgentState
    action: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentResult:
    run_id: str
    status: str  # SUCCESS, BLOCKED, HITL_PAUSED, FAILED
    question: str
    final_sql: str
    query_plan: Optional[Dict[str, Any]]
    data: Optional[List[Dict[str, Any]]]
    statistical_profile: Optional[Dict[str, Any]]
    row_count: int
    insight_summary: str
    trajectory: List[Dict[str, Any]]
    retries_count: int
    elapsed_ms: float


class AutonomousDataAnalystAgent:
    """
    Cyclic state machine agent executing:
    INIT -> GENERATE -> AUDIT -> EXPLAIN_PLAN -> EXECUTE -> (SELF_HEAL) -> SYNTHESIZE -> COMPLETED
    With stateful checkpointing for Human-in-the-Loop (HITL) approval of state mutations.
    """

    def __init__(self, sandbox: Optional[DatabaseSandbox] = None, config: AgentConfig = DEFAULT_AGENT_CONFIG):
        self.config = config
        self.sandbox = sandbox or DatabaseSandbox(self.config.database_uri)
        self.schema = self.sandbox.get_schema()
        self.safety_guard = SQLSafetyGuard(config=self.config)
        self.generator = SQLGeneratorAndHealer(self.schema)
        self.hitl_checkpoints: Dict[str, Dict[str, Any]] = {}

    def run(self, user_question: str, initial_sql_override: Optional[str] = None) -> AgentResult:
        """Executes the autonomous cyclic state graph."""
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        start_time = time.perf_counter()
        trajectory: List[StateTransition] = []
        current_state = AgentState.INIT
        current_sql = initial_sql_override or ""
        retries = 0
        df_result = None
        query_plan = None
        stat_profile = None
        error_msg = ""

        trajectory.append(StateTransition(
            from_state=AgentState.INIT,
            to_state=AgentState.GENERATE,
            action="Receive inquiry and initialize state context",
            details={"question": user_question, "run_id": run_id},
        ))
        current_state = AgentState.GENERATE

        while current_state not in [AgentState.COMPLETED, AgentState.FAILED, AgentState.HITL_PAUSED]:
            # --- GENERATE STATE ---
            if current_state == AgentState.GENERATE:
                if not current_sql:
                    current_sql = self.generator.generate_initial_query(user_question)
                trajectory.append(StateTransition(
                    from_state=AgentState.GENERATE,
                    to_state=AgentState.AUDIT,
                    action="Formulated candidate SQL statement",
                    details={"sql": current_sql},
                ))
                current_state = AgentState.AUDIT

            # --- AUDIT STATE ---
            elif current_state == AgentState.AUDIT:
                audit_report: SafetyAuditReport = self.safety_guard.audit(current_sql)

                if audit_report.requires_human_approval:
                    trajectory.append(StateTransition(
                        from_state=AgentState.AUDIT,
                        to_state=AgentState.HITL_PAUSED,
                        action="Mutation detected: Checkpointed run for Human-in-the-Loop approval",
                        details={"reasons": audit_report.detected_reasons, "run_id": run_id},
                    ))
                    self.hitl_checkpoints[run_id] = {
                        "question": user_question,
                        "sql": current_sql,
                        "trajectory": list(trajectory),
                    }
                    current_state = AgentState.HITL_PAUSED
                    break

                if not audit_report.is_allowed:
                    trajectory.append(StateTransition(
                        from_state=AgentState.AUDIT,
                        to_state=AgentState.FAILED,
                        action="Destructive query blocked by zero-trust safety policy",
                        details={"reasons": audit_report.detected_reasons},
                    ))
                    current_state = AgentState.FAILED
                    break

                trajectory.append(StateTransition(
                    from_state=AgentState.AUDIT,
                    to_state=AgentState.EXPLAIN_PLAN,
                    action="Safety audit passed: read-only SQL verified",
                    details={"risk_level": audit_report.risk_level},
                ))
                current_state = AgentState.EXPLAIN_PLAN

            # --- EXPLAIN_PLAN STATE ---
            elif current_state == AgentState.EXPLAIN_PLAN:
                try:
                    query_plan = self.sandbox.explain_query_plan(current_sql)
                    trajectory.append(StateTransition(
                        from_state=AgentState.EXPLAIN_PLAN,
                        to_state=AgentState.EXECUTE,
                        action=f"Verified query execution plan ({query_plan['scan_strategy']})",
                        details=query_plan,
                    ))
                    current_state = AgentState.EXECUTE
                except Exception as e:
                    error_msg = str(e)
                    if retries < self.config.max_self_healing_retries:
                        trajectory.append(StateTransition(
                            from_state=AgentState.EXPLAIN_PLAN,
                            to_state=AgentState.SELF_HEAL,
                            action=f"Query plan validation failed: {error_msg}. Entering self-healing.",
                            details={"error": error_msg, "retry": retries + 1},
                        ))
                        current_state = AgentState.SELF_HEAL
                    else:
                        trajectory.append(StateTransition(
                            from_state=AgentState.EXPLAIN_PLAN,
                            to_state=AgentState.FAILED,
                            action="Maximum self-healing retries exceeded",
                            details={"error": error_msg},
                        ))
                        current_state = AgentState.FAILED

            # --- EXECUTE STATE ---
            elif current_state == AgentState.EXECUTE:
                try:
                    df_result = self.sandbox.execute(current_sql)
                    trajectory.append(StateTransition(
                        from_state=AgentState.EXECUTE,
                        to_state=AgentState.SYNTHESIZE,
                        action="Executed query in sandbox successfully",
                        details={"rows_returned": len(df_result)},
                    ))
                    current_state = AgentState.SYNTHESIZE
                except Exception as e:
                    error_msg = str(e)
                    if retries < self.config.max_self_healing_retries:
                        trajectory.append(StateTransition(
                            from_state=AgentState.EXECUTE,
                            to_state=AgentState.SELF_HEAL,
                            action=f"Execution error encountered: {error_msg}. Entering self-healing.",
                            details={"error": error_msg, "retry": retries + 1},
                        ))
                        current_state = AgentState.SELF_HEAL
                    else:
                        trajectory.append(StateTransition(
                            from_state=AgentState.EXECUTE,
                            to_state=AgentState.FAILED,
                            action="Maximum self-healing retries exceeded",
                            details={"error": error_msg},
                        ))
                        current_state = AgentState.FAILED

            # --- SELF HEAL STATE ---
            elif current_state == AgentState.SELF_HEAL:
                retries += 1
                healed_sql = self.generator.heal_query(current_sql, error_msg)

                if healed_sql and healed_sql != current_sql:
                    trajectory.append(StateTransition(
                        from_state=AgentState.SELF_HEAL,
                        to_state=AgentState.AUDIT,
                        action="Self-healing synthesized repaired SQL",
                        details={"old_sql": current_sql, "healed_sql": healed_sql},
                    ))
                    current_sql = healed_sql
                    current_state = AgentState.AUDIT
                else:
                    trajectory.append(StateTransition(
                        from_state=AgentState.SELF_HEAL,
                        to_state=AgentState.FAILED,
                        action="Self-healing could not resolve schema divergence",
                        details={"error": error_msg},
                    ))
                    current_state = AgentState.FAILED

            # --- SYNTHESIZE STATE ---
            elif current_state == AgentState.SYNTHESIZE:
                stat_profile = DataResultProfiler.profile(df_result)
                trajectory.append(StateTransition(
                    from_state=AgentState.SYNTHESIZE,
                    to_state=AgentState.COMPLETED,
                    action="Profiled statistical distributions and synthesized insights",
                    details=stat_profile,
                ))
                current_state = AgentState.COMPLETED

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        data_records = df_result.to_dict(orient="records") if df_result is not None else []
        row_count = len(data_records)

        if current_state == AgentState.COMPLETED:
            status_str = "SUCCESS"
            insight = (
                f"Query executed ({query_plan['scan_strategy'] if query_plan else 'SANDBOX'}), "
                f"returning {row_count} rows. Top concentration ratio: "
                f"{stat_profile['top_share_ratio']:.1%}."
            )
        elif current_state == AgentState.HITL_PAUSED:
            status_str = "HITL_PAUSED"
            insight = f"Run {run_id} paused: Mutation requires Human-in-the-Loop approval."
        else:
            status_str = "BLOCKED" if "blocked" in str(trajectory[-1].action).lower() else "FAILED"
            insight = f"Agent stopped: {trajectory[-1].action}"

        formatted_trajectory = [
            {
                "from_state": t.from_state.value,
                "to_state": t.to_state.value,
                "action": t.action,
                "details": t.details,
            }
            for t in trajectory
        ]

        return AgentResult(
            run_id=run_id,
            status=status_str,
            question=user_question,
            final_sql=current_sql,
            query_plan=query_plan,
            data=data_records,
            statistical_profile=stat_profile,
            row_count=row_count,
            insight_summary=insight,
            trajectory=formatted_trajectory,
            retries_count=retries,
            elapsed_ms=round(elapsed_ms, 2),
        )

    def approve_hitl_run(self, run_id: str) -> AgentResult:
        """Resume a paused HITL run after administrator approval and execute mutation."""
        if run_id not in self.hitl_checkpoints:
            raise KeyError(f"Checkpoint run_id '{run_id}' not found")

        cp = self.hitl_checkpoints.pop(run_id)
        sql = cp["sql"]
        trajectory: List[StateTransition] = cp["trajectory"]
        t0 = time.perf_counter()

        affected = self.sandbox.execute_mutation(sql)
        trajectory.append(StateTransition(
            from_state=AgentState.HITL_PAUSED,
            to_state=AgentState.EXECUTE,
            action="Human-in-the-Loop administrator approved mutation",
            details={"affected_rows": affected},
        ))
        trajectory.append(StateTransition(
            from_state=AgentState.EXECUTE,
            to_state=AgentState.COMPLETED,
            action="Mutation committed in database sandbox",
            details={"affected_rows": affected},
        ))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        formatted_trajectory = [
            {
                "from_state": t.from_state.value,
                "to_state": t.to_state.value,
                "action": t.action,
                "details": t.details,
            }
            for t in trajectory
        ]
        return AgentResult(
            run_id=run_id,
            status="SUCCESS",
            question=cp["question"],
            final_sql=sql,
            query_plan=None,
            data=[{"affected_rows": affected}],
            statistical_profile=None,
            row_count=affected,
            insight_summary=f"HITL mutation approved and committed ({affected} rows affected).",
            trajectory=formatted_trajectory,
            retries_count=0,
            elapsed_ms=round(elapsed_ms, 2),
        )

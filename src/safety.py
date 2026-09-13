"""Safety auditing and Human-in-the-Loop (HITL) authorization gates for SQL execution."""

import re
from dataclasses import dataclass
from typing import List, Tuple
from src.config import DEFAULT_AGENT_CONFIG, AgentConfig


@dataclass
class SafetyAuditReport:
    is_allowed: bool
    requires_human_approval: bool
    risk_level: str  # SAFE, HIGH, BLOCKED
    detected_reasons: List[str]


class SQLSafetyGuard:
    """Enforces zero-trust execution policies on generated or incoming SQL queries."""

    def __init__(self, config: AgentConfig = DEFAULT_AGENT_CONFIG):
        self.config = config

    def audit(self, sql_query: str) -> SafetyAuditReport:
        """Audits SQL query against security policies and mutation rules."""
        reasons = []
        clean_sql = sql_query.strip()

        if not clean_sql:
            return SafetyAuditReport(
                is_allowed=False,
                requires_human_approval=False,
                risk_level="BLOCKED",
                detected_reasons=["Empty SQL statement"],
            )

        # 1. Check for hard-blocked destructive commands
        upper_sql = clean_sql.upper()
        for kw in self.config.blocked_keywords:
            # Word boundary check for keywords like DROP, DELETE, TRUNCATE
            if re.search(rf"\b{kw}\b", upper_sql):
                reasons.append(f"Destructive operation blocked: '{kw}' keyword detected")

        if reasons:
            return SafetyAuditReport(
                is_allowed=False,
                requires_human_approval=False,
                risk_level="BLOCKED",
                detected_reasons=reasons,
            )

        # 2. Check for mutation commands requiring Human-in-the-Loop (HITL)
        for kw in self.config.hitl_mutation_keywords:
            if re.search(rf"\b{kw}\b", upper_sql):
                reasons.append(f"Data mutation requires Human-in-the-Loop approval: '{kw}' keyword detected")

        if reasons:
            return SafetyAuditReport(
                is_allowed=False,
                requires_human_approval=True,
                risk_level="HIGH",
                detected_reasons=reasons,
            )

        # 3. Ensure query starts with an allowed read-only statement
        starts_with_allowed = any(
            upper_sql.startswith(allowed_kw) for allowed_kw in self.config.allowed_statement_types
        )
        if not starts_with_allowed:
            return SafetyAuditReport(
                is_allowed=False,
                requires_human_approval=False,
                risk_level="BLOCKED",
                detected_reasons=["Query must be a read-only SELECT or WITH statement"],
            )

        # Passed all safety checks
        return SafetyAuditReport(
            is_allowed=True,
            requires_human_approval=False,
            risk_level="SAFE",
            detected_reasons=[],
        )

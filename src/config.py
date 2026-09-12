"""Configuration settings for Autonomous Data Analyst Agent."""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class AgentConfig:
    """Master configuration for autonomous agent state transitions, safety, and retries."""
    max_self_healing_retries: int = 3
    sql_execution_timeout_sec: float = 5.0
    allowed_statement_types: tuple = ("SELECT", "WITH")
    blocked_keywords: tuple = (
        "DROP", "DELETE", "TRUNCATE", "ALTER", "GRANT", "REVOKE", "EXEC", "SHUTDOWN"
    )
    hitl_mutation_keywords: tuple = ("UPDATE", "INSERT", "CREATE")
    database_uri: str = ":memory:"


DEFAULT_AGENT_CONFIG = AgentConfig()

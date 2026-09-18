"""Test suite for SQL safety guard and Human-in-the-Loop policy enforcement."""

import pytest
from src.safety import SQLSafetyGuard


@pytest.fixture
def guard():
    return SQLSafetyGuard()


def test_safe_select_query_allowed(guard):
    """Read-only SELECT and WITH statements must pass with SAFE risk."""
    queries = [
        "SELECT customer_id, name, annual_spend FROM customers WHERE tier = 'Enterprise';",
        "WITH HighValue AS (SELECT * FROM orders WHERE amount > 10000) SELECT * FROM HighValue;",
    ]
    for q in queries:
        report = guard.audit(q)
        assert report.is_allowed is True
        assert report.requires_human_approval is False
        assert report.risk_level == "SAFE"


def test_destructive_operations_blocked(guard):
    """Destructive SQL commands must be completely blocked."""
    destructive = [
        "DROP TABLE customers;",
        "DELETE FROM orders WHERE order_id = 1;",
        "TRUNCATE TABLE equipment_telemetry;",
        "ALTER TABLE customers ADD COLUMN secret TEXT;",
    ]
    for q in destructive:
        report = guard.audit(q)
        assert report.is_allowed is False
        assert report.risk_level == "BLOCKED"
        assert len(report.detected_reasons) > 0


def test_mutations_require_hitl_approval(guard):
    """State-mutating operations like UPDATE or INSERT require Human-in-the-Loop approval."""
    mutations = [
        "UPDATE customers SET annual_spend = 500000 WHERE customer_id = 101;",
        "INSERT INTO orders (order_id, customer_id, amount) VALUES (99, 101, 500.0);",
    ]
    for q in mutations:
        report = guard.audit(q)
        assert report.is_allowed is False
        assert report.requires_human_approval is True
        assert report.risk_level == "HIGH"

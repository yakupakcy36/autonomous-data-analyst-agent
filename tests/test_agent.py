"""Test suite for autonomous agent state transitions, query plans, self-healing, and HITL resume."""

import pytest
from src.database import DatabaseSandbox
from src.agent import AutonomousDataAnalystAgent


@pytest.fixture
def agent():
    sandbox = DatabaseSandbox(":memory:")
    return AutonomousDataAnalystAgent(sandbox=sandbox)


def test_agent_telemetry_query_and_plan(agent):
    res = agent.run("Show critical machine telemetry readings")
    assert res.status == "SUCCESS"
    assert res.row_count > 0
    assert res.query_plan is not None
    assert res.query_plan["uses_index"] is True
    assert res.statistical_profile is not None


def test_agent_live_self_healing_loop(agent):
    """Verify agent catches column typo during execution, enters SELF_HEAL, fixes SQL, and succeeds."""
    faulty_sql = "SELECT customer_id, name, annual_spending FROM customers WHERE tier = 'Enterprise';"
    res = agent.run("Enterprise customer spend", initial_sql_override=faulty_sql)
    assert res.status == "SUCCESS"
    assert res.retries_count == 1
    assert "annual_spend" in res.final_sql
    assert any(step["from_state"] == "SELF_HEAL" for step in res.trajectory)


def test_agent_hitl_checkpoint_and_approval(agent):
    """Verify mutation pauses at HITL_PAUSED and resumes upon administrator approval."""
    mutation_sql = "UPDATE customers SET annual_spend = 250000.0 WHERE customer_id = 101;"
    paused_res = agent.run("Update Acme Robotics spend", initial_sql_override=mutation_sql)
    assert paused_res.status == "HITL_PAUSED"
    assert paused_res.run_id in agent.hitl_checkpoints

    # Approve and resume checkpoint
    resumed_res = agent.approve_hitl_run(paused_res.run_id)
    assert resumed_res.status == "SUCCESS"
    assert resumed_res.row_count == 1
    assert paused_res.run_id not in agent.hitl_checkpoints

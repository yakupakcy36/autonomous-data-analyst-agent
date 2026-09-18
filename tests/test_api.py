"""Test suite for FastAPI endpoints including HITL approval and self-healing SQL override."""

import pytest
from fastapi.testclient import TestClient
from api.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_api_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["agent_ready"] is True


def test_api_schema(client):
    res = client.get("/schema")
    assert res.status_code == 200
    data = res.json()
    assert "customers" in data["tables"]
    assert "orders" in data["tables"]


def test_api_query_endpoint(client):
    payload = {"question": "List all enterprise tier customers"}
    res = client.post("/query", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["row_count"] > 0
    assert data["statistical_profile"] is not None


def test_api_hitl_pause_and_approve_flow(client):
    payload = {
        "question": "Insert new order record",
        "sql_override": "INSERT INTO orders (order_id, customer_id, category, amount, status, order_date) VALUES (99, 101, 'Sensors', 5000.0, 'Completed', '2026-04-01');",
    }
    res1 = client.post("/query", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "HITL_PAUSED"
    run_id = data1["run_id"]

    res2 = client.post(f"/runs/{run_id}/approve")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "SUCCESS"


def test_api_audit_endpoint(client):
    payload = {"sql": "DROP TABLE customers;"}
    res = client.post("/audit", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["is_allowed"] is False
    assert data["risk_level"] == "BLOCKED"

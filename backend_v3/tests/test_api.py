"""
Backend V3 — API Route Tests
"""
import json
import pytest
from backend_v3.app import app, session_store


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "healthy"
    assert "ollama_connected" in data


def test_unauthorized_chat(client):
    # Missing Auth headers / session
    r = client.post("/chat", json={"message": "hello", "chat_id": "test"})
    assert r.status_code == 401
    assert r.get_json()["success"] is False


def test_login_and_chat_flow(client):
    # 1. Login
    r1 = client.post("/login", json={"email": "rahul.karn@motherson.com"})
    assert r1.status_code == 200
    data1 = r1.get_json()
    assert data1["success"] is True
    token = data1["session_token"]
    assert "MI0168" in token

    # 2. Chat using token
    headers = {"Authorization": f"Bearer {token}"}
    r2 = client.post(
        "/chat",
        headers=headers,
        json={"message": "show my claims", "chat_id": "api_chat"},
    )
    assert r2.status_code == 200
    data2 = r2.get_json()
    assert data2["success"] is True
    # LLM may return a list (RECORD_LIST) or a summary (SUMMARY) — both are valid
    assert data2["response_type"] in ("RECORD_LIST", "SUMMARY", "ANALYTICS"), \
        f"Unexpected response_type: {data2['response_type']}"


def test_out_of_scope_query(client):
    # 1. Login
    r1 = client.post("/login", json={"email": "rahul.karn@motherson.com"})
    token = r1.get_json()["session_token"]

    # 2. Query unrelated question
    headers = {"Authorization": f"Bearer {token}"}
    r2 = client.post(
        "/chat",
        headers=headers,
        json={"message": "how do I cook pasta?", "chat_id": "pasta_chat"},
    )
    assert r2.status_code == 200
    data2 = r2.get_json()
    assert data2["success"] is True
    assert data2["response_type"] == "OUT_OF_SCOPE"
    assert "pasta" in data2["message"] or "reimbursements" in data2["message"]

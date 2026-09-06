"""Health endpoint tests — no Docker or Redis required."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "aws-agent-deployment-demo"


def test_index_returns_ui():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "AWS Agent Deployment Demo" in response.text


def test_queue_metrics_endpoint():
    response = client.get("/metrics/queue")
    assert response.status_code == 200
    body = response.json()
    assert "queue_depth" in body
    assert body["metric_name"] == "QueueDepth"


def test_costs_endpoint():
    response = client.get("/costs")
    assert response.status_code == 200
    body = response.json()
    assert "rate_limit" in body
    assert body["rate_limit"]["requests_per_minute"] == 120

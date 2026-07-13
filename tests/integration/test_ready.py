"""Integration tests for the /ready endpoint."""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.main import app

HEARTBEAT_FILENAME = "_processor_heartbeat.json"


@pytest.fixture
def client():
    return TestClient(app)


def test_ready_endpoint_returns_200(client):
    response = client.get("/ready")
    assert response.status_code == 200


def test_ready_endpoint_reports_not_ready_when_no_heartbeat(client):
    # Make deterministic: remove heartbeat file if present.
    from api.file_storage import file_storage

    heartbeat_file = file_storage.base_dir / HEARTBEAT_FILENAME
    if heartbeat_file.exists():
        heartbeat_file.unlink()

    response = client.get("/ready")
    data = response.json()

    assert data["api"] == "ok"
    assert data["processor_ready"] is False
    assert data["processor_last_heartbeat"] is None


def test_ready_endpoint_reports_ready_when_heartbeat_is_fresh(client):
    from api.file_storage import file_storage

    heartbeat_file = file_storage.base_dir / HEARTBEAT_FILENAME
    heartbeat_file.write_text(
        json.dumps({"updated_at": datetime.now(UTC).isoformat()}, indent=2)
    )

    response = client.get("/ready?processor_max_age_seconds=60")
    data = response.json()

    assert data["api"] == "ok"
    assert data["processor_ready"] is True
    assert isinstance(data["processor_last_heartbeat"], str)
    assert data["processor_heartbeat_age_seconds"] is not None

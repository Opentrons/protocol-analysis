"""Integration tests for the /info endpoint."""

import pytest
from fastapi.testclient import TestClient

from api.main import VERSION, app
from api.version_mapping import PROTOCOL_API_TO_ROBOT_STACK


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_info_endpoint_returns_200(client):
    """Test that the /info endpoint returns a 200 status code."""
    response = client.get("/info")
    assert response.status_code == 200


def test_info_endpoint_returns_json(client):
    """Test that the /info endpoint returns JSON content."""
    response = client.get("/info")
    assert response.headers["content-type"] == "application/json"


def test_info_endpoint_response_structure(client):
    """Test that the /info endpoint returns the correct response structure."""
    response = client.get("/info")
    data = response.json()

    assert "version" in data
    assert "protocol_api_versions" in data
    assert "supported_robot_versions" in data


def test_info_endpoint_returns_correct_version(client):
    """Test that the /info endpoint returns the correct application version."""
    response = client.get("/info")
    data = response.json()

    assert data["version"] == VERSION
    assert data["version"] == "0.1.0"


def test_info_endpoint_returns_protocol_api_mappings(client):
    """Test that the /info endpoint returns protocol API to robot stack mappings."""
    response = client.get("/info")
    data = response.json()

    assert data["protocol_api_versions"] == PROTOCOL_API_TO_ROBOT_STACK
    assert isinstance(data["protocol_api_versions"], dict)


def test_info_endpoint_protocol_api_versions_not_empty(client):
    """Test that the protocol API versions mapping is not empty."""
    response = client.get("/info")
    data = response.json()

    assert len(data["protocol_api_versions"]) > 0


def test_info_endpoint_protocol_api_versions_contain_expected_entries(client):
    """Test that the protocol API versions mapping contains expected entries."""
    response = client.get("/info")
    data = response.json()

    # Check for some known protocol API version mappings (only 2.20 and up)
    protocol_api_versions = data["protocol_api_versions"]

    assert "2.20" in protocol_api_versions
    assert protocol_api_versions["2.20"] == "8.0.0"

    assert "2.26" in protocol_api_versions
    assert protocol_api_versions["2.26"] == "8.7.0"

    assert "2.27" in protocol_api_versions
    assert protocol_api_versions["2.27"] == "8.8.0"
    assert protocol_api_versions["2.26"] == "8.7.0"

    assert "2.28" in protocol_api_versions
    assert protocol_api_versions["2.28"] == "9.0.0"

    assert "2.29" in protocol_api_versions
    assert protocol_api_versions["2.29"] == "9.1.1"


def test_info_endpoint_accepts_only_get_method(client):
    """Test that the /info endpoint only accepts GET requests."""
    # POST should not be allowed
    response = client.post("/info")
    assert response.status_code == 405  # Method Not Allowed

    # PUT should not be allowed
    response = client.put("/info")
    assert response.status_code == 405

    # DELETE should not be allowed
    response = client.delete("/info")
    assert response.status_code == 405


def test_info_endpoint_response_is_consistent(client):
    """Test that the /info endpoint returns consistent responses across multiple calls."""
    response1 = client.get("/info")
    response2 = client.get("/info")

    assert response1.json() == response2.json()


def test_info_endpoint_returns_supported_robot_versions(client):
    """Test that the /info endpoint returns supported robot server versions."""
    response = client.get("/info")
    data = response.json()

    assert "supported_robot_versions" in data
    assert isinstance(data["supported_robot_versions"], list)
    assert len(data["supported_robot_versions"]) > 0

    # Check that versions are sorted and contain expected values
    expected_versions = [
        "6.2.1",
        "8.0.0",
        "8.2.0",
        "8.3.0",
        "8.4.0",
        "8.5.0",
        "8.6.0",
        "8.7.0",
        "8.8.0",
        "9.0.0",
        "9.1.1",
        "edge",
        "next",
    ]
    assert data["supported_robot_versions"] == expected_versions

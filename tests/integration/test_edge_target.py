"""Integration tests for the edge analysis target."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from evaluate.env_config import get_environment_for_version


@pytest.fixture
def client():
    return TestClient(app)


def test_edge_is_supported_robot_version(client):
    response = client.get("/info")
    assert response.status_code == 200
    assert "edge" in response.json()["supported_robot_versions"]


def test_edge_environment_config_uses_python_312():
    config = get_environment_for_version("edge")
    assert config.python_version == "3.12"
    assert config.name == "opentrons-edge"
    assert any("opentrons.git@edge" in spec for spec in config.install_specs)


def test_edge_environment_uses_python_312_compatible_pandas():
    config = get_environment_for_version("edge")
    pandas_specs = [spec for spec in config.install_specs if "pandas" in spec]
    assert pandas_specs
    assert "1.4.3" not in pandas_specs[0]


def test_evaluate_endpoint_accepts_edge_target(client):
    from io import BytesIO

    files = {
        "protocol_file": ("protocol.py", BytesIO(b"# test protocol"), "text/plain"),
    }
    response = client.post("/evaluate", files=files, data={"robot_version": "edge"})
    assert response.status_code == 200
    assert response.json()["robot_version"] == "edge"

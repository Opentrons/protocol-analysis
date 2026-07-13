"""Unit tests for the protocol processor simulation flow."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evaluate.processor import ProtocolProcessor


@pytest.fixture
def processor(tmp_path):
    """Return a ProtocolProcessor with an isolated storage directory."""
    instance = ProtocolProcessor(storage_dir=tmp_path)
    return instance


def _build_files(tmp_path: Path) -> dict:
    job_dir = tmp_path / "job"
    labware_dir = job_dir / "labware"
    job_dir.mkdir(parents=True, exist_ok=True)
    labware_dir.mkdir(exist_ok=True)

    protocol_path = job_dir / "protocol.py"
    protocol_path.write_text("metadata = {}\n")

    custom_labware = labware_dir / "plate.json"
    custom_labware.write_text("{}")

    return {
        "job_id": "job-123",
        "job_dir": str(job_dir),
        "protocol_file": str(protocol_path),
        "labware_files": [str(custom_labware)],
        "csv_file": None,
    }


def test_run_simulation_skips_with_rtp(processor: ProtocolProcessor, tmp_path: Path):
    files = _build_files(tmp_path)
    metadata: dict[str, object] = {"rtp": {"param": 42}}

    result = processor._run_simulation(Path(sys.executable), files, "8.7.0", metadata)

    assert result["status"] == "skipped"
    assert "runtime parameter overrides" in result["reason"]


def test_run_simulation_invokes_subprocess_and_parses_output(
    processor: ProtocolProcessor, tmp_path: Path
):
    files = _build_files(tmp_path)
    metadata: dict[str, object] = {}

    completed_process = SimpleNamespace(
        stdout='{"formatted_runlog": "commands"}',
        stderr="",
        returncode=0,
    )

    with patch(
        "evaluate.processor.subprocess.run", return_value=completed_process
    ) as mocked_run:
        result = processor._run_simulation(
            Path(sys.executable), files, "8.7.0", metadata
        )

    assert result["status"] == "success"
    assert result["simulation"] == {"formatted_runlog": "commands"}
    assert result["metadata"]["labware_search_paths"] == [
        str(Path(files["job_dir"]) / "labware")
    ]
    mocked_run.assert_called_once()

"""Slow integration test that exercises real edge environment analysis."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from evaluate.env_config import get_environment_for_version
from evaluate.job_status import JobStatus, write_job_metadata, write_job_status
from evaluate.processor import ProtocolProcessor
from evaluate.venv_manager import VenvManager

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _edge_enabled() -> bool:
    return os.getenv("PROTOCOL_EVALUATION_ENABLE_EDGE", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@pytest.mark.skipif(
    not _edge_enabled(),
    reason="Set PROTOCOL_EVALUATION_ENABLE_EDGE=1 to run real edge analysis",
)
def test_edge_analysis_against_git_branch(tmp_path: Path):
    """Build or reuse the edge venv and run a real protocol analysis."""
    protocol_src = Path("test-files/simple/Flex_S_v2_24_P50_PAPI_Changes.py")
    assert protocol_src.exists()

    config = get_environment_for_version("edge")
    python_path = VenvManager().ensure_venv_exists(config)

    import subprocess

    version_proc = subprocess.run(
        [str(python_path), "-c", "import opentrons; print(opentrons.__version__)"],
        check=True,
        capture_output=True,
        text=True,
    )
    installed_version = version_proc.stdout.strip()
    assert installed_version

    storage = tmp_path / "jobs"
    job_id = str(uuid.uuid4())
    job_dir = storage / job_id
    job_dir.mkdir(parents=True)
    shutil.copy(protocol_src, job_dir / protocol_src.name)
    write_job_metadata(job_dir, "edge")
    write_job_status(job_dir, JobStatus.PENDING)

    processor = ProtocolProcessor(storage_dir=storage)
    processor.process_job(job_id)

    status = json.loads((job_dir / "status.json").read_text())
    analysis = json.loads((job_dir / "completed_analysis.json").read_text())

    assert status["status"] == "completed"
    assert analysis["status"] == "success"
    assert analysis["robot_version"] == "edge"
    assert analysis["analysis"]["result"] == "ok"

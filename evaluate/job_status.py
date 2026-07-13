"""Job status management for protocol analysis."""

import json
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class JobStatus(str, Enum):
    """Status of an analysis job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def write_job_metadata(
    job_dir: Path, robot_version: str, **additional_metadata: Any
) -> None:
    """Write job metadata to a metadata file.

    Args:
        job_dir: Path to the job directory
        robot_version: Robot server version to analyze against
        **additional_metadata: Additional metadata to store
    """
    metadata_file = job_dir / "metadata.json"
    metadata = {
        "robot_version": robot_version,
        "created_at": datetime.now(UTC).isoformat(),
        **additional_metadata,
    }
    metadata_file.write_text(json.dumps(metadata, indent=2))


def read_job_metadata(job_dir: Path) -> dict:
    """Read job metadata from metadata file.

    Args:
        job_dir: Path to the job directory

    Returns:
        Dictionary containing job metadata
    """
    metadata_file = job_dir / "metadata.json"

    if not metadata_file.exists():
        return {}

    return json.loads(metadata_file.read_text())


def write_job_status(
    job_dir: Path, status: JobStatus, error: str | None = None
) -> None:
    """Write job status to a status file.

    Args:
        job_dir: Path to the job directory
        status: Current status of the job
        error: Optional error message if status is FAILED
    """
    status_file = job_dir / "status.json"
    status_data = {
        "status": status.value,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    if error:
        status_data["error"] = error

    status_file.write_text(json.dumps(status_data, indent=2))


def read_job_status(job_dir: Path) -> dict:
    """Read job status from status file.

    Args:
        job_dir: Path to the job directory

    Returns:
        Dictionary containing status information
    """
    status_file = job_dir / "status.json"

    if not status_file.exists():
        return {"status": JobStatus.PENDING.value}

    return json.loads(status_file.read_text())


def is_job_completed(job_dir: Path) -> bool:
    """Check if a job has completed analysis.

    Args:
        job_dir: Path to the job directory

    Returns:
        True if completed_analysis.json exists
    """
    return (job_dir / "completed_analysis.json").exists()

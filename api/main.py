"""FastAPI application for protocol evaluation."""

from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from evaluate.job_status import (
    JobStatus,
    read_job_status,
    write_job_metadata,
    write_job_status,
)
from evaluate.processor_heartbeat import get_processor_readiness
from api.file_storage import file_storage
from api.version_mapping import PROTOCOL_API_TO_ROBOT_STACK, VALID_ROBOT_VERSIONS

# Get version from package metadata
VERSION = "0.1.0"

app = FastAPI(
    title="Protocol Evaluation API",
    description="API for evaluating Opentrons protocols",
    version=VERSION,
)


class InfoResponse(BaseModel):
    """Response model for the /info endpoint."""

    version: str
    protocol_api_versions: dict[str, str]
    supported_robot_versions: list[str]


class ReadyResponse(BaseModel):
    """Response model for the /ready endpoint."""

    api: str
    processor_ready: bool
    processor_last_heartbeat: str | None
    processor_heartbeat_age_seconds: float | None
    processor_heartbeat_max_age_seconds: int


@app.get("/info", response_model=InfoResponse)
async def get_info() -> InfoResponse:
    """
    Get application information.

    Returns:
        InfoResponse containing:
        - version: The current application version
        - protocol_api_versions: Mapping of protocol API versions to robot stack versions
        - supported_robot_versions: List of supported robot server versions
    """
    return InfoResponse(
        version=VERSION,
        protocol_api_versions=PROTOCOL_API_TO_ROBOT_STACK,
        supported_robot_versions=sorted(VALID_ROBOT_VERSIONS),
    )


@app.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness probe",
    description="Reports whether the API is up and whether the processor appears alive.",
)
async def get_ready(
    processor_max_age_seconds: int = Query(
        30,
        ge=1,
        le=3600,
        description="Max heartbeat age (seconds) before considering the processor not ready.",
    ),
) -> ReadyResponse:
    readiness = get_processor_readiness(
        file_storage.base_dir, max_age_seconds=processor_max_age_seconds
    )

    return ReadyResponse(
        api="ok",
        processor_ready=readiness.ready,
        processor_last_heartbeat=readiness.last_heartbeat,
        processor_heartbeat_age_seconds=readiness.age_seconds,
        processor_heartbeat_max_age_seconds=readiness.max_age_seconds,
    )


class EvaluateResponse(BaseModel):
    """Response model for the /evaluate endpoint."""

    job_id: str
    protocol_file: str
    labware_files: list[str]
    csv_file: str | None
    rtp: dict[str, Any] | None
    robot_version: str


class JobStatusResponse(BaseModel):
    """Response model for job status endpoint."""

    job_id: str
    status: str
    updated_at: str | None = None
    error: str | None = None


class JobResultResponse(BaseModel):
    """Response model for completed job results."""

    job_id: str
    status: str
    result_type: Literal["analysis", "simulation"]
    result: dict[str, Any] | None = None
    error: str | None = None


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_protocol(
    robot_version: str = Form(
        ..., description="Robot server version (e.g., '8.7.0', 'next')"
    ),
    protocol_file: UploadFile = File(..., description="Python protocol file (.py)"),
    labware_files: list[UploadFile] = File(
        default=[], description="Optional custom labware JSON files"
    ),
    csv_file: UploadFile | None = File(
        default=None,
        description="Optional CSV file (.csv or .txt) used for add_csv_file runtime parameter",
    ),
    rtp: str | None = Form(default=None, description="Optional RTP JSON object"),
) -> EvaluateResponse:
    """
    Evaluate a protocol file with optional custom labware, CSV data, and runtime parameters.

    Args:
        robot_version: Robot server version (e.g., '8.7.0', 'next')
        protocol_file: Required Python protocol file (.py extension)
        labware_files: Optional list of custom labware definition files (.json)
        csv_file: Optional CSV file (.csv or .txt extension)
        rtp: Optional runtime parameters as JSON string

    Returns:
        EvaluateResponse with details about the uploaded files

    Raises:
        HTTPException: If file extensions are invalid or version is unsupported
    """
    import json

    # Validate robot server version
    if robot_version not in VALID_ROBOT_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported robot server version: {robot_version}. "
            f"Supported versions: {', '.join(sorted(VALID_ROBOT_VERSIONS))}",
        )

    # Validate protocol file extension
    if not protocol_file.filename or not protocol_file.filename.endswith(".py"):
        raise HTTPException(
            status_code=400,
            detail="Protocol file must have a .py extension",
        )

    # Validate labware files extensions
    labware_filenames = []
    for labware_file in labware_files:
        if not labware_file.filename or not labware_file.filename.endswith(".json"):
            raise HTTPException(
                status_code=400,
                detail=f"Labware file '{labware_file.filename}' must have a .json extension",
            )
        labware_filenames.append(labware_file.filename)

    # Validate CSV file extensions if provided
    csv_filename: str | None = None
    if csv_file and csv_file.filename:
        if not (
            csv_file.filename.endswith(".csv") or csv_file.filename.endswith(".txt")
        ):
            raise HTTPException(
                status_code=400,
                detail="CSV file must have a .csv or .txt extension",
            )
        csv_filename = csv_file.filename

    # Parse RTP JSON if provided
    rtp_data = None
    if rtp:
        try:
            rtp_data = json.loads(rtp)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid RTP JSON: {str(e)}",
            )

    # Create job directory and save files synchronously
    job_id = file_storage.create_job_directory()
    job_dir = file_storage.base_dir / job_id

    metadata_extra: dict[str, Any] = {}
    if rtp_data is not None:
        metadata_extra["rtp"] = rtp_data
    if csv_filename:
        metadata_extra["csv_file"] = csv_filename

    # Save job metadata with robot server version
    write_job_metadata(job_dir, robot_version, **metadata_extra)

    # Save files synchronously (file I/O is fast enough)
    await file_storage.save_protocol_file(job_id, protocol_file)

    if labware_files:
        await file_storage.save_labware_files(job_id, labware_files)

    if csv_file:
        await file_storage.save_csv_file(job_id, csv_file)

    # Mark job as pending for the processor to pick up
    write_job_status(job_dir, JobStatus.PENDING)

    return EvaluateResponse(
        job_id=job_id,
        protocol_file=protocol_file.filename,
        labware_files=labware_filenames,
        csv_file=csv_filename,
        rtp=rtp_data,
        robot_version=robot_version,
    )


@app.get(
    "/jobs/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Check the status of an analysis job",
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Get the current status of an analysis job.

    Args:
        job_id: The job ID to check

    Returns:
        JobStatusResponse with current status and timestamp

    Raises:
        HTTPException: If job is not found
    """
    job_dir = file_storage.base_dir / job_id

    if not file_storage.job_exists(job_id):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    status_data = read_job_status(job_dir)

    return JobStatusResponse(
        job_id=job_id,
        status=status_data.get("status", "pending"),
        updated_at=status_data.get("updated_at"),
        error=status_data.get("error"),
    )


@app.get(
    "/jobs/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get job result",
    description="Get the analysis result for a completed job",
)
async def get_job_result(
    job_id: str,
    result_type: Literal["analysis", "simulation"] = Query(
        "analysis",
        description="Which evaluation artifact to return",
    ),
) -> JobResultResponse:
    """
    Get the analysis result for a completed job.

    Args:
        job_id: The job ID to retrieve

    Returns:
        JobResultResponse with requested evaluation data if completed

    Raises:
        HTTPException: If job is not found or not yet completed
    """
    import json

    job_dir = file_storage.base_dir / job_id

    if not file_storage.job_exists(job_id):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    status_data = read_job_status(job_dir)
    status = status_data.get("status", "pending")

    # Check if job has completed
    artifact_filename = (
        "completed_analysis.json"
        if result_type == "analysis"
        else "completed_simulation.json"
    )
    artifact_file = job_dir / artifact_filename

    if not artifact_file.exists():
        if status == JobStatus.FAILED.value:
            return JobResultResponse(
                job_id=job_id,
                status=status,
                result_type=result_type,
                error=status_data.get("error", "Job failed"),
            )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requested {result_type} results are not available yet for job {job_id}."
                f" Current status: {status}"
            ),
        )

    result_data = json.loads(artifact_file.read_text())

    return JobResultResponse(
        job_id=job_id,
        status=status,
        result_type=result_type,
        result=result_data,
    )

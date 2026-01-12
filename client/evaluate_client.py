"""Client for uploading protocols and retrieving evaluation results."""

import asyncio
import json
import os
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx


class EvaluationClient:
    """Client for interacting with the protocol evaluation API."""

    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.Client | None = None,
    ):
        """Initialize the client with the base API URL."""
        self.base_url = base_url or os.getenv(
            "PROTOCOL_EVALUATION_BASE_URL", "http://127.0.0.1:8000"
        )
        self.client = http_client or httpx.Client(timeout=30.0)
        self._owns_client = http_client is None

    def get_info(self) -> dict[str, Any]:
        """Get API information."""
        response = self.client.get(f"{self.base_url}/info")
        response.raise_for_status()
        return response.json()

    def get_ready(self, processor_max_age_seconds: int | None = None) -> dict[str, Any]:
        """Get API + processor readiness information.

        Args:
            processor_max_age_seconds: Optional heartbeat max age (seconds).

        Returns:
            JSON response from GET /ready.
        """
        params: dict[str, Any] = {}
        if processor_max_age_seconds is not None:
            params["processor_max_age_seconds"] = processor_max_age_seconds

        response = self.client.get(f"{self.base_url}/ready", params=params)
        response.raise_for_status()
        return response.json()

    def submit_protocol(
        self,
        protocol_file: Path,
        robot_version: str = "8.7.0",
        labware_files: list[Path] | None = None,
        csv_file: Path | None = None,
        rtp: dict[str, Any] | None = None,
    ) -> str:
        """
        Submit a protocol for evaluation.

        Args:
            protocol_file: Path to the protocol file
            robot_version: Robot server version (e.g., '8.7.0', 'next')
            labware_files: Optional list of custom labware definition files
            csv_file: Optional CSV/text file containing runtime data
            rtp: Optional runtime parameter object to send as JSON

        Returns:
            Job ID for tracking the evaluation
        """
        with ExitStack() as stack:
            protocol_handle = stack.enter_context(open(protocol_file, "rb"))
            files: list[tuple[str, tuple[str, Any, str]]] = [
                (
                    "protocol_file",
                    (protocol_file.name, protocol_handle, "text/x-python"),
                )
            ]

            if labware_files:
                for labware_file in labware_files:
                    labware_handle = stack.enter_context(open(labware_file, "rb"))
                    files.append(
                        (
                            "labware_files",
                            (
                                labware_file.name,
                                labware_handle,
                                "application/json",
                            ),
                        )
                    )

            if csv_file:
                csv_handle = stack.enter_context(open(csv_file, "rb"))
                content_type = (
                    "text/csv" if csv_file.suffix.lower() == ".csv" else "text/plain"
                )
                files.append(
                    (
                        "csv_file",
                        (
                            csv_file.name,
                            csv_handle,
                            content_type,
                        ),
                    )
                )

            data = {"robot_version": robot_version}
            if rtp is not None:
                data["rtp"] = json.dumps(rtp)

            response = self.client.post(
                f"{self.base_url}/evaluate",
                files=files,
                data=data,
            )
            response.raise_for_status()
            result = response.json()
            return result["job_id"]

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get the status of a job."""
        response = self.client.get(f"{self.base_url}/jobs/{job_id}/status")
        response.raise_for_status()
        return response.json()

    def get_job_result(
        self, job_id: str, result_type: str = "analysis"
    ) -> dict[str, Any]:
        """Get either the analysis or simulation result for a completed job."""
        response = self.client.get(
            f"{self.base_url}/jobs/{job_id}/result",
            params={"result_type": result_type},
        )
        response.raise_for_status()
        return response.json()

    def wait_for_completion(
        self, job_id: str, poll_interval: float = 1.0, max_wait: float = 300.0
    ) -> dict[str, Any]:
        """
        Poll job status until completion or timeout.

        Args:
            job_id: Job ID to poll
            poll_interval: Seconds between polls
            max_wait: Maximum seconds to wait

        Returns:
            Final job status

        Raises:
            TimeoutError: If job doesn't complete within max_wait
        """
        start_time = time.time()
        while True:
            status = self.get_job_status(job_id)

            if status["status"] in ["completed", "failed"]:
                return status

            elapsed = time.time() - start_time
            if elapsed > max_wait:
                raise TimeoutError(
                    f"Job {job_id} did not complete within {max_wait} seconds"
                )

            time.sleep(poll_interval)

    def close(self):
        """Close the HTTP client."""
        if self._owns_client:
            self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class AsyncEvaluationClient:
    """Async client for interacting with the protocol evaluation API."""

    def __init__(
        self,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        """Initialize the async client with the base API URL."""
        self.base_url = base_url or os.getenv(
            "PROTOCOL_EVALUATION_BASE_URL", "http://127.0.0.1:8000"
        )
        self.client = http_client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = http_client is None

    async def get_info(self) -> dict[str, Any]:
        """Get API information."""
        response = await self.client.get(f"{self.base_url}/info")
        response.raise_for_status()
        return response.json()

    async def get_ready(
        self, processor_max_age_seconds: int | None = None
    ) -> dict[str, Any]:
        """Get API + processor readiness information.

        Args:
            processor_max_age_seconds: Optional heartbeat max age (seconds).

        Returns:
            JSON response from GET /ready.
        """
        params: dict[str, Any] = {}
        if processor_max_age_seconds is not None:
            params["processor_max_age_seconds"] = processor_max_age_seconds

        response = await self.client.get(f"{self.base_url}/ready", params=params)
        response.raise_for_status()
        return response.json()

    async def submit_protocol(
        self,
        protocol_file: Path,
        robot_version: str = "8.7.0",
        labware_files: list[Path] | None = None,
        csv_file: Path | None = None,
        rtp: dict[str, Any] | None = None,
    ) -> str:
        """Submit a protocol for evaluation."""

        with ExitStack() as stack:
            protocol_handle = stack.enter_context(open(protocol_file, "rb"))
            files: list[tuple[str, tuple[str, Any, str]]] = [
                (
                    "protocol_file",
                    (protocol_file.name, protocol_handle, "text/x-python"),
                )
            ]

            if labware_files:
                for labware_file in labware_files:
                    labware_handle = stack.enter_context(open(labware_file, "rb"))
                    files.append(
                        (
                            "labware_files",
                            (
                                labware_file.name,
                                labware_handle,
                                "application/json",
                            ),
                        )
                    )

            if csv_file:
                csv_handle = stack.enter_context(open(csv_file, "rb"))
                content_type = (
                    "text/csv" if csv_file.suffix.lower() == ".csv" else "text/plain"
                )
                files.append(
                    (
                        "csv_file",
                        (
                            csv_file.name,
                            csv_handle,
                            content_type,
                        ),
                    )
                )

            data = {"robot_version": robot_version}
            if rtp is not None:
                data["rtp"] = json.dumps(rtp)

            response = await self.client.post(
                f"{self.base_url}/evaluate",
                files=files,
                data=data,
            )
            response.raise_for_status()
            result = response.json()
            return result["job_id"]

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get the status of a job."""
        response = await self.client.get(f"{self.base_url}/jobs/{job_id}/status")
        response.raise_for_status()
        return response.json()

    async def get_job_result(
        self, job_id: str, result_type: str = "analysis"
    ) -> dict[str, Any]:
        """Get either the analysis or simulation result for a completed job."""
        response = await self.client.get(
            f"{self.base_url}/jobs/{job_id}/result",
            params={"result_type": result_type},
        )
        response.raise_for_status()
        return response.json()

    async def wait_for_completion(
        self, job_id: str, poll_interval: float = 1.0, max_wait: float = 300.0
    ) -> dict[str, Any]:
        """Poll job status until completion or timeout."""

        start_time = time.time()
        while True:
            status = await self.get_job_status(job_id)

            if status["status"] in ["completed", "failed"]:
                return status

            elapsed = time.time() - start_time
            if elapsed > max_wait:
                raise TimeoutError(
                    f"Job {job_id} did not complete within {max_wait} seconds"
                )

            await asyncio.sleep(poll_interval)

    async def close(self):
        """Close the HTTP client."""
        if self._owns_client:
            await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

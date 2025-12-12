"""Protocol analysis processor service.

This service monitors for new analysis jobs and processes them.
It's designed to run separately from the FastAPI server.
"""

import json
import re
import subprocess
import time
import ast
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from evaluate.env_config import get_environment_for_version, get_supported_versions
from evaluate.job_status import (
    JobStatus,
    read_job_metadata,
    read_job_status,
    write_job_status,
)
from evaluate.venv_manager import VenvManager
from api.config import STORAGE_BASE_DIR
from evaluate.processor_heartbeat import write_processor_heartbeat

ANALYSIS_TIMEOUT = 120  # Timeout per protocol in seconds
SIMULATION_TIMEOUT = ANALYSIS_TIMEOUT


class ProtocolProcessor:
    """Process protocol analysis jobs."""

    def __init__(self, storage_dir: Path = STORAGE_BASE_DIR):
        """Initialize the processor.

        Args:
            storage_dir: Base directory for job storage
        """
        self.storage_dir = storage_dir
        self.venv_manager = VenvManager()
        self._environments_warmed = False

    def warm_up_environments(self, *, max_workers: int = 4) -> dict[str, bool]:
        """Create venvs for all configured versions and verify opentrons is importable.

        This reduces first-job latency and catches broken environments early.
        """

        versions = sorted(get_supported_versions())

        # Installing from the Opentrons/opentrons repo branch can be slow.
        # Keep 'edge' capability, but don't warm it up unless explicitly enabled.
        enable_edge = os.getenv("PROTOCOL_EVALUATION_ENABLE_EDGE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if not enable_edge:
            versions = [v for v in versions if v != "edge"]

        if not versions:
            self._environments_warmed = True
            return {}

        def _setup(version: str) -> tuple[str, bool]:
            try:
                config = get_environment_for_version(version)
                python_path = self.venv_manager.ensure_venv_exists(config)
                self._print_environment_debug(version, python_path)
                ok = self._check_opentrons_installed(python_path)
                return version, ok
            except Exception as e:  # pragma: no cover - defensive
                print(f"Warm-up failed for {version}: {e}")
                return version, False

        results: dict[str, bool] = {}
        worker_count = min(max_workers, len(versions))
        print(f"Warming up {len(versions)} environments (workers={worker_count})...")
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(_setup, v) for v in versions]
            for future in as_completed(futures):
                version, ok = future.result()
                results[version] = ok

        self._environments_warmed = True

        not_ready = sorted([v for v, ok in results.items() if not ok])
        if not_ready:
            print("Warm-up completed with failures for: " + ", ".join(not_ready))
        else:
            print("Warm-up completed successfully.")

        return results

    def _check_opentrons_installed(self, python_path: Path) -> bool:
        """Return True if opentrons can be imported in the given venv."""
        try:
            subprocess.run(
                [str(python_path), "-c", "import opentrons; print('ok')"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return True
        except Exception as e:
            print(f"opentrons import check failed for {python_path}: {e}")
            return False

    def _print_environment_debug(self, version: str, python_path: Path) -> None:
        """Print environment diagnostics to stdout (captured by service logs)."""

        def _run(cmd: list[str]) -> str:
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                out = (proc.stdout or "").strip()
                err = (proc.stderr or "").strip()
                if out and err:
                    return out + "\n" + err
                return out or err
            except Exception as e:  # pragma: no cover
                return f"<failed to run {' '.join(cmd)}: {e}>"

        print("=" * 80)
        print(f"Environment debug for {version}")
        print(f"python: {python_path}")
        print("python --version:")
        print(_run([str(python_path), "--version"]))
        print("pip --version:")
        print(_run([str(python_path), "-m", "pip", "--version"]))
        print("pip list:")
        print(_run([str(python_path), "-m", "pip", "list"]))
        print("=" * 80)

    def get_job_files(self, job_id: str) -> dict[str, Any]:
        """Get all files for a job.

        Args:
            job_id: The job ID

        Returns:
            Dictionary with file paths and metadata
        """
        job_dir = self.storage_dir / job_id

        files: dict[str, Any] = {
            "job_id": job_id,
            "job_dir": str(job_dir),
            "protocol_file": None,
            "labware_files": [],
            "csv_file": None,
        }

        # Find protocol file
        for py_file in job_dir.glob("*.py"):
            files["protocol_file"] = str(py_file)
            break

        # Find labware files
        labware_dir = job_dir / "labware"
        if labware_dir.exists():
            files["labware_files"] = [str(f) for f in labware_dir.glob("*.json")]

        # Find CSV/TXT file (treated as CSV input)
        for pattern in ("*.csv", "*.txt"):
            csv_match = next(job_dir.glob(pattern), None)
            if csv_match:
                files["csv_file"] = str(csv_match)
                break

        return files

    def process_job(self, job_id: str) -> None:
        """Process a single job.

        Args:
            job_id: The job ID to process
        """
        job_dir = self.storage_dir / job_id

        if not job_dir.exists():
            print(f"Job directory not found: {job_id}")
            return

        # Check if already completed
        if (job_dir / "completed_analysis.json").exists():
            print(f"Job {job_id} already completed")
            return

        # Update status to processing
        write_job_status(job_dir, JobStatus.PROCESSING)
        print(f"Processing job {job_id}...")

        try:
            # Read job metadata to get robot server version
            metadata = read_job_metadata(job_dir)
            robot_version = metadata.get("robot_version")

            if not robot_version:
                raise ValueError(
                    "Job metadata missing robot_version. "
                    "This job may have been created before version support was added."
                )

            print(f"Job requires robot server version: {robot_version}")

            # Get environment configuration for this version
            env_config = get_environment_for_version(robot_version)

            # Ensure the virtual environment exists
            python_path = self.venv_manager.ensure_venv_exists(env_config)
            print(f"Using Python: {python_path}")

            # Get all job files
            files = self.get_job_files(job_id)

            # Run the actual analysis using the protocol in the correct venv
            analysis_result = self._run_analysis(
                python_path, files, robot_version, metadata
            )

            # Write completed analysis
            completed_file = job_dir / "completed_analysis.json"
            completed_file.write_text(json.dumps(analysis_result, indent=2))

            # Run the simulation in the same environment (best-effort)
            try:
                simulation_result = self._run_simulation(
                    python_path, files, robot_version, metadata
                )
            except Exception as sim_error:  # pragma: no cover - defensive catch
                import traceback

                print(f"Job {job_id} simulation failed: {sim_error}")
                print(f"Traceback: {traceback.format_exc()}")
                simulation_result = {
                    "job_id": job_id,
                    "status": "error",
                    "error": f"Simulation failed with unexpected error: {sim_error}",
                    "robot_version": robot_version,
                }

            simulation_file = job_dir / "completed_simulation.json"
            simulation_file.write_text(json.dumps(simulation_result, indent=2))

            # Update status to completed
            write_job_status(job_dir, JobStatus.COMPLETED)
            print(f"Job {job_id} completed successfully")

        except Exception as e:
            import traceback

            error_msg = f"Error processing job: {str(e)}"
            print(f"Job {job_id} failed: {error_msg}")
            print(f"Traceback: {traceback.format_exc()}")
            write_job_status(job_dir, JobStatus.FAILED, error=error_msg)

    def _extract_first_json_object(self, text: str) -> dict[str, Any] | None:
        """
        Attempts to extract the first valid JSON object from the given text string.
        Returns the parsed dict, or None if extraction fails.
        """
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except Exception:
            return None

    def _run_analysis(
        self,
        python_path: Path,
        files: dict[str, Any],
        robot_version: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Run protocol analysis in the specified virtual environment.

        Args:
            python_path: Path to the Python executable in the venv
            files: Dictionary containing file paths
            robot_version: Robot server version being used

        Returns:
            Analysis result dictionary
        """
        protocol_file = files.get("protocol_file")
        if not protocol_file:
            return {
                "job_id": files["job_id"],
                "status": "error",
                "error": "No protocol file found",
                "robot_version": robot_version,
            }

        # Build runtime parameter mappings (CSV files + explicit RTP values)
        rtp_values_json, rtp_files_json = self._build_runtime_parameters(
            metadata, files
        )

        # Build the analysis command using opentrons.cli.analyze
        cmd = [
            str(python_path),
            "-c",
            """
import asyncio
import io
import json
import sys
from pathlib import Path
from opentrons.cli.analyze import _analyze, _Output

protocol_file = Path(sys.argv[1])
labware_files = [Path(p) for p in sys.argv[2].split(',') if p]
rtp_values = sys.argv[3]
rtp_files = sys.argv[4]
files = labware_files + [protocol_file]
json_output_stream = io.BytesIO()
outputs = [_Output(to_file=json_output_stream, kind='json')]

try:
    exit_code = asyncio.run(_analyze(files, rtp_values, rtp_files, outputs, False, False, False))
except Exception as e:
    print(json.dumps({'error': f'Exception: {str(e)}'}), file=sys.stdout)
    sys.exit(1)

json_output_stream.seek(0)
json_bytes = json_output_stream.read()
try:
    json_str = json_bytes.decode('utf-8')
    result_json = json.loads(json_str)
except Exception:
    result_json = {'error': 'Failed to decode JSON output'}

print(json.dumps(result_json), file=sys.stdout)
sys.exit(exit_code)
""",
            protocol_file,
            ",".join(files.get("labware_files", [])),
            rtp_values_json,
            rtp_files_json,
        ]

        try:
            # Run the analysis with a timeout
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=ANALYSIS_TIMEOUT,
            )

            stdout = proc.stdout
            stderr = proc.stderr

            # Parse the result
            result_json = None
            try:
                result_json = json.loads(stdout)
            except Exception:
                result_json = self._extract_first_json_object(stdout)
                if result_json is None:
                    result_json = {
                        "error": "Failed to decode JSON output",
                        "raw": stdout,
                        "stderr": stderr,
                    }

            # Wrap the analysis result with our metadata
            return {
                "job_id": files["job_id"],
                "status": "success" if proc.returncode == 0 else "error",
                "robot_version": robot_version,
                "files_analyzed": {
                    "protocol_file": Path(protocol_file).name,
                    "labware_files": [
                        Path(f).name for f in files.get("labware_files", [])
                    ],
                    "csv_file": Path(files["csv_file"]).name
                    if files.get("csv_file")
                    else None,
                },
                "analysis": result_json,
                "logs": stderr,
                "metadata": {
                    "robot_version": robot_version,
                    "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "python_path": str(python_path),
                    "exit_code": proc.returncode,
                    "csv_parameter_map": json.loads(rtp_files_json)
                    if rtp_files_json
                    else {},
                },
            }

        except subprocess.TimeoutExpired:
            return {
                "job_id": files["job_id"],
                "status": "error",
                "error": f"Analysis timed out after {ANALYSIS_TIMEOUT} seconds",
                "robot_version": robot_version,
                "files_analyzed": {
                    "protocol_file": Path(protocol_file).name,
                    "csv_file": Path(files["csv_file"]).name
                    if files.get("csv_file")
                    else None,
                },
            }
        except Exception as e:
            return {
                "job_id": files["job_id"],
                "status": "error",
                "error": f"Analysis failed with error: {str(e)}",
                "robot_version": robot_version,
                "files_analyzed": {
                    "protocol_file": Path(protocol_file).name,
                    "csv_file": Path(files["csv_file"]).name
                    if files.get("csv_file")
                    else None,
                },
            }

    def find_pending_jobs(self) -> list[str]:
        """Find all pending jobs that need processing.

        Returns:
            List of job IDs that are pending
        """
        pending_jobs: list[str] = []

        if not self.storage_dir.exists():
            return pending_jobs

        for job_dir in self.storage_dir.iterdir():
            if not job_dir.is_dir():
                continue

            job_id = job_dir.name

            # Skip if already has completed analysis
            if (job_dir / "completed_analysis.json").exists():
                continue

            # Check status
            status_data = read_job_status(job_dir)
            if status_data.get("status") in [
                JobStatus.PENDING.value,
                JobStatus.FAILED.value,
            ]:
                pending_jobs.append(job_id)

        return pending_jobs

    def _build_runtime_parameters(
        self, metadata: dict[str, Any] | None, files: dict[str, Any]
    ) -> tuple[str, str]:
        """Construct runtime parameter JSON strings for opentrons CLI."""

        rtp_values: dict[str, Any] = {}
        if metadata:
            stored_rtp = metadata.get("rtp")
            if isinstance(stored_rtp, dict):
                rtp_values = stored_rtp

        csv_map = self._map_csv_parameter(files)

        return json.dumps(rtp_values or {}), json.dumps(csv_map or {})

    def _map_csv_parameter(self, files: dict[str, Any]) -> dict[str, str]:
        """Map the single CSV parameter name to the uploaded file path."""

        protocol_path = files.get("protocol_file")
        csv_path = files.get("csv_file")

        if not protocol_path or not csv_path:
            return {}

        param_names = self._extract_csv_parameter_names(Path(protocol_path))

        if not param_names:
            return {}

        if len(param_names) > 1:
            raise ValueError("Only one CSV File parameter can be defined per protocol.")

        return {param_names[0]: csv_path}

    def _extract_csv_parameter_names(self, protocol_path: Path) -> list[str]:
        """Parse protocol file to find add_csv_file variable names."""

        try:
            source = protocol_path.read_text()
            tree = ast.parse(source)
        except Exception:
            return []

        parameter_names: list[str] = []

        class _CsvParamVisitor(ast.NodeVisitor):
            def __init__(self):
                self.names: list[str] = []
                self._inside_target = False

            def visit_FunctionDef(self, node: ast.FunctionDef):
                if node.name == "add_parameters":
                    prev = self._inside_target
                    self._inside_target = True
                    self.generic_visit(node)
                    self._inside_target = prev
                else:
                    self.generic_visit(node)

            def visit_Call(self, node: ast.Call):
                if (
                    self._inside_target
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_csv_file"
                ):
                    for kw in node.keywords:
                        if (
                            kw.arg == "variable_name"
                            and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)
                        ):
                            self.names.append(kw.value.value)
                self.generic_visit(node)

        visitor = _CsvParamVisitor()
        visitor.visit(tree)
        parameter_names.extend(visitor.names)
        return parameter_names

    def _get_simulation_skip_reason(
        self, metadata: dict[str, Any] | None, files: dict[str, Any]
    ) -> str | None:
        """Determine if simulation should be skipped due to unsupported inputs."""

        reasons: list[str] = []

        if metadata:
            rtp_data = metadata.get("rtp")
            if isinstance(rtp_data, dict) and rtp_data:
                reasons.append("runtime parameter overrides are present")

        if files.get("csv_file"):
            reasons.append("runtime parameter CSV input is provided")

        if not reasons:
            return None

        joined = " and ".join(reasons)
        return f"Simulation skipped because {joined}."

    def _get_labware_search_paths(self, files: dict[str, Any]) -> list[str]:
        """Return directories that should be searched for custom labware."""

        job_dir = files.get("job_dir")
        if not job_dir:
            return []

        labware_dir = Path(job_dir) / "labware"
        if labware_dir.exists():
            return [str(labware_dir)]
        return []

    def _run_simulation(
        self,
        python_path: Path,
        files: dict[str, Any],
        robot_version: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Run protocol simulation when supported and capture output."""

        protocol_file = files.get("protocol_file")
        if not protocol_file:
            return {
                "job_id": files.get("job_id"),
                "status": "error",
                "error": "No protocol file found",
                "robot_version": robot_version,
            }

        skip_reason = self._get_simulation_skip_reason(metadata, files)
        if skip_reason:
            return {
                "job_id": files.get("job_id"),
                "status": "skipped",
                "reason": skip_reason,
                "robot_version": robot_version,
                "files_analyzed": {
                    "protocol_file": Path(protocol_file).name,
                    "labware_files": [
                        Path(f).name for f in files.get("labware_files", [])
                    ],
                    "csv_file": Path(files["csv_file"]).name
                    if files.get("csv_file")
                    else None,
                },
            }

        labware_dirs = self._get_labware_search_paths(files)
        labware_arg = ",".join(labware_dirs)

        cmd = [
            str(python_path),
            "-c",
            """
import json
import sys
from pathlib import Path
from opentrons.simulate import simulate, format_runlog

protocol_file = Path(sys.argv[1])
labware_dirs = [p for p in sys.argv[2].split(',') if p]

with protocol_file.open() as proto_handle:
    runlog, _bundle = simulate(
        proto_handle,
        custom_labware_paths=labware_dirs,
    )

formatted_runlog = format_runlog(runlog)
print(json.dumps({
    'formatted_runlog': formatted_runlog,
    'command_count': len(runlog),
}))
""",
            protocol_file,
            labware_arg,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SIMULATION_TIMEOUT,
            )

            stdout = proc.stdout
            stderr = proc.stderr

            simulation_json = None
            try:
                simulation_json = json.loads(stdout)
            except Exception:
                simulation_json = self._extract_first_json_object(stdout)
                if simulation_json is None:
                    simulation_json = {
                        "error": "Failed to decode simulation JSON output",
                        "raw": stdout,
                        "stderr": stderr,
                    }

            return {
                "job_id": files.get("job_id"),
                "status": "success" if proc.returncode == 0 else "error",
                "robot_version": robot_version,
                "files_analyzed": {
                    "protocol_file": Path(protocol_file).name,
                    "labware_files": [
                        Path(f).name for f in files.get("labware_files", [])
                    ],
                    "csv_file": Path(files["csv_file"]).name
                    if files.get("csv_file")
                    else None,
                },
                "simulation": simulation_json,
                "logs": stderr,
                "metadata": {
                    "robot_version": robot_version,
                    "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "python_path": str(python_path),
                    "exit_code": proc.returncode,
                    "labware_search_paths": labware_dirs,
                },
            }

        except subprocess.TimeoutExpired:
            return {
                "job_id": files.get("job_id"),
                "status": "error",
                "error": f"Simulation timed out after {SIMULATION_TIMEOUT} seconds",
                "robot_version": robot_version,
                "files_analyzed": {
                    "protocol_file": Path(protocol_file).name,
                    "csv_file": Path(files["csv_file"]).name
                    if files.get("csv_file")
                    else None,
                },
            }
        except Exception as e:
            return {
                "job_id": files.get("job_id"),
                "status": "error",
                "error": f"Simulation failed with error: {str(e)}",
                "robot_version": robot_version,
                "files_analyzed": {
                    "protocol_file": Path(protocol_file).name,
                    "csv_file": Path(files["csv_file"]).name
                    if files.get("csv_file")
                    else None,
                },
            }

    def run_once(self) -> int:
        """Process all pending jobs once.

        Returns:
            Number of jobs processed
        """
        # Update heartbeat at the start of every polling cycle.
        write_processor_heartbeat(self.storage_dir)

        # Warm up environments on first run.
        if not self._environments_warmed:
            self.warm_up_environments()
        pending_jobs = self.find_pending_jobs()

        for job_id in pending_jobs:
            self.process_job(job_id)

        return len(pending_jobs)

    def run_forever(self, poll_interval: int = 5) -> None:
        """Run the processor in a loop, checking for new jobs.

        Args:
            poll_interval: Seconds to wait between checks
        """
        print(f"Protocol processor started, polling every {poll_interval}s")
        print(f"Monitoring: {self.storage_dir}")

        # Warm up environments once at startup.
        if not self._environments_warmed:
            write_processor_heartbeat(self.storage_dir)
            self.warm_up_environments()
            write_processor_heartbeat(self.storage_dir)

        while True:
            try:
                # Heartbeat even if there are no jobs.
                write_processor_heartbeat(self.storage_dir)
                processed = self.run_once()
                if processed > 0:
                    print(f"Processed {processed} job(s)")
            except KeyboardInterrupt:
                print("\nShutting down processor...")
                break
            except Exception as e:
                print(f"Error in processor loop: {e}")

            # Heartbeat before sleeping as well, to keep the timestamp fresh.
            write_processor_heartbeat(self.storage_dir)

            time.sleep(poll_interval)


if __name__ == "__main__":
    processor = ProtocolProcessor()
    processor.run_forever()

# protocol-evaluation

FastAPI service for evaluating Opentrons protocols with asynchronous analysis plus simulation.

## Features

- **`/info` endpoint**: Returns application version and protocol API to robot stack version mappings
- **`/ready` endpoint**: Readiness probe (API up + processor heartbeat seen recently)
- **`/evaluate` endpoint**: Accepts protocol files for analysis _and_ simulation with optional custom labware, CSV data, and runtime parameters
- **`/jobs/{job_id}/status` endpoint**: Check the status of an evaluation job
- **`/jobs/{job_id}/result` endpoint**: Retrieve either the analysis or simulation artifact via the `result_type` query parameter
- **Asynchronous processing**: Evaluations run in a dedicated processor service

## Architecture

This service uses a two-component architecture:

1. **FastAPI Server** (`api/main.py`): Handles file uploads and serves results
2. **Processor Service** (`evaluate/processor.py`): Runs analysis and simulation jobs asynchronously in the background

Jobs are queued via the filesystem at `storage/jobs/{job_id}/` and the processor picks them up for evaluation.

Each job specifies a target robot server version. Supported versions range from 8.0.0 through the special `next` alias, which always points at the latest published Opentrons alpha build (configured in `evaluate/env_config.py`). The processor spins up isolated virtual environments (managed via uv) per version so evaluations stay reproducible.

In addition to release targets, the API also accepts an `edge` target intended for installing and analyzing against Opentrons' `edge` branch.

## Development

### Prerequisites

- Python >= 3.10
- [uv](https://github.com/astral-sh/uv) for dependency management

### Setup

```bash
# Install dependencies
make setup

# Run linter (check only, no fixes)
make lint

# Run tests (unit + integration)
make test

# Run end-to-end tests (starts services automatically)
make test-e2e

# Run all tests and linting
make test-all

# Format code
make format
```

## CI/CD

The project uses GitHub Actions for continuous integration:

- **Linting**: Runs `ruff` to check code quality
- **Unit & Integration Tests**: Fast tests without services
- **End-to-End Tests**: Full workflow tests with services running

All checks run automatically on pull requests and pushes to `main`.

> **TODO – RTP overrides:** Runtime parameter (RTP) override scenarios are not yet implemented or tested end-to-end. Once someone needs RTP overrides, we can extend the processor/API/tests to cover the behavior.

### Running the Services

Start the FastAPI server:

```bash
make run-api
# Or manually:
uv run fastapi dev api/main.py
```

Start the processor service (in a separate terminal):

```bash
make run-processor
# Or manually:
uv run python run_processor.py
```

For one-shot processing (process pending jobs and exit):

```bash
make run-processor-once
```

The API will be available at `http://localhost:8000`

### API Documentation

Once the server is running, you can access:

- Interactive API docs: `http://localhost:8000/docs`
- ReDoc documentation: `http://localhost:8000/redoc`

### Testing

Run all tests:

```bash
make test
```

> **Note:** `make test-e2e` automatically starts both the API and processor services for you, so you don't need to run them manually before exercising full workflow tests.

Run only unit tests:

```bash
make test-unit
```

Run only integration tests:

```bash
make test-integration
```

### Makefile Targets

- `make setup` - Install dependencies with uv (including dev tools)
- `make teardown` - Remove the project virtual environment
- `make lint` - Run ruff lint + format check (no fixes)
- `make format` - Run ruff check --fix and ruff format
- `make test` - Run unit + integration tests (excludes e2e)
- `make test-unit` / `make test-integration` - Run specific suites
- `make test-e2e` - Spin up both services, run E2E tests, capture logs
- `make test-all` - Run lint, fast tests, and e2e in sequence
- `make run` - Launch both API and processor in one terminal
- `make run-api` / `make run-processor` / `make run-processor-once` - Control individual services
- `make run-client` - Execute the example client workflow
- `make clean-storage` - Delete all queued job directories
- `make clean-venvs` - Remove analysis virtual environments (recreated on demand)
- `make clean-e2e-artifacts` - Remove e2e PID + log files (`e2e-*.pid/.log`)

## Project Structure

```text
protocol-evaluation/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI application and endpoints
│   ├── file_storage.py      # File storage service
│   ├── config.py            # Configuration
│   └── version_mapping.py   # Protocol API to robot stack version mappings
├── evaluate/
│   ├── __init__.py
│   ├── env_config.py        # Robot server environment definitions
│   ├── job_status.py        # Job status management helpers
│   ├── processor.py         # Analysis + simulation processor service
│   └── venv_manager.py      # Virtual environment lifecycle helpers
├── client/
│   ├── README.md            # Usage docs for EvaluationClient
│   └── evaluate_client.py   # Sync + async clients for the API
├── tests/
│   ├── unit/
│   │   ├── test_evaluate.py
│   │   ├── test_file_storage.py
│   │   ├── test_info.py
│   │   └── test_processor.py
│   ├── integration/
│   │   ├── test_evaluate.py
│   │   └── test_info.py
│   └── e2e/
│       └── test_protocol_analysis.py
├── run_processor.py         # CLI script for running processor
├── Makefile                 # Development tasks
├── pyproject.toml           # Project dependencies and configuration
└── README.md
```

## Endpoints

### GET `/info`

Returns application information including version and protocol API version mappings.

**Response:**

```json
{
  "version": "0.1.0",
  "protocol_api_versions": {
    "2.0": "3.14.0",
    "2.1": "3.15.2",
    ...
    "2.26": "8.7.0"
  }
}
```

### POST `/evaluate`

Accepts a protocol file for evaluation with optional custom labware, CSV data, and runtime parameters.

**Parameters:**

- `protocol_file` (required): Python protocol file (`.py` extension)
- `labware_files` (optional): Array of custom labware JSON files (`.json` extension)
- `csv_file` (optional): CSV data file (`.csv` or `.txt` extension)
- `rtp` (optional): Runtime parameters as JSON object
- `robot_version` (required): Target robot server version (e.g., `8.7.0`, `next`)

**Example using curl:**

```bash
curl -X POST http://localhost:8000/evaluate \
  -F "robot_version=8.7.0" \
  -F "protocol_file=@my_protocol.py" \
  -F "labware_files=@custom_labware1.json" \
  -F "labware_files=@custom_labware2.json" \
  -F "csv_file=@plate_data.csv" \
  -F 'rtp={"volume": 100, "temperature": 37}'
```

**Response:**

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "protocol_file": "my_protocol.py",
  "labware_files": ["custom_labware1.json", "custom_labware2.json"],
  "csv_file": "plate_data.csv",
  "rtp": {
    "volume": 100,
    "temperature": 37
  },
  "robot_version": "8.7.0"
}
```

The `job_id` is a unique identifier for this evaluation job. Files are saved to `storage/jobs/{job_id}/` with the following structure:

- `{job_id}.py` - The protocol file
- `labware/` - Directory containing custom labware JSON files
- `{original_name}.csv` - Uploaded CSV/TXT file (if provided)
- `status.json` - Job status information
- `completed_analysis.json` - Result from `opentrons.cli.analyze`
- `completed_simulation.json` - Result (or skip reason) from `opentrons.simulate`

The RTP parameters are stored with the response but not persisted to disk.

Simulation is best-effort: if runtime parameter overrides or RTP CSV inputs are provided, the processor skips `simulate` and records the reason in `completed_simulation.json`.

### GET `/jobs/{job_id}/status`

Check the status of an evaluation job.

**Response:**

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "updated_at": "2024-01-15T10:30:00.123456"
}
```

Status values: `pending`, `processing`, `completed`, `failed`

### GET `/jobs/{job_id}/result`

Retrieve either the analysis or simulation results for a completed job. Use the optional `result_type` query parameter (`analysis` by default, or `simulation`).

**Response:**

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "result_type": "analysis",
  "result": {
    "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "success",
    "files_analyzed": {
      "protocol_file": "my_protocol.py",
      "labware_files": ["custom_labware1.json"],
      "csv_file": "plate_data.csv"
    },
    "analysis": {
      "commands": [],
      "labware": [],
      "pipettes": [],
      "modules": [],
      "errors": [],
      "warnings": []
    },
    "metadata": {
      "protocol_api_version": "2.26",
      "processed_at": "2024-01-15T10:30:00Z"
    }
  }
}

To retrieve the simulation output instead, append `?result_type=simulation` to the request URL.
```

## Job Processing Flow

1. **Submit**: Client POSTs to `/evaluate` with the protocol, optional labware/CSV, RTP payload, and robot version
2. **Queue**: API saves the files to `storage/jobs/{job_id}/`, persists metadata, and marks status as `pending`
3. **Process**: Processor picks up pending jobs, ensures the correct venv exists, runs analysis, then attempts simulation (skipping simulation when CSV/RTP overrides are present)
4. **Complete**: Processor writes `completed_analysis.json`, `completed_simulation.json`, and updates status to `completed`
5. **Retrieve**: Client GETs `/jobs/{job_id}/result?result_type=analysis|simulation` to fetch the desired artifact

The processor service can run:

- **Daemon mode** (default): Continuously polls for new jobs
- **One-shot mode**: Processes pending jobs and exits (useful for cron/scheduled tasks)

## Usage Example

Here's a complete example workflow:

### 1. Start the Services

Terminal 1 - Start the API server:

```bash
make run-api
```

Terminal 2 - Start the processor:

```bash
make run-processor
```

### 2. Submit a Protocol for Evaluation

```bash
curl -X POST http://localhost:8000/evaluate \
  -F "robot_version=8.7.0" \
  -F "protocol_file=@example_protocol.py" \
  | jq '.'
```

Response includes the assigned `job_id`, recorded filenames, optional RTP payload, and robot version.

### 3. Check Job Status

```bash
curl http://localhost:8000/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/status | jq '.'
```

Response:

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "updated_at": "2024-01-15T10:30:00.123456"
}
```

### 4. Retrieve Evaluation Results

```bash
# Analysis output (default)
curl "http://localhost:8000/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/result" | jq '.'

# Simulation output
curl "http://localhost:8000/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/result?result_type=simulation" | jq '.'
```

The analysis response contains protocol metadata, commands, and warnings. The simulation response mirrors `completed_simulation.json` and may indicate `status: "skipped"` with a reason when RTP overrides or CSV inputs prevent running `simulate`.

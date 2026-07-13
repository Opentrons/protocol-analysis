#!/usr/bin/env python3
"""Example client for submitting a protocol and printing the analysis result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from client.evaluate_client import EvaluationClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a protocol for evaluation")
    parser.add_argument(
        "protocol_file",
        type=Path,
        help="Path to the protocol .py file",
    )
    parser.add_argument(
        "--robot-version",
        default="8.7.0",
        help="Target robot server version (default: 8.7.0)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="API base URL (default: PROTOCOL_EVALUATION_BASE_URL or http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    if not args.protocol_file.exists():
        print(f"Protocol file not found: {args.protocol_file}", file=sys.stderr)
        return 1

    with EvaluationClient(base_url=args.base_url) as client:
        job_id = client.submit_protocol(
            args.protocol_file,
            robot_version=args.robot_version,
        )
        print(f"Submitted job {job_id}")

        status = client.wait_for_completion(job_id)
        print(f"Job status: {status['status']}")

        if status["status"] == "failed":
            print(status.get("error", "unknown error"), file=sys.stderr)
            return 1

        result = client.get_job_result(job_id)
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

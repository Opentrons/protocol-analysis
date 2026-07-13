"""Processor heartbeat utilities.

The processor runs as a separate service from the API. To let the API report a
single "ready" status that includes processor health, the processor periodically
writes a heartbeat file in the shared storage directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HEARTBEAT_FILENAME = "_processor_heartbeat.json"

__all__ = [
    "HEARTBEAT_FILENAME",
    "ProcessorReadiness",
    "get_processor_readiness",
    "write_processor_heartbeat",
]


def _heartbeat_path(storage_dir: Path) -> Path:
    return storage_dir / HEARTBEAT_FILENAME


def write_processor_heartbeat(
    storage_dir: Path, *, now: datetime | None = None
) -> None:
    """Write/update the processor heartbeat file."""
    storage_dir.mkdir(parents=True, exist_ok=True)

    if now is None:
        now = datetime.now(UTC)

    payload = {"updated_at": now.isoformat()}
    _heartbeat_path(storage_dir).write_text(json.dumps(payload, indent=2))


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        # Accept both RFC3339-like '...Z' and ISO with offset.
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except Exception:
        return None


@dataclass(frozen=True)
class ProcessorReadiness:
    ready: bool
    last_heartbeat: str | None
    age_seconds: float | None
    max_age_seconds: int


def get_processor_readiness(
    storage_dir: Path,
    *,
    max_age_seconds: int = 30,
    now: datetime | None = None,
) -> ProcessorReadiness:
    """Compute processor readiness based on the heartbeat file age."""
    if now is None:
        now = datetime.now(UTC)

    heartbeat_file = _heartbeat_path(storage_dir)
    if not heartbeat_file.exists():
        return ProcessorReadiness(
            ready=False,
            last_heartbeat=None,
            age_seconds=None,
            max_age_seconds=max_age_seconds,
        )

    try:
        raw: dict[str, Any] = json.loads(heartbeat_file.read_text())
    except Exception:
        return ProcessorReadiness(
            ready=False,
            last_heartbeat=None,
            age_seconds=None,
            max_age_seconds=max_age_seconds,
        )

    updated_at = raw.get("updated_at")
    if not isinstance(updated_at, str):
        return ProcessorReadiness(
            ready=False,
            last_heartbeat=None,
            age_seconds=None,
            max_age_seconds=max_age_seconds,
        )

    updated_at_dt = _parse_iso_datetime(updated_at)
    if updated_at_dt is None:
        return ProcessorReadiness(
            ready=False,
            last_heartbeat=None,
            age_seconds=None,
            max_age_seconds=max_age_seconds,
        )

    age_seconds = (now - updated_at_dt).total_seconds()
    ready = age_seconds <= max_age_seconds

    return ProcessorReadiness(
        ready=ready,
        last_heartbeat=updated_at,
        age_seconds=age_seconds,
        max_age_seconds=max_age_seconds,
    )

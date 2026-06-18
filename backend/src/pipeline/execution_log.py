"""
Structured execution log for pipeline runs — v3.1.1.

Appends JSONL events to run_dir/execution_log.jsonl. Used by pipeline stages and
executor to give operators a clear, step-by-step trace. No raw prompts or large payloads.
Payloads are sanitized so serialization never fails (best-effort, resilient).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, cast

from src.pipeline.execution_log_sanitizer import (
    find_non_json_serializable_path,
    make_json_safe_for_execution_log,
)

logger = logging.getLogger(__name__)

EXECUTION_LOG_FILENAME = "execution_log.jsonl"
LAST_STAGE_ERROR_FILENAME = "last_stage_error.txt"

# Max length for generic string values in payloads to avoid huge log lines
_PAYLOAD_STRING_MAX = 512
_UNTRUNCATED_PAYLOAD_KEYS = frozenset({"prompt_text"})


def _truncate_payload_strings(value: Any, *, key: str | None = None) -> Any:
    """Apply execution_log string length limits after JSON-safe redaction."""
    if isinstance(value, str):
        if key in _UNTRUNCATED_PAYLOAD_KEYS:
            return value
        return value[:_PAYLOAD_STRING_MAX] if len(value) > _PAYLOAD_STRING_MAX else value
    if isinstance(value, dict):
        return {
            str(k): _truncate_payload_strings(v, key=str(k))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_truncate_payload_strings(item) for item in value]
    return value


def _sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a JSON-serializable copy of payload, or None if empty/invalid."""
    if not payload or not isinstance(payload, dict):
        return None
    try:
        safe = make_json_safe_for_execution_log(payload)
        if not isinstance(safe, dict):
            return None
        truncated = _truncate_payload_strings(safe)
        bad_path = find_non_json_serializable_path(truncated)
        if bad_path:
            logger.warning(
                "execution_log payload still not JSON-serializable at %s after sanitization",
                bad_path,
            )
        return cast(Optional[dict[str, Any]], truncated)
    except Exception as exc:
        bad_path = find_non_json_serializable_path(payload) or "<root>"
        logger.warning(
            "execution_log sanitization failed at %s: %s",
            bad_path,
            exc,
        )
        return None


@dataclass
class LogEvent:
    """Single execution log event (machine- and UI-friendly)."""

    ts: str  # ISO 8601
    stage: str
    level: str  # info | warning | error
    message: str
    payload: dict[str, Any] | None = None

    def to_json_line(self) -> str | None:
        """Return JSON line or None if serialization fails (caller should fall back)."""
        d: dict[str, Any] = {
            "ts": self.ts,
            "stage": self.stage,
            "level": self.level,
            "message": (
                self.message[: _PAYLOAD_STRING_MAX * 2]
                if len(self.message) > _PAYLOAD_STRING_MAX * 2
                else self.message
            ),
        }
        if self.payload:
            d["payload"] = self.payload
        try:
            return json.dumps(d, ensure_ascii=False) + "\n"
        except (TypeError, ValueError) as exc:
            bad_path = find_non_json_serializable_path(self.payload or {}) or "<payload>"
            logger.warning(
                "execution_log serialization failed at %s: %s",
                bad_path,
                exc,
            )
            d["payload"] = {
                "_serialization_error": "payload could not be serialized",
                "_failing_path": bad_path,
                "_value_type": type(exc).__name__,
            }
            try:
                return json.dumps(d, ensure_ascii=False) + "\n"
            except (TypeError, ValueError):
                return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionLogWriter:
    """Append-only writer for execution_log.jsonl in a run directory."""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = Path(run_dir)
        self._path = self._run_dir / EXECUTION_LOG_FILENAME
        self._last_error_path = self._run_dir / LAST_STAGE_ERROR_FILENAME

    def _ensure_dir(self) -> None:
        self._run_dir.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        stage: str,
        level: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append one event. level must be info, warning, or error. Payload is sanitized for JSON."""
        safe_payload = _sanitize_payload(payload)
        event = LogEvent(
            ts=_utc_now_iso(),
            stage=stage,
            level=level,
            message=message,
            payload=safe_payload,
        )
        try:
            self._ensure_dir()
            line = event.to_json_line()
            if line:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line)
            else:
                fallback = (
                    json.dumps(
                        {
                            "ts": event.ts,
                            "stage": event.stage,
                            "level": event.level,
                            "message": event.message[:500]
                            if len(event.message) > 500
                            else event.message,
                            "payload": {"_fallback": True},
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(fallback)
        except (OSError, TypeError, ValueError) as e:
            logger.warning("Failed to write execution log %s: %s", self._path, e)

    def info(self, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.append(stage, "info", message, payload)

    def warning(self, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.append(stage, "warning", message, payload)

    def error(self, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.append(stage, "error", message, payload)

    def structured_event(
        self,
        *,
        job_id: str,
        inventory_id: str | None,
        aisle_id: str | None,
        attempt: int,
        stage: str,
        substep: str | None,
        event: str,
        duration_ms: int | None = None,
        details: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        payload: dict[str, Any] = {
            "job_id": job_id,
            "inventory_id": inventory_id,
            "aisle_id": aisle_id,
            "attempt": attempt,
            "event": event,
        }
        if substep:
            payload["substep"] = substep
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if details:
            payload["details"] = details
        self.append(stage, level, event, payload)

    def write_last_stage_error(self, stage: str, error_message: str) -> None:
        """Write a short last-stage error file for executor to read and expose."""
        try:
            self._ensure_dir()
            line = f"{stage}: {error_message}"
            with open(self._last_error_path, "w", encoding="utf-8") as f:
                f.write(line[:2048])
        except OSError as e:
            logger.warning("Failed to write last_stage_error %s: %s", self._last_error_path, e)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def last_error_path(self) -> Path:
        return self._last_error_path


def _parse_execution_log_lines(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def read_execution_log_bytes(content: bytes) -> list[dict[str, Any]]:
    """Parse execution_log.jsonl from raw bytes (e.g. S3 GET body). Empty if invalid or empty.

    Prefer :func:`read_execution_log_file` when bytes already live on disk (large logs).
    """
    if not content:
        return []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return []
    return _parse_execution_log_lines(text)


def read_execution_log_file(path: Path) -> list[dict[str, Any]]:
    """Parse JSONL execution log from a file path; line-oriented read (no full-file string for the raw blob)."""
    path = Path(path)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return events


def validate_execution_log_jsonl_file(path: Path) -> None:
    """Raise ValueError when any line in execution_log.jsonl is not valid JSON."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"execution_log missing: {path}")
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"execution_log invalid JSON at line {line_no}: {exc.msg}"
            ) from exc


def read_execution_log(run_dir: Path) -> list[dict[str, Any]]:
    """Read execution_log.jsonl and return list of event dicts. Empty if missing or invalid."""
    path = Path(run_dir) / EXECUTION_LOG_FILENAME
    return read_execution_log_file(path)


def read_last_stage_error(run_dir: Path) -> str | None:
    """Read last_stage_error.txt if present. Returns None if missing or empty."""
    path = Path(run_dir) / LAST_STAGE_ERROR_FILENAME
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    except OSError:
        return None

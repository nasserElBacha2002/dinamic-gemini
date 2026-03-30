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
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

EXECUTION_LOG_FILENAME = "execution_log.jsonl"
LAST_STAGE_ERROR_FILENAME = "last_stage_error.txt"

# Max length for string values in payloads to avoid huge log lines
_PAYLOAD_STRING_MAX = 512


def _sanitize_payload_value(value: Any) -> Any:
    """Convert a value to a JSON-serializable form. Recurses into dict/list; stringifies others."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_PAYLOAD_STRING_MAX] if len(value) > _PAYLOAD_STRING_MAX else value
    if isinstance(value, (datetime, Path)):
        s = str(value)
        return s[:_PAYLOAD_STRING_MAX] if len(s) > _PAYLOAD_STRING_MAX else s
    if isinstance(value, BaseException):
        s = f"{type(value).__name__}: {value}"
        return s[:_PAYLOAD_STRING_MAX] if len(s) > _PAYLOAD_STRING_MAX else s
    if isinstance(value, dict):
        return {str(k)[:_PAYLOAD_STRING_MAX]: _sanitize_payload_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_payload_value(v) for v in value]
    try:
        s = str(value)
        return s[:_PAYLOAD_STRING_MAX] if len(s) > _PAYLOAD_STRING_MAX else s
    except Exception:
        return "<non-serializable>"


def _sanitize_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a JSON-serializable copy of payload, or None if empty/invalid."""
    if not payload or not isinstance(payload, dict):
        return None
    try:
        return _sanitize_payload_value(payload)  # type: ignore[return-value]
    except Exception:
        return None


@dataclass
class LogEvent:
    """Single execution log event (machine- and UI-friendly)."""
    ts: str  # ISO 8601
    stage: str
    level: str  # info | warning | error
    message: str
    payload: Optional[Dict[str, Any]] = None

    def to_json_line(self) -> Optional[str]:
        """Return JSON line or None if serialization fails (caller should fall back)."""
        d: Dict[str, Any] = {
            "ts": self.ts,
            "stage": self.stage,
            "level": self.level,
            "message": (self.message[:_PAYLOAD_STRING_MAX * 2] if len(self.message) > _PAYLOAD_STRING_MAX * 2 else self.message),
        }
        if self.payload:
            d["payload"] = self.payload
        try:
            return json.dumps(d, ensure_ascii=False) + "\n"
        except (TypeError, ValueError):
            d["payload"] = {"_serialization_error": "payload could not be serialized"}
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
        payload: Optional[Dict[str, Any]] = None,
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
                fallback = json.dumps({
                    "ts": event.ts,
                    "stage": event.stage,
                    "level": event.level,
                    "message": event.message[:500] if len(event.message) > 500 else event.message,
                    "payload": {"_fallback": True},
                }, ensure_ascii=False) + "\n"
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(fallback)
        except (OSError, TypeError, ValueError) as e:
            logger.warning("Failed to write execution log %s: %s", self._path, e)

    def info(self, stage: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self.append(stage, "info", message, payload)

    def warning(self, stage: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self.append(stage, "warning", message, payload)

    def error(self, stage: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self.append(stage, "error", message, payload)

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


def _parse_execution_log_lines(text: str) -> list[Dict[str, Any]]:
    events: list[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def read_execution_log_bytes(content: bytes) -> list[Dict[str, Any]]:
    """Parse execution_log.jsonl from raw bytes (e.g. S3 GET body). Empty if invalid or empty."""
    if not content:
        return []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return []
    return _parse_execution_log_lines(text)


def read_execution_log(run_dir: Path) -> list[Dict[str, Any]]:
    """Read execution_log.jsonl and return list of event dicts. Empty if missing or invalid."""
    path = Path(run_dir) / EXECUTION_LOG_FILENAME
    events: list[Dict[str, Any]] = []
    if not path.is_file():
        return events
    try:
        with open(path, encoding="utf-8") as f:
            return _parse_execution_log_lines(f.read())
    except OSError:
        pass
    return events


def read_last_stage_error(run_dir: Path) -> Optional[str]:
    """Read last_stage_error.txt if present. Returns None if missing or empty."""
    path = Path(run_dir) / LAST_STAGE_ERROR_FILENAME
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text if text else None
    except OSError:
        return None

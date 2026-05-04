"""Path-safe validation for job_id, entity_uid, and relative paths to prevent path traversal.

Allowed format for ids: ^[a-zA-Z0-9_-]+$
Rejects: .., /, \\, and any other non-alphanumeric except underscore and hyphen.
"""

import re
from typing import Optional

# Same pattern for job_id and entity_uid (e.g. job_abc123_E1)
_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_job_id(job_id: Optional[str]) -> str:
    """Validate job_id for path safety. Returns the string if valid.

    Raises:
        ValueError: If job_id is None, empty, or contains disallowed characters
            (e.g. .., /, \\, or anything not in [a-zA-Z0-9_-]).
    """
    if job_id is None or not isinstance(job_id, str):
        raise ValueError("job_id must be a non-empty string")
    s = job_id.strip()
    if not s:
        raise ValueError("job_id must be non-empty")
    if ".." in s or "/" in s or "\\" in s:
        raise ValueError("job_id must not contain '..', '/', or '\\'")
    if not _SAFE_ID_PATTERN.fullmatch(s):
        raise ValueError("job_id must contain only letters, digits, underscore, and hyphen")
    return s


def validate_entity_uid(entity_uid: Optional[str]) -> str:
    """Validate entity_uid for path safety. Returns the string if valid.

    Raises:
        ValueError: If entity_uid is None, empty, or contains disallowed characters.
    """
    if entity_uid is None or not isinstance(entity_uid, str):
        raise ValueError("entity_uid must be a non-empty string")
    s = entity_uid.strip()
    if not s:
        raise ValueError("entity_uid must be non-empty")
    if ".." in s or "/" in s or "\\" in s:
        raise ValueError("entity_uid must not contain '..', '/', or '\\'")
    if not _SAFE_ID_PATTERN.fullmatch(s):
        raise ValueError("entity_uid must contain only letters, digits, underscore, and hyphen")
    return s


def validate_relative_path(value: str, name: str = "path") -> str:
    """Reject unsafe path components; return stripped value.

    Raises ValueError if value contains '..', is absolute (starts with /), or contains backslash.
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")
    s = value.strip()
    if ".." in s:
        raise ValueError(f"{name} must not contain '..'")
    if s.startswith("/") or "\\" in s:
        raise ValueError(f"{name} must be a relative path without backslashes")
    return s

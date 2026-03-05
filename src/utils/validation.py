"""Path-safe validation for job_id and entity_uid to prevent path traversal.

Allowed format: ^[a-zA-Z0-9_-]+$
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
        raise ValueError(
            "job_id must contain only letters, digits, underscore, and hyphen"
        )
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
        raise ValueError(
            "entity_uid must contain only letters, digits, underscore, and hyphen"
        )
    return s

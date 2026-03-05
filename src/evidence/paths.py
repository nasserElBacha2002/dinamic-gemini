"""Evidence path utilities: slug and entity evidence directory."""

import re
from pathlib import Path


def slug(value: str) -> str:
    """Convert pallet_id or entity_uid into a filesystem-safe string.

    - Replace non-alphanumeric with underscore.
    - Collapse multiple underscores.
    - Strip leading/trailing underscores.
    - Empty or invalid → "entity".
    """
    if not value or not isinstance(value, str):
        return "entity"
    s = re.sub(r"[^A-Za-z0-9_\-]", "_", value.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s if s else "entity"


def entity_evidence_path(run_dir: Path, entity_uid: str) -> Path:
    """Return run_dir/evidence/<entity_slug>/.

    Args:
        run_dir: e.g. output/job_xxx/run
        entity_uid: e.g. job_abc_E1

    Returns:
        Path to entity evidence subfolder.
    """
    return run_dir / "evidence" / slug(entity_uid)

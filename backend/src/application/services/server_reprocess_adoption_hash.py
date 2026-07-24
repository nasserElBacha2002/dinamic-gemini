"""Adoption content hash for idempotent payload replay."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence


def canonicalize_adoption_content(
    *,
    run_id: str,
    items: Sequence[Any],
) -> str:
    payload = {
        "run_id": (run_id or "").strip(),
        "items": [
            {
                "proposal_id": (getattr(item, "proposal_id", "") or "").strip(),
                "action": (getattr(item, "action", "") or "").strip().upper(),
                "edit_internal_code": getattr(item, "edit_internal_code", None) or None,
                "edit_quantity": getattr(item, "edit_quantity", None),
            }
            for item in sorted(
                items,
                key=lambda i: (
                    getattr(i, "proposal_id", "") or "",
                    getattr(i, "action", "") or "",
                ),
            )
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

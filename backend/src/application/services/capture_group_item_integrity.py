"""G7 — defensive checks for capture session items vs group/session scope."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.errors import CaptureSessionGroupIntegrityError
from src.domain.assets.entities import SourceAsset
from src.domain.capture.entities import CaptureSessionItem


def validate_group_items_coherent(
    items: Sequence[CaptureSessionItem],
    *,
    session_id: str,
    group_id: str,
) -> None:
    """Ensure every item belongs to ``session_id`` and ``group_id``."""
    sid = (session_id or "").strip()
    gid = (group_id or "").strip()
    for it in items:
        if (it.session_id or "").strip() != sid:
            raise CaptureSessionGroupIntegrityError(
                "Capture session group integrity: item session_id does not match the requested session."
            )
        if (it.group_id or "").strip() != gid:
            raise CaptureSessionGroupIntegrityError(
                "Capture session group integrity: item group_id does not match the requested group."
            )


def validate_assets_belong_to_aisle(assets: Sequence[SourceAsset], *, aisle_id: str) -> None:
    """Ensure each asset's ``aisle_id`` matches the group's aisle (defensive)."""
    aid = (aisle_id or "").strip()
    for a in assets:
        got = (a.aisle_id or "").strip()
        if got != aid:
            raise CaptureSessionGroupIntegrityError(
                "Capture session preview integrity: scoped asset aisle_id does not match the group's aisle."
            )

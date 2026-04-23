"""G6 — deterministic preview from aisle ``SourceAsset`` rows materialized for one temporal group."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import (
    CaptureSessionGroupNotFoundError,
    CaptureSessionGroupNotAssignedForPreviewError,
    CaptureSessionGroupNotMaterializedForPreviewError,
    CaptureSessionNotFoundError,
)
from src.application.ports.capture_repositories import (
    CaptureSessionGroupRepository,
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.repositories import JOB_ID_FILTER_UNSET, PositionRepository, SourceAssetRepository
from src.application.services.capture_assignment_preview import compute_item_preview_outcomes
from src.application.use_cases.capture_session_group_assignment_guard import (
    ensure_group_aisle_assignment_allowed,
)
from src.domain.assets.entities import SourceAsset
from src.domain.capture.entities import (
    CaptureSessionGroupAisleAssignmentStatus,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
)


def _capture_session_item_id_from_asset(asset: SourceAsset) -> str | None:
    cid = (asset.capture_session_item_id or "").strip()
    if cid:
        return cid
    meta = asset.metadata_json or {}
    raw = meta.get("capture_session_item_id")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _asset_scopes_to_capture_session_group(
    asset: SourceAsset,
    *,
    session_id: str,
    group_id: str,
    group_item_ids: set[str],
    item_by_id: dict[str, CaptureSessionItem],
) -> bool:
    meta = asset.metadata_json or {}
    mid = str(meta.get("capture_session_id", "")).strip()
    mgid = str(meta.get("capture_session_group_id", "")).strip()
    if mid == session_id and mgid == group_id:
        return True
    iid = _capture_session_item_id_from_asset(asset)
    if not iid or iid not in group_item_ids:
        return False
    it = item_by_id.get(iid)
    if it is None:
        return False
    return (it.group_id or "").strip() == group_id


def _classify_g6_preview_status(
    *,
    filtered_asset_count: int,
    resolved_row_count: int,
    distinct_preview_imported_item_count: int,
    has_any_unlinked_imported_in_group: bool,
    proposed_outcome_count: int,
    conflict_outcome_count: int,
    unassigned_outcome_count: int,
) -> str:
    """Return ``preview_status`` for G6 with explicit, auditable semantics.

    **empty** — No usable materialized input for the ordinal preview heuristic:
      - No imported items could be joined from scoped aisle assets into preview rows
        (includes: zero scoped assets that resolve to a row; scoped assets only join to
        non-imported items; metadata-scoped assets with no resolvable ``CaptureSessionItem``).

    **partial** — At least one usable imported item is previewed, but coverage or outcomes are mixed:
      - ``filtered_asset_count > resolved_row_count`` (orphan / unjoinable scoped assets),
      - Some imported group items still lack ``linked_source_asset_id`` while any scoped asset exists,
      - Any CONFLICT or UNASSIGNED outcome from ``compute_item_preview_outcomes``,
      - ``proposed_outcome_count < distinct_preview_imported_item_count``.

    **ready** — All previewable imported items tied to resolved rows received PROPOSED, with no gaps:
      - ``distinct_preview_imported_item_count > 0``,
      - No join gap, no materialization gap, no conflict/unassigned outcomes,
      - ``proposed_outcome_count == distinct_preview_imported_item_count``.
    """
    join_gap_count = filtered_asset_count - resolved_row_count
    materialization_incomplete = bool(filtered_asset_count) and has_any_unlinked_imported_in_group

    no_usable_preview_input = distinct_preview_imported_item_count == 0
    if no_usable_preview_input:
        return "empty"

    mixed_or_incomplete = (
        join_gap_count > 0
        or materialization_incomplete
        or conflict_outcome_count > 0
        or unassigned_outcome_count > 0
        or proposed_outcome_count < distinct_preview_imported_item_count
    )
    if mixed_or_incomplete:
        return "partial"
    return "ready"


@dataclass(frozen=True)
class MaterializedGroupPreviewItemResult:
    capture_session_item_id: str
    source_asset_id: str
    assignment_status: str
    assignment_reason: str
    adjusted_capture_time: object | None
    preview_target_position_id: str | None


@dataclass(frozen=True)
class MaterializedGroupPreviewSummaryResult:
    proposed_count: int
    conflict_count: int
    unassigned_count: int
    previewed_item_count: int


@dataclass(frozen=True)
class ComputeMaterializedCaptureSessionGroupPreviewResult:
    capture_session_id: str
    group_id: str
    aisle_id: str
    source_asset_count: int
    source_asset_ids: tuple[str, ...]
    preview_status: str
    items: tuple[MaterializedGroupPreviewItemResult, ...]
    summary: MaterializedGroupPreviewSummaryResult


class ComputeMaterializedCaptureSessionGroupPreviewUseCase:
    """Read-only G6 preview: post-assignment, post-materialization, group-scoped ``SourceAsset`` → ordinal pairing.

    Session gates match G4/G5 via :func:`ensure_group_aisle_assignment_allowed`. Preview does not mutate
    ``CaptureSessionItem`` or session rows and does not invoke aisle processing.
    """

    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        group_repo: CaptureSessionGroupRepository,
        item_repo: CaptureSessionItemRepository,
        position_repo: PositionRepository,
        asset_repo: SourceAssetRepository,
        preview_max_positions: int,
    ) -> None:
        self._session_repo = session_repo
        self._group_repo = group_repo
        self._item_repo = item_repo
        self._position_repo = position_repo
        self._asset_repo = asset_repo
        self._preview_max_positions = max(1, int(preview_max_positions))

    def execute(
        self,
        *,
        inventory_id: str,
        session_id: str,
        group_id: str,
    ) -> ComputeMaterializedCaptureSessionGroupPreviewResult:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory.")
        ensure_group_aisle_assignment_allowed(session, group_repo=self._group_repo, session_id=session_id)

        group = self._group_repo.get_by_id_and_session(group_id, session_id)
        if group is None:
            raise CaptureSessionGroupNotFoundError("Capture session group not found for this session.")

        if group.assignment_status == CaptureSessionGroupAisleAssignmentStatus.UNASSIGNED or not (
            (group.assigned_aisle_id or "").strip()
        ):
            raise CaptureSessionGroupNotAssignedForPreviewError("")

        aisle_id = (group.assigned_aisle_id or "").strip()

        group_items = list(self._item_repo.list_by_session_and_group_id(session_id, group_id))
        group_item_ids = {i.id for i in group_items}
        item_by_id = {i.id: i for i in group_items}
        imported_group = [i for i in group_items if i.import_status == CaptureSessionItemImportStatus.IMPORTED]
        any_unlinked_imported = any(not (i.linked_source_asset_id or "").strip() for i in imported_group)

        aisle_assets = list(self._asset_repo.list_by_aisle(aisle_id))
        filtered = [
            a
            for a in aisle_assets
            if _asset_scopes_to_capture_session_group(
                a,
                session_id=session_id,
                group_id=group_id,
                group_item_ids=group_item_ids,
                item_by_id=item_by_id,
            )
        ]
        filtered.sort(key=lambda x: (x.uploaded_at, x.id))

        if not filtered and any_unlinked_imported:
            raise CaptureSessionGroupNotMaterializedForPreviewError("")

        positions = list(
            self._position_repo.list_by_aisle(
                aisle_id,
                page=1,
                page_size=self._preview_max_positions,
                job_id=JOB_ID_FILTER_UNSET,
            )
        )

        rows: list[tuple[SourceAsset, CaptureSessionItem]] = []
        for asset in filtered:
            iid = _capture_session_item_id_from_asset(asset)
            item = item_by_id.get(iid) if iid else None
            if item is None and iid:
                item = self._item_repo.get_by_id(iid)
            if item is None or item.session_id != session_id or (item.group_id or "").strip() != group_id:
                continue
            rows.append((asset, item))

        preview_items: list[CaptureSessionItem] = []
        seen: set[str] = set()
        for _, item in rows:
            if item.import_status != CaptureSessionItemImportStatus.IMPORTED:
                continue
            if item.id in seen:
                continue
            seen.add(item.id)
            preview_items.append(item)

        outcomes = compute_item_preview_outcomes(
            items=preview_items,
            positions=positions,
            clock_offset_seconds=session.clock_offset_seconds,
        )

        item_results: list[MaterializedGroupPreviewItemResult] = []
        for asset, item in rows:
            if item.import_status != CaptureSessionItemImportStatus.IMPORTED:
                item_results.append(
                    MaterializedGroupPreviewItemResult(
                        capture_session_item_id=item.id,
                        source_asset_id=asset.id,
                        assignment_status=CaptureSessionItemAssignmentStatus.UNASSIGNED.value,
                        assignment_reason="preview:item_not_imported",
                        adjusted_capture_time=None,
                        preview_target_position_id=None,
                    )
                )
                continue
            row = outcomes.get(item.id)
            if row is None:
                item_results.append(
                    MaterializedGroupPreviewItemResult(
                        capture_session_item_id=item.id,
                        source_asset_id=asset.id,
                        assignment_status=CaptureSessionItemAssignmentStatus.UNASSIGNED.value,
                        assignment_reason="preview:missing_preview_row",
                        adjusted_capture_time=None,
                        preview_target_position_id=None,
                    )
                )
                continue
            item_results.append(
                MaterializedGroupPreviewItemResult(
                    capture_session_item_id=item.id,
                    source_asset_id=asset.id,
                    assignment_status=row.assignment_status.value,
                    assignment_reason=row.assignment_reason,
                    adjusted_capture_time=row.adjusted_capture_time,
                    preview_target_position_id=row.preview_target_position_id,
                )
            )

        proposed = conflict = unassigned = 0
        for it in preview_items:
            row = outcomes.get(it.id)
            if row is None:
                continue
            if row.assignment_status == CaptureSessionItemAssignmentStatus.PROPOSED:
                proposed += 1
            elif row.assignment_status == CaptureSessionItemAssignmentStatus.CONFLICT:
                conflict += 1
            else:
                unassigned += 1

        previewed_item_count = len(preview_items)
        summary = MaterializedGroupPreviewSummaryResult(
            proposed_count=proposed,
            conflict_count=conflict,
            unassigned_count=unassigned,
            previewed_item_count=previewed_item_count,
        )

        preview_status = _classify_g6_preview_status(
            filtered_asset_count=len(filtered),
            resolved_row_count=len(rows),
            distinct_preview_imported_item_count=len(preview_items),
            has_any_unlinked_imported_in_group=any(
                not (i.linked_source_asset_id or "").strip() for i in imported_group
            ),
            proposed_outcome_count=proposed,
            conflict_outcome_count=conflict,
            unassigned_outcome_count=unassigned,
        )

        return ComputeMaterializedCaptureSessionGroupPreviewResult(
            capture_session_id=session_id,
            group_id=group_id,
            aisle_id=aisle_id,
            source_asset_count=len(filtered),
            source_asset_ids=tuple(a.id for a in filtered),
            preview_status=preview_status,
            items=tuple(item_results),
            summary=summary,
        )

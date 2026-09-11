"""Preview, confirm, and report local CSV imports."""

from __future__ import annotations

import logging
import uuid

from src.application.ports.clock import Clock
from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.application.ports.local_csv_inventory_result_writer import LocalCsvInventoryResultWriter
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.ports.sql_cursor import SqlCursorLike
from src.application.services.import_canonical_position_materializer import (
    ImportCanonicalPositionMaterializer,
)
from src.application.services.local_csv_parser import (
    ParsedLocalCsv,
    ParsedLocalCsvRow,
    parse_local_csv,
)
from src.application.services.local_csv_position_materializer import LocalCsvPositionMaterializer
from src.application.services.supplier_local_csv_row_revalidator import (
    SupplierCsvAuthoritativeFields,
    SupplierLocalCsvRowRevalidator,
)
from src.domain.inventory.write_policy import (
    InventoryNotWritableError,
    require_inventory_writable,
)
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    local_csv_row_secondary_key,
)
from src.domain.local_csv_import.errors import (
    CONFLICT_POLICIES,
    INVENTORY_CLOSED,
    INVENTORY_NOT_WRITABLE,
    LATE_SYNC_REJECTED,
    LOCAL_CSV_EXPORT_CONFLICT,
    LOCAL_CSV_IMPORT_NOT_FOUND,
    LOCAL_CSV_INVENTORY_MISMATCH,
    LOCAL_CSV_MATERIALIZATION_FAILED,
    LocalCsvImportDisabledError,
    LocalCsvImportError,
)
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.domain.local_csv_import.statuses import (
    LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    LOCAL_CSV_IMPORT_STATUS_PREVIEWED,
)

# Re-export for routes/tests that import from the use-case module.
__all__ = [
    "ConfirmLocalCsvImport",
    "GetLocalCsvImport",
    "LOCAL_CSV_EXPORT_CONFLICT",
    "LOCAL_CSV_IMPORT_DISABLED",
    "LOCAL_CSV_IMPORT_NOT_FOUND",
    "LOCAL_CSV_INVENTORY_MISMATCH",
    "LOCAL_CSV_SECONDARY_CONFLICT",
    "LocalCsvImportDisabledError",
    "LocalCsvImportError",
    "PreviewLocalCsvImport",
]

from src.domain.local_csv_import.errors import (  # noqa: E402
    LOCAL_CSV_IMPORT_DISABLED,
    LOCAL_CSV_SECONDARY_CONFLICT,
)

logger = logging.getLogger(__name__)


def _map_inventory_write_error(exc: InventoryNotWritableError) -> LocalCsvImportError:
    code = exc.code
    if code not in {INVENTORY_NOT_WRITABLE, INVENTORY_CLOSED, LATE_SYNC_REJECTED}:
        code = INVENTORY_NOT_WRITABLE
    return LocalCsvImportError(code, exc.detail)


class PreviewLocalCsvImport:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        import_repo: LocalCsvImportRepository,
        clock: Clock,
        enabled: bool,
        supplier_revalidator: SupplierLocalCsvRowRevalidator | None = None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._import_repo = import_repo
        self._clock = clock
        self._enabled = enabled
        self._supplier_revalidator = supplier_revalidator

    def execute(self, *, inventory_id: str, content: bytes) -> LocalCsvImport:
        if not self._enabled:
            raise LocalCsvImportDisabledError()
        self._require_writable(inventory_id)

        parsed = parse_local_csv(content)
        if parsed.inventory_id != inventory_id:
            raise LocalCsvImportError(
                LOCAL_CSV_INVENTORY_MISMATCH,
                "CSV inventory_id does not match the path inventory_id",
            )
        return self._preview_parsed(inventory_id=inventory_id, parsed=parsed)

    def execute_from_parsed(
        self,
        *,
        inventory_id: str,
        parsed: ParsedLocalCsv,
        pending_aisle_ids: frozenset[str] | None = None,
    ) -> LocalCsvImport:
        """Stage a preview from an already-built ParsedLocalCsv (e.g. scanner TXT converter)."""
        return self._preview_parsed(
            inventory_id=inventory_id,
            parsed=parsed,
            pending_aisle_ids=pending_aisle_ids,
        )

    def _require_writable(self, inventory_id: str) -> None:
        try:
            require_inventory_writable(
                self._inventory_repo.get_by_id(inventory_id),
                inventory_id=inventory_id,
            )
        except InventoryNotWritableError as exc:
            raise _map_inventory_write_error(exc) from exc

    def _preview_parsed(
        self,
        *,
        inventory_id: str,
        parsed: ParsedLocalCsv,
        pending_aisle_ids: frozenset[str] | None = None,
    ) -> LocalCsvImport:
        if not self._enabled:
            raise LocalCsvImportDisabledError()
        self._require_writable(inventory_id)
        if parsed.inventory_id != inventory_id:
            raise LocalCsvImportError(
                LOCAL_CSV_INVENTORY_MISMATCH,
                "Parsed import inventory_id does not match the path inventory_id",
            )
        existing = self._import_repo.get_by_export_id(
            inventory_id=inventory_id, export_id=parsed.export_id
        )
        if existing is not None:
            if existing.content_hash != parsed.content_hash:
                raise LocalCsvImportError(
                    LOCAL_CSV_EXPORT_CONFLICT,
                    "export_id already exists with different import content",
                )
            if (
                existing.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED
                or existing.rejected_rows == 0
            ):
                return existing
            return self._build_and_persist_preview(
                inventory_id=inventory_id,
                parsed=parsed,
                existing=existing,
                pending_aisle_ids=pending_aisle_ids,
            )
        return self._build_and_persist_preview(
            inventory_id=inventory_id,
            parsed=parsed,
            existing=None,
            pending_aisle_ids=pending_aisle_ids,
        )

    def _build_and_persist_preview(
        self,
        *,
        inventory_id: str,
        parsed: ParsedLocalCsv,
        existing: LocalCsvImport | None,
        pending_aisle_ids: frozenset[str] | None = None,
    ) -> LocalCsvImport:
        aisle_ids = {a.id for a in self._aisle_repo.list_by_inventory(inventory_id)}
        import_id = existing.id if existing is not None else str(uuid.uuid4())
        prior_by_number = (
            {row.row_number: row for row in existing.rows} if existing is not None else {}
        )
        seen_keys: set[tuple[str, str]] = set()
        rows: list[LocalCsvImportRow] = []
        for parsed_row in parsed.rows:
            errors = list(parsed_row.errors)
            authoritative: SupplierCsvAuthoritativeFields | None = None
            if parsed_row.supplier_import is not None:
                if self._supplier_revalidator is None:
                    errors.append("supplier_import:revalidation_unavailable")
                else:
                    outcome = self._supplier_revalidator.revalidate(
                        inventory_id=inventory_id,
                        parsed_row=parsed_row,
                    )
                    if outcome.errors:
                        errors.extend(outcome.errors)
                    else:
                        authoritative = outcome.authoritative
            values = parsed_row.values
            for field, expected in (
                ("export_id", parsed.export_id),
                ("schema_version", parsed.schema_version),
                ("inventory_id", inventory_id),
                ("device_id", parsed.device_id),
            ):
                if values[field] != expected:
                    errors.append(f"{field}:inconsistent")
            if parsed_row.exported_at != parsed.exported_at:
                errors.append("exported_at:inconsistent")
            aisle_id = values["aisle_id"]
            if aisle_id not in aisle_ids:
                allowed_pending = pending_aisle_ids or frozenset()
                if aisle_id not in allowed_pending:
                    errors.append("aisle_id:not_in_inventory")
            secondary_key = local_csv_row_secondary_key(
                capture_session_id=values["capture_session_id"],
                capture_photo_id=values["capture_photo_id"],
                label_id=(values.get("label_id") or "").strip() or None,
                detection_source=(
                    (parsed_row.detection_source or values.get("source") or "").strip() or None
                ),
            )
            if secondary_key in seen_keys:
                errors.append("secondary_key:duplicate_in_file")
            seen_keys.add(secondary_key)
            prior = prior_by_number.get(parsed_row.row_number)
            rows.append(
                self._to_row(
                    import_id,
                    parsed_row,
                    tuple(dict.fromkeys(errors)),
                    row_id=prior.id if prior is not None else None,
                    authoritative=authoritative,
                )
            )

        now = self._clock.now()
        rejected = sum(row.status == "REJECTED" for row in rows)
        record = LocalCsvImport(
            id=import_id,
            export_id=parsed.export_id,
            schema_version=parsed.schema_version,
            inventory_id=inventory_id,
            device_id=parsed.device_id,
            exported_at=parsed.exported_at,
            status=LOCAL_CSV_IMPORT_STATUS_PREVIEWED,
            content_hash=parsed.content_hash,
            total_rows=len(rows),
            valid_rows=len(rows) - rejected,
            rejected_rows=rejected,
            duplicate_rows=0,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
            rows=tuple(rows),
        )
        if existing is not None:
            return self._import_repo.save(record)
        return self._import_repo.stage_or_get_existing(record)

    @staticmethod
    def _to_row(
        import_id: str,
        parsed: ParsedLocalCsvRow,
        errors: tuple[str, ...],
        *,
        row_id: str | None = None,
        authoritative: SupplierCsvAuthoritativeFields | None = None,
    ) -> LocalCsvImportRow:
        values = parsed.values
        requires_review = bool(parsed.requires_review)
        if not values["position_code"]:
            requires_review = True
        raw_label = (values.get("label_id") or "").strip()
        label_id = raw_label.upper() if raw_label else None
        position_label_id = (values.get("position_label_id") or "").strip() or None
        position_payload_raw = (values.get("position_payload_raw") or "").strip() or None
        position_code = values["position_code"]
        internal_code = values["internal_code"] or None
        quantity = parsed.quantity
        if authoritative is not None:
            if authoritative.label_id is not None:
                label_id = authoritative.label_id
            if authoritative.internal_code is not None:
                internal_code = authoritative.internal_code
            if authoritative.quantity is not None:
                quantity = authoritative.quantity
            if authoritative.position_code is not None:
                position_code = authoritative.position_code
            if authoritative.position_label_id is not None:
                position_label_id = authoritative.position_label_id
            if authoritative.position_payload_raw is not None:
                position_payload_raw = authoritative.position_payload_raw
        return LocalCsvImportRow(
            id=row_id or str(uuid.uuid4()),
            import_id=import_id,
            row_number=parsed.row_number,
            inventory_id=values["inventory_id"],
            aisle_id=values["aisle_id"],
            capture_session_id=values["capture_session_id"],
            capture_photo_id=values["capture_photo_id"],
            client_file_id=values["client_file_id"],
            capture_order=parsed.capture_order,
            captured_at=parsed.captured_at,
            position_code=position_code,
            internal_code=internal_code,
            quantity=quantity,
            quantity_status=values["quantity_status"],
            detection_status=values["detection_status"],
            detection_source=parsed.detection_source,
            ingestion_source=parsed.ingestion_source or INGESTION_SOURCE_LOCAL_CSV_IMPORT,
            requires_review=requires_review,
            error_code=values["error_code"] or None,
            notes=values["notes"] or None,
            status="REJECTED" if errors else "PREVIEW_VALID",
            validation_errors=errors,
            validation_warnings=parsed.warnings,
            label_id=label_id,
            position_label_id=position_label_id,
            position_payload_raw=position_payload_raw,
        )


class ConfirmLocalCsvImport:
    def __init__(
        self,
        *,
        import_repo: LocalCsvImportRepository,
        result_writer: LocalCsvInventoryResultWriter,
        clock: Clock,
        enabled: bool,
        inventory_repo: InventoryRepository,
        position_materializer: LocalCsvPositionMaterializer | None = None,
        aisle_repo: AisleRepository | None = None,
        status_reconciler: object | None = None,
        canonical_position_materializer: ImportCanonicalPositionMaterializer | None = None,
        materialization_lease_sec: int = 120,
        materialization_max_attempts: int = 5,
        owner: str | None = None,
    ) -> None:
        self._import_repo = import_repo
        self._result_writer = result_writer
        self._clock = clock
        self._enabled = enabled
        self._position_materializer = position_materializer
        self._aisle_repo = aisle_repo
        self._status_reconciler = status_reconciler
        self._inventory_repo = inventory_repo
        self._canonical_position_materializer = canonical_position_materializer
        self._materialization_lease_sec = materialization_lease_sec
        self._materialization_max_attempts = materialization_max_attempts
        self._owner = (owner or "").strip() or None

    def execute(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str = "SKIP",
        confirmed_by_user_id: str | None = None,
        owner: str | None = None,
    ) -> tuple[LocalCsvImport, bool]:
        from src.application.services.import_canonical_materialization_policy import (
            raise_for_canonical_failures,
        )
        from src.domain.local_csv_import.error_codes import (
            LOCAL_CSV_CANONICAL_MATERIALIZATION_REJECTED,
            LOCAL_CSV_MATERIALIZATION_EXHAUSTED,
            LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
            LOCAL_CSV_REQUIRES_REVIEW,
            is_retryable_error_code,
            normalize_stable_error_code,
        )
        from src.observability.metrics.instruments import record_local_csv_import_event

        if not self._enabled:
            raise LocalCsvImportDisabledError()
        policy = (conflict_policy or "SKIP").strip().upper()
        if policy not in CONFLICT_POLICIES:
            raise LocalCsvImportError(
                "LOCAL_CSV_CONFLICT_POLICY_INVALID",
                f"conflict_policy must be one of: {', '.join(sorted(CONFLICT_POLICIES))}",
            )
        inventory = self._require_writable(inventory_id)
        claim_owner = (
            (owner or "").strip()
            or self._owner
            or (confirmed_by_user_id or "").strip()
            or "system-import"
        )
        try:
            claimed, duplicate = self._import_repo.claim_import_for_materialization(
                inventory_id=inventory_id,
                export_id=export_id.strip(),
                conflict_policy=policy,
                confirmed_by_user_id=confirmed_by_user_id,
                apply_productive=self._apply_productive,
                clock_now=self._clock.now,
                owner=claim_owner,
                lease_sec=self._materialization_lease_sec,
            )
        except LocalCsvImportError:
            raise
        if duplicate and claimed.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
            return claimed, True

        fencing = int(claimed.fencing_version)
        self._require_writable(inventory_id)

        try:
            results = self._result_writer.list_for_import(claimed.id)
            if self._position_materializer is not None and results:
                self._position_materializer.materialize(results, now=self._clock.now())
            if self._canonical_position_materializer is not None and results:
                client_id = (inventory.client_id or "").strip()
                if not client_id:
                    raise LocalCsvImportError(
                        LOCAL_CSV_MATERIALIZATION_FAILED,
                        "Inventory client_id is required for import position materialization",
                    )
                summary = self._canonical_position_materializer.materialize_from_results(
                    results,
                    client_id=client_id,
                    actor_id=confirmed_by_user_id,
                )
                raise_for_canonical_failures(summary)
            if results:
                self._mark_aisles_processed(inventory_id, results)
            confirmed = self._import_repo.finalize_import_confirmation(
                import_id=claimed.id,
                clock_now=self._clock.now,
                confirmed_by_user_id=confirmed_by_user_id,
                owner=claim_owner,
                expected_fencing_version=fencing,
            )
            record_local_csv_import_event(event="confirmed")
            return confirmed, False
        except LocalCsvImportError as exc:
            code = normalize_stable_error_code(
                exc.code, fallback=LOCAL_CSV_MATERIALIZATION_FAILED
            )
            if code in {
                INVENTORY_CLOSED,
                INVENTORY_NOT_WRITABLE,
                LATE_SYNC_REJECTED,
                LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
            }:
                # Do not rewrite inventory / lease conflicts as generic materialization failed.
                if code == LOCAL_CSV_MATERIALIZATION_IN_PROGRESS:
                    raise LocalCsvImportError(code, str(exc)) from exc
                self._import_repo.mark_materialization_failed(
                    import_id=claimed.id,
                    error_code=code,
                    clock_now=self._clock.now,
                    requires_review=False,
                    owner=claim_owner,
                    expected_fencing_version=fencing,
                )
                raise LocalCsvImportError(code, str(exc)) from exc

            requires_review = code in {
                LOCAL_CSV_CANONICAL_MATERIALIZATION_REJECTED,
                LOCAL_CSV_REQUIRES_REVIEW,
                LOCAL_CSV_MATERIALIZATION_EXHAUSTED,
            } or (
                int(claimed.materialization_attempts) >= self._materialization_max_attempts
                and not is_retryable_error_code(code)
            )
            if (
                int(claimed.materialization_attempts) >= self._materialization_max_attempts
                and is_retryable_error_code(code)
            ):
                requires_review = True
                code = LOCAL_CSV_MATERIALIZATION_EXHAUSTED

            self._import_repo.mark_materialization_failed(
                import_id=claimed.id,
                error_code=code,
                clock_now=self._clock.now,
                requires_review=requires_review,
                owner=claim_owner,
                expected_fencing_version=fencing,
            )
            if requires_review:
                raise LocalCsvImportError(
                    LOCAL_CSV_REQUIRES_REVIEW
                    if code != LOCAL_CSV_MATERIALIZATION_EXHAUSTED
                    else code,
                    str(exc),
                ) from exc
            raise LocalCsvImportError(code, str(exc)) from exc
        except InventoryNotWritableError as exc:
            mapped = _map_inventory_write_error(exc)
            self._import_repo.mark_materialization_failed(
                import_id=claimed.id,
                error_code=mapped.code,
                clock_now=self._clock.now,
                owner=claim_owner,
                expected_fencing_version=fencing,
            )
            raise mapped from exc
        except Exception as exc:
            logger.exception(
                "local_csv_import_materialization_failed import_id=%s inventory_id=%s",
                claimed.id,
                inventory_id,
            )
            self._import_repo.mark_materialization_failed(
                import_id=claimed.id,
                error_code=LOCAL_CSV_MATERIALIZATION_FAILED,
                clock_now=self._clock.now,
                owner=claim_owner,
                expected_fencing_version=fencing,
            )
            raise LocalCsvImportError(
                LOCAL_CSV_MATERIALIZATION_FAILED,
                "Import materialization failed due to an unexpected error",
            ) from exc

    def _require_writable(self, inventory_id: str):
        try:
            return require_inventory_writable(
                self._inventory_repo.get_by_id(inventory_id),
                inventory_id=inventory_id,
            )
        except InventoryNotWritableError as exc:
            raise _map_inventory_write_error(exc) from exc

    def _mark_aisles_processed(
        self,
        inventory_id: str,
        results: tuple,
    ) -> None:
        if self._aisle_repo is None:
            return
        now = self._clock.now()
        for aisle_id in {r.aisle_id for r in results}:
            aisle = self._aisle_repo.get_by_id(aisle_id)
            if aisle is None:
                continue
            aisle.mark_processed(now)
            self._aisle_repo.save(aisle)
        if self._status_reconciler is not None:
            self._status_reconciler.reconcile(inventory_id)  # type: ignore[attr-defined]

    def _apply_productive(
        self,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        *,
        cursor: SqlCursorLike | None = None,
    ):
        return self._result_writer.apply_import(
            record=record,
            rows_to_import=rows_to_import,
            confirmed_by_user_id=confirmed_by_user_id,
            cursor=cursor,
        )


class GetLocalCsvImport:
    def __init__(self, *, import_repo: LocalCsvImportRepository, enabled: bool) -> None:
        self._import_repo = import_repo
        self._enabled = enabled

    def execute(self, *, inventory_id: str, import_id: str) -> LocalCsvImport:
        if not self._enabled:
            raise LocalCsvImportDisabledError()
        record = self._import_repo.get_by_id(import_id)
        if record is None or record.inventory_id != inventory_id:
            raise LocalCsvImportError(LOCAL_CSV_IMPORT_NOT_FOUND, "CSV import not found")
        return record

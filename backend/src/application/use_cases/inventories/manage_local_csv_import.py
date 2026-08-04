"""Preview, confirm, and report local CSV imports."""

from __future__ import annotations

import uuid
from dataclasses import replace

from src.application.ports.clock import Clock
from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.local_csv_parser import ParsedLocalCsvRow, parse_local_csv
from src.domain.local_csv_import.entities import (
    LOCAL_CSV_IMPORT_SOURCE,
    LocalCsvImport,
    LocalCsvImportRow,
)

LOCAL_CSV_IMPORT_DISABLED = "LOCAL_CSV_IMPORT_DISABLED"
LOCAL_CSV_IMPORT_NOT_FOUND = "LOCAL_CSV_IMPORT_NOT_FOUND"
LOCAL_CSV_EXPORT_NOT_PREVIEWED = "LOCAL_CSV_EXPORT_NOT_PREVIEWED"
LOCAL_CSV_EXPORT_CONFLICT = "LOCAL_CSV_EXPORT_CONFLICT"
LOCAL_CSV_INVENTORY_MISMATCH = "LOCAL_CSV_INVENTORY_MISMATCH"
LOCAL_CSV_SECONDARY_CONFLICT = "LOCAL_CSV_SECONDARY_CONFLICT"
CONFLICT_POLICIES = frozenset({"SKIP", "REJECT"})


class LocalCsvImportError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


class LocalCsvImportDisabledError(LocalCsvImportError):
    def __init__(self) -> None:
        super().__init__(LOCAL_CSV_IMPORT_DISABLED, "Local CSV import is not enabled")


class PreviewLocalCsvImport:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        import_repo: LocalCsvImportRepository,
        clock: Clock,
        enabled: bool,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._import_repo = import_repo
        self._clock = clock
        self._enabled = enabled

    def execute(self, *, inventory_id: str, content: bytes) -> LocalCsvImport:
        if not self._enabled:
            raise LocalCsvImportDisabledError()
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise LocalCsvImportError("INVENTORY_NOT_FOUND", f"Inventory {inventory_id} not found")

        parsed = parse_local_csv(content)
        if parsed.inventory_id != inventory_id:
            raise LocalCsvImportError(
                LOCAL_CSV_INVENTORY_MISMATCH,
                "CSV inventory_id does not match the path inventory_id",
            )
        existing = self._import_repo.get_by_export_id(
            inventory_id=inventory_id, export_id=parsed.export_id
        )
        if existing is not None:
            if existing.content_hash != parsed.content_hash:
                raise LocalCsvImportError(
                    LOCAL_CSV_EXPORT_CONFLICT,
                    "export_id already exists with different CSV content",
                )
            return existing

        aisle_ids = {a.id for a in self._aisle_repo.list_by_inventory(inventory_id)}
        import_id = str(uuid.uuid4())
        seen_keys: set[tuple[str, str]] = set()
        rows: list[LocalCsvImportRow] = []
        for parsed_row in parsed.rows:
            errors = list(parsed_row.errors)
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
            if values["aisle_id"] not in aisle_ids:
                errors.append("aisle_id:not_in_inventory")
            secondary_key = (values["capture_session_id"], values["capture_photo_id"])
            if secondary_key in seen_keys:
                errors.append("secondary_key:duplicate_in_file")
            seen_keys.add(secondary_key)
            rows.append(self._to_row(import_id, parsed_row, tuple(dict.fromkeys(errors))))

        now = self._clock.now()
        rejected = sum(row.status == "REJECTED" for row in rows)
        record = LocalCsvImport(
            id=import_id,
            export_id=parsed.export_id,
            schema_version=parsed.schema_version,
            inventory_id=inventory_id,
            device_id=parsed.device_id,
            exported_at=parsed.exported_at,
            status="PREVIEWED",
            content_hash=parsed.content_hash,
            total_rows=len(rows),
            valid_rows=len(rows) - rejected,
            rejected_rows=rejected,
            duplicate_rows=0,
            created_at=now,
            updated_at=now,
            rows=tuple(rows),
        )
        return self._import_repo.save(record)

    @staticmethod
    def _to_row(
        import_id: str, parsed: ParsedLocalCsvRow, errors: tuple[str, ...]
    ) -> LocalCsvImportRow:
        values = parsed.values
        return LocalCsvImportRow(
            id=str(uuid.uuid4()),
            import_id=import_id,
            row_number=parsed.row_number,
            inventory_id=values["inventory_id"],
            aisle_id=values["aisle_id"],
            capture_session_id=values["capture_session_id"],
            capture_photo_id=values["capture_photo_id"],
            client_file_id=values["client_file_id"],
            capture_order=parsed.capture_order,
            captured_at=parsed.captured_at,
            position_code=values["position_code"],
            internal_code=values["internal_code"] or None,
            quantity=parsed.quantity,
            quantity_status=values["quantity_status"],
            detection_status=values["detection_status"],
            source=LOCAL_CSV_IMPORT_SOURCE,
            requires_review=bool(parsed.requires_review),
            error_code=values["error_code"] or None,
            notes=values["notes"] or None,
            status="REJECTED" if errors else "PREVIEW_VALID",
            validation_errors=errors,
            validation_warnings=parsed.warnings,
        )


class ConfirmLocalCsvImport:
    def __init__(
        self,
        *,
        import_repo: LocalCsvImportRepository,
        clock: Clock,
        enabled: bool,
    ) -> None:
        self._import_repo = import_repo
        self._clock = clock
        self._enabled = enabled

    def execute(
        self, *, inventory_id: str, export_id: str, conflict_policy: str = "SKIP"
    ) -> tuple[LocalCsvImport, bool]:
        if not self._enabled:
            raise LocalCsvImportDisabledError()
        policy = (conflict_policy or "SKIP").strip().upper()
        if policy not in CONFLICT_POLICIES:
            raise LocalCsvImportError(
                "LOCAL_CSV_CONFLICT_POLICY_INVALID",
                f"conflict_policy must be one of: {', '.join(sorted(CONFLICT_POLICIES))}",
            )
        record = self._import_repo.get_by_export_id(
            inventory_id=inventory_id, export_id=export_id.strip()
        )
        if record is None:
            raise LocalCsvImportError(
                LOCAL_CSV_EXPORT_NOT_PREVIEWED, "export_id has not been previewed"
            )
        if record.status == "CONFIRMED":
            return record, True

        eligible = {row.secondary_key for row in record.rows if row.status == "PREVIEW_VALID"}
        conflicts = self._import_repo.find_confirmed_secondary_keys(eligible)
        if conflicts and policy == "REJECT":
            raise LocalCsvImportError(
                LOCAL_CSV_SECONDARY_CONFLICT,
                "One or more capture_session_id + capture_photo_id keys already exist",
            )

        rows = tuple(
            replace(
                row,
                status=(
                    "DUPLICATE"
                    if row.status == "PREVIEW_VALID" and row.secondary_key in conflicts
                    else "IMPORTED"
                    if row.status == "PREVIEW_VALID"
                    else row.status
                ),
            )
            for row in record.rows
        )
        now = self._clock.now()
        confirmed = replace(
            record,
            status="CONFIRMED",
            valid_rows=sum(row.status == "IMPORTED" for row in rows),
            duplicate_rows=sum(row.status == "DUPLICATE" for row in rows),
            rejected_rows=sum(row.status == "REJECTED" for row in rows),
            conflict_policy=policy,
            confirmed_at=now,
            updated_at=now,
            rows=rows,
        )
        return self._import_repo.save(confirmed), False


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

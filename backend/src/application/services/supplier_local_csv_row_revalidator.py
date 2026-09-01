"""Authoritative supplier revalidation for legacy local CSV import rows."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    InventoryRepository,
)
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.services.exact_extraction_profile_version import (
    ExactExtractionProfileVersionService,
    HistoricalProfileAttestation,
    ProfileVersionNotFoundError,
    ProfileVersionScopeMismatchError,
)
from src.application.services.label_validation import LabelValidationService
from src.application.services.local_csv_parser import ParsedLocalCsvRow
from src.application.services.local_csv_supplier_import_metadata import SupplierImportMetadata
from src.domain.client_supplier.extraction_profile import SupplierExtractionProfile
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationStatus,
    NormalizedItemLabel,
    NormalizedPositionLabel,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext

logger = logging.getLogger(__name__)

_PROFILE_CACHE_KEY = tuple[str, str, str, int, str]  # inv, supplier, profile_id, version, kind


@dataclass(frozen=True)
class SupplierCsvAuthoritativeFields:
    label_id: str | None = None
    internal_code: str | None = None
    quantity: int | None = None
    position_code: str | None = None
    position_label_id: str | None = None
    position_payload_raw: str | None = None


@dataclass(frozen=True)
class SupplierCsvRevalidationOutcome:
    errors: tuple[str, ...]
    authoritative: SupplierCsvAuthoritativeFields | None = None

    @property
    def accepted(self) -> bool:
        return not self.errors


class SupplierLocalCsvRowRevalidator:
    """Revalidate supplier CSV rows using pinned historical profiles (never ACTIVE fallback)."""

    def __init__(
        self,
        *,
        profile_service: ExactExtractionProfileVersionService,
        label_validation_service: LabelValidationService | None = None,
    ) -> None:
        self._profile_service = profile_service
        self._validation = label_validation_service or LabelValidationService()
        self._profile_cache: dict[_PROFILE_CACHE_KEY, SupplierExtractionProfile] = {}

    def revalidate(
        self,
        *,
        inventory_id: str,
        parsed_row: ParsedLocalCsvRow,
    ) -> SupplierCsvRevalidationOutcome:
        metadata = parsed_row.supplier_import
        if metadata is None:
            return SupplierCsvRevalidationOutcome(())

        aisle_id = (parsed_row.values.get("aisle_id") or "").strip()
        if not aisle_id:
            return SupplierCsvRevalidationOutcome(("supplier_import:missing_aisle_id",))

        try:
            profile = self._load_profile(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                metadata=metadata,
            )
        except ProfileVersionNotFoundError:
            logger.info(
                "local_csv.supplier_validation_failed inventory_id=%s client_supplier_id=%s "
                "label_kind=%s profile_id=%s profile_version=%s error_code=%s",
                inventory_id,
                metadata.client_supplier_id,
                metadata.label_kind.value,
                metadata.profile_id,
                metadata.profile_version,
                "SUPPLIER_PROFILE_VERSION_NOT_AVAILABLE",
            )
            return SupplierCsvRevalidationOutcome(
                ("SUPPLIER_PROFILE_VERSION_NOT_AVAILABLE",),
            )
        except ProfileVersionScopeMismatchError:
            logger.info(
                "local_csv.supplier_validation_failed inventory_id=%s client_supplier_id=%s "
                "label_kind=%s profile_id=%s profile_version=%s error_code=%s",
                inventory_id,
                metadata.client_supplier_id,
                metadata.label_kind.value,
                metadata.profile_id,
                metadata.profile_version,
                "supplier_profile:scope_mismatch",
            )
            return SupplierCsvRevalidationOutcome(("supplier_profile:scope_mismatch",))

        logger.info(
            "local_csv.supplier_profile_resolved inventory_id=%s client_supplier_id=%s "
            "label_kind=%s profile_id=%s profile_version=%s",
            inventory_id,
            metadata.client_supplier_id,
            metadata.label_kind.value,
            profile.id,
            profile.version,
        )

        context = self._validation_context(metadata=metadata, profile=profile)
        result = self._validation.validate(
            CandidateLabel(
                raw_payload=metadata.raw_payload,
                recognition_source=RecognitionSource.CSV,
                label_kind_hint=metadata.label_kind,
            ),
            context=context,
            label_kind=metadata.label_kind,
        )
        if result.status is not LabelValidationStatus.VALID or result.label is None:
            code = (result.error_code or "supplier_validation:failed").strip()
            logger.info(
                "local_csv.supplier_validation_failed inventory_id=%s client_supplier_id=%s "
                "label_kind=%s profile_id=%s profile_version=%s error_code=%s",
                inventory_id,
                metadata.client_supplier_id,
                metadata.label_kind.value,
                profile.id,
                profile.version,
                code,
            )
            return SupplierCsvRevalidationOutcome((code,))

        if metadata.label_kind is LabelKind.ITEM:
            outcome = self._finalize_item(parsed_row, metadata, result.label)
        else:
            outcome = self._finalize_position(parsed_row, metadata, result.label)

        if outcome.accepted:
            logger.info(
                "local_csv.supplier_validation_completed inventory_id=%s client_supplier_id=%s "
                "label_kind=%s profile_id=%s profile_version=%s",
                inventory_id,
                metadata.client_supplier_id,
                metadata.label_kind.value,
                profile.id,
                profile.version,
            )
        return outcome

    def _load_profile(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        metadata: SupplierImportMetadata,
    ) -> SupplierExtractionProfile:
        cache_key: _PROFILE_CACHE_KEY = (
            inventory_id,
            metadata.client_supplier_id,
            metadata.profile_id,
            int(metadata.profile_version),
            metadata.label_kind.value,
        )
        cached = self._profile_cache.get(cache_key)
        if cached is not None:
            return cached
        loaded = self._profile_service.load_for_aisle_capture(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            attestation=HistoricalProfileAttestation(
                profile_id=metadata.profile_id,
                profile_version=int(metadata.profile_version),
                client_supplier_id=metadata.client_supplier_id,
                label_kind=metadata.label_kind,
            ),
        )
        self._profile_cache[cache_key] = loaded
        return loaded

    @staticmethod
    def _validation_context(
        *,
        metadata: SupplierImportMetadata,
        profile: SupplierExtractionProfile,
    ) -> LabelValidationContext:
        config = profile.configuration
        resolved = ResolvedLabelProfiles(
            item=ResolvedLabelProfile(
                label_kind=LabelKind.ITEM,
                source=LabelProfileSource.SUPPLIER,
                client_supplier_id=metadata.client_supplier_id,
                resolution_source="LOCAL_CSV_IMPORT",
                extraction_profile_id=profile.id,
                extraction_profile_version=profile.version,
            ),
            position=ResolvedLabelProfile(
                label_kind=LabelKind.POSITION,
                source=LabelProfileSource.SUPPLIER,
                client_supplier_id=metadata.client_supplier_id,
                resolution_source="LOCAL_CSV_IMPORT",
                extraction_profile_id=profile.id,
                extraction_profile_version=profile.version,
            ),
        )
        return LabelValidationContext(
            resolved_profiles=resolved,
            item_extraction_configuration=(
                config if metadata.label_kind is LabelKind.ITEM else None
            ),
            position_extraction_configuration=(
                config if metadata.label_kind is LabelKind.POSITION else None
            ),
            client_id=profile.client_id,
        )

    def _finalize_item(
        self,
        parsed_row: ParsedLocalCsvRow,
        metadata: SupplierImportMetadata,
        label: object,
    ) -> SupplierCsvRevalidationOutcome:
        if not isinstance(label, NormalizedItemLabel):
            return SupplierCsvRevalidationOutcome(("supplier_validation:kind_mismatch",))
        values = parsed_row.values
        backend_label_id = (label.label_id or "").strip().upper() or None
        backend_sku = (label.sku or "").strip() or None
        backend_qty = label.quantity

        csv_label_id = (values.get("label_id") or "").strip().upper() or None
        csv_internal = (values.get("internal_code") or "").strip() or None
        csv_qty = parsed_row.quantity

        mismatches = self._semantic_mismatches_item(
            csv_label_id=csv_label_id,
            csv_internal=csv_internal,
            csv_qty=csv_qty,
            backend_label_id=backend_label_id,
            backend_sku=backend_sku,
            backend_qty=backend_qty,
        )
        if mismatches:
            for code in mismatches:
                logger.info(
                    "local_csv.supplier_semantic_mismatch inventory_id=%s client_supplier_id=%s "
                    "label_kind=%s profile_id=%s profile_version=%s error_code=%s",
                    values.get("inventory_id"),
                    metadata.client_supplier_id,
                    metadata.label_kind.value,
                    metadata.profile_id,
                    metadata.profile_version,
                    code,
                )
            return SupplierCsvRevalidationOutcome(tuple(mismatches))

        return SupplierCsvRevalidationOutcome(
            (),
            SupplierCsvAuthoritativeFields(
                label_id=backend_label_id,
                internal_code=backend_sku,
                quantity=backend_qty,
            ),
        )

    def _finalize_position(
        self,
        parsed_row: ParsedLocalCsvRow,
        metadata: SupplierImportMetadata,
        label: object,
    ) -> SupplierCsvRevalidationOutcome:
        if not isinstance(label, NormalizedPositionLabel):
            return SupplierCsvRevalidationOutcome(("supplier_validation:kind_mismatch",))
        values = parsed_row.values
        backend_position_id = (label.position_id or "").strip()
        backend_pallet = (label.pallet or "").strip()
        backend_side = (label.side or "").strip().upper()
        backend_level = (label.level or "").strip()

        csv_position_code = (values.get("position_code") or "").strip()
        csv_position_label_id = (values.get("position_label_id") or "").strip()
        csv_payload_raw = (values.get("position_payload_raw") or "").strip()

        mismatches: list[str] = []
        if csv_position_code and csv_position_code != backend_position_id:
            mismatches.append("supplier_semantic_mismatch:position_code")
        if csv_position_label_id and csv_position_label_id != backend_position_id:
            mismatches.append("supplier_semantic_mismatch:position_label_id")
        if csv_payload_raw and csv_payload_raw != metadata.raw_payload.strip():
            mismatches.append("supplier_semantic_mismatch:position_payload_raw")
        expected_raw = "|".join(
            part
            for part in (backend_position_id, backend_pallet, backend_side, backend_level)
            if part
        )
        if csv_payload_raw and expected_raw and csv_payload_raw != expected_raw:
            if "supplier_semantic_mismatch:position_payload_raw" not in mismatches:
                mismatches.append("supplier_semantic_mismatch:position_payload_raw")

        if mismatches:
            for code in mismatches:
                logger.info(
                    "local_csv.supplier_semantic_mismatch inventory_id=%s client_supplier_id=%s "
                    "label_kind=%s profile_id=%s profile_version=%s error_code=%s",
                    values.get("inventory_id"),
                    metadata.client_supplier_id,
                    metadata.label_kind.value,
                    metadata.profile_id,
                    metadata.profile_version,
                    code,
                )
            return SupplierCsvRevalidationOutcome(tuple(dict.fromkeys(mismatches)))

        return SupplierCsvRevalidationOutcome(
            (),
            SupplierCsvAuthoritativeFields(
                position_code=backend_position_id,
                position_label_id=backend_position_id,
                position_payload_raw=metadata.raw_payload.strip(),
            ),
        )

    @staticmethod
    def _semantic_mismatches_item(
        *,
        csv_label_id: str | None,
        csv_internal: str | None,
        csv_qty: int | None,
        backend_label_id: str | None,
        backend_sku: str | None,
        backend_qty: int | None,
    ) -> list[str]:
        errors: list[str] = []
        if csv_label_id is not None and backend_label_id is not None and csv_label_id != backend_label_id:
            errors.append("supplier_semantic_mismatch:label_id")
        if csv_internal is not None and backend_sku is not None and csv_internal != backend_sku:
            errors.append("supplier_semantic_mismatch:internal_code")
        if csv_qty is not None and backend_qty is not None and int(csv_qty) != int(backend_qty):
            errors.append("supplier_semantic_mismatch:quantity")
        return errors


def build_supplier_local_csv_row_revalidator(
    *,
    inventory_repo: InventoryRepository,
    aisle_repo: AisleRepository,
    client_supplier_repo: ClientSupplierRepository,
    extraction_profile_repo: SupplierExtractionProfileRepository,
    label_validation_service: LabelValidationService | None = None,
) -> SupplierLocalCsvRowRevalidator:
    return SupplierLocalCsvRowRevalidator(
        profile_service=ExactExtractionProfileVersionService(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            client_supplier_repo=client_supplier_repo,
            extraction_profile_repo=extraction_profile_repo,
        ),
        label_validation_service=label_validation_service,
    )

"""Neutral CSV import composition used by runtime recovery and API providers."""

from __future__ import annotations

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler


def _build_import_canonical_position_materializer(container):
    settings = container.settings
    if not bool(getattr(settings, "position_import_materialization_enabled", False)):
        return None
    if not bool(getattr(settings, "position_flexible_import_enabled", False)):
        return None
    if not bool(getattr(settings, "position_flexible_validation_enabled", False)):
        return None
    from src.application.services.import_canonical_position_materializer import (
        ImportCanonicalPositionMaterializer,
    )

    service = container.get_position_materialization_service()
    if service is None:
        return None
    return ImportCanonicalPositionMaterializer(
        materialize_service=service,
        enabled=True,
        aisle_repo=container.get_aisle_repo(),
    )


def build_confirm_local_csv_import(
    *,
    container,
    clock: Clock,
    inventory_repo: InventoryRepository,
    aisle_repo: AisleRepository,
    position_repo: PositionRepository,
    product_record_repo: ProductRecordRepository,
    status_reconciler: InventoryStatusReconciler,
    enabled: bool | None = None,
):
    from src.application.services.local_csv_position_materializer import (
        LocalCsvPositionMaterializer,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.services.product_labels.issued_product_label_resolver import (
        IssuedProductLabelResolver,
    )
    from src.application.use_cases.inventories.manage_local_csv_import import (
        ConfirmLocalCsvImport,
    )

    settings = container.settings
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )
    canonical_materializer = _build_import_canonical_position_materializer(container)
    return ConfirmLocalCsvImport(
        import_repo=container.get_local_csv_import_repo(),
        result_writer=container.get_local_csv_result_writer(),
        clock=clock,
        enabled=(
            bool(getattr(settings, "server_csv_import_enabled", False))
            if enabled is None
            else enabled
        ),
        position_materializer=LocalCsvPositionMaterializer(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            counted_product_label_repo=container.get_counted_product_label_repo(),
            issued_label_resolver=IssuedProductLabelResolver(
                issued_repo=container.get_issued_product_label_repo()
            ),
            inventory_repo=inventory_repo,
            client_position_label_repo=container.get_client_position_label_repo(),
            positioning_signing=signing if signing.can_sign else None,
        ),
        aisle_repo=aisle_repo,
        status_reconciler=status_reconciler,
        inventory_repo=inventory_repo,
        canonical_position_materializer=canonical_materializer,
        materialization_lease_sec=int(settings.local_csv_import_recovery_lease_sec),
        materialization_max_attempts=int(settings.local_csv_import_recovery_max_attempts),
    )

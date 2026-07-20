"""Phase 6 — resolve extraction profile for job processing (snapshot-aware)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.services.image_processing.extraction_profile_configuration import (
    parse_extraction_configuration,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    snapshot_dict_from_configuration,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    ExtractionProfileStatus,
    default_extraction_configuration,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedSupplierExtractionProfile:
    profile_id: str | None
    profile_key: str
    profile_version: int
    client_id: str | None
    supplier_id: str | None
    configuration: ExtractionProfileConfiguration
    visual_notes: str | None
    source: str  # SNAPSHOT | ACTIVE | DEFAULT
    snapshot: dict[str, Any]


class SupplierExtractionProfileResolver:
    def __init__(
        self,
        profile_repo: SupplierExtractionProfileRepository | None = None,
        *,
        profiles_enabled: bool = False,
    ) -> None:
        self._repo = profile_repo
        self._enabled = profiles_enabled

    def resolve_for_job(
        self,
        *,
        client_id: str | None,
        supplier_id: str | None,
        engine_params: dict[str, Any] | None = None,
    ) -> ResolvedSupplierExtractionProfile:
        """Prefer immutable job snapshot; else active profile; else system default."""
        params = engine_params if isinstance(engine_params, dict) else {}
        ident = params.get("identification_execution")
        if isinstance(ident, dict):
            snap = ident.get("supplier_extraction_profile")
            if isinstance(snap, dict) and snap.get("configuration"):
                try:
                    config = parse_extraction_configuration(snap.get("configuration"))
                    resolved = ResolvedSupplierExtractionProfile(
                        profile_id=str(snap["supplier_profile_id"])
                        if snap.get("supplier_profile_id")
                        else None,
                        profile_key=str(snap.get("supplier_profile_key") or "default"),
                        profile_version=int(snap.get("supplier_profile_version") or 1),
                        client_id=str(snap.get("client_id") or client_id or "") or None,
                        supplier_id=str(snap.get("supplier_id") or supplier_id or "") or None,
                        configuration=config,
                        visual_notes=None,
                        source="SNAPSHOT",
                        snapshot=snap,
                    )
                    logger.info(
                        "extraction_profile.resolved source=SNAPSHOT client_id=%s "
                        "supplier_id=%s profile_version=%s",
                        resolved.client_id,
                        resolved.supplier_id,
                        resolved.profile_version,
                    )
                    return resolved
                except Exception:
                    logger.warning(
                        "extraction_profile.snapshot_invalid falling_back",
                        exc_info=True,
                    )

        if (
            self._enabled
            and self._repo is not None
            and client_id
            and supplier_id
        ):
            active = self._repo.get_active(client_id, supplier_id)
            if active is not None and active.status is ExtractionProfileStatus.ACTIVE:
                snap = snapshot_dict_from_configuration(
                    profile_id=active.id,
                    profile_key=active.profile_key,
                    profile_version=active.version,
                    client_id=client_id,
                    supplier_id=supplier_id,
                    configuration=active.configuration,
                )
                logger.info(
                    "extraction_profile.resolved source=ACTIVE client_id=%s "
                    "supplier_id=%s profile_version=%s",
                    client_id,
                    supplier_id,
                    active.version,
                )
                return ResolvedSupplierExtractionProfile(
                    profile_id=active.id,
                    profile_key=active.profile_key,
                    profile_version=active.version,
                    client_id=client_id,
                    supplier_id=supplier_id,
                    configuration=active.configuration,
                    visual_notes=active.visual_notes,
                    source="ACTIVE",
                    snapshot=snap,
                )

        config = default_extraction_configuration()
        snap = snapshot_dict_from_configuration(
            profile_id=None,
            profile_key="system_default",
            profile_version=1,
            client_id=client_id,
            supplier_id=supplier_id,
            configuration=config,
        )
        logger.info(
            "extraction_profile.resolved source=DEFAULT client_id=%s supplier_id=%s",
            client_id,
            supplier_id,
        )
        return ResolvedSupplierExtractionProfile(
            profile_id=None,
            profile_key="system_default",
            profile_version=1,
            client_id=client_id,
            supplier_id=supplier_id,
            configuration=config,
            visual_notes=None,
            source="DEFAULT",
            snapshot=snap,
        )

    def build_snapshot_for_new_job(
        self,
        *,
        client_id: str | None,
        supplier_id: str | None,
    ) -> dict[str, Any]:
        """Resolve active/default once at job create (immutable thereafter)."""
        if not self._enabled:
            # Legacy path: empty profile block omitted by caller when flags off.
            return {}
        resolved = self.resolve_for_job(
            client_id=client_id,
            supplier_id=supplier_id,
            engine_params=None,
        )
        logger.info(
            "extraction_profile.snapshot_created client_id=%s supplier_id=%s "
            "profile_version=%s source=%s",
            client_id,
            supplier_id,
            resolved.profile_version,
            resolved.source,
        )
        return resolved.snapshot


__all__ = [
    "ResolvedSupplierExtractionProfile",
    "SupplierExtractionProfileResolver",
]

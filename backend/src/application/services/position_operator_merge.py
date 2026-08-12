"""
Operator-driven position merge planning (preview + confirm shared logic).

Canonical product identity: ``canonicalize_sku`` over ProductRecord.sku, falling back to
``detected_summary_json.internal_code``. Display SKU / EAN / position_barcode are not identity.

Quantity: sum of each source's final display quantity (operator correction when set, else
system-resolved qty). Independent photo-review rows are additive counted units.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.application.mappers.position_canonical_view import (
    build_position_canonical_view,
    resolve_effective_position_code,
)
from src.application.services.display_primary_product import select_display_primary_product
from src.domain.labels.canonicalization import canonicalize_sku
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord


@dataclass(frozen=True)
class MergeConflict:
    code: str
    message: str
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class MergeWarning:
    code: str
    message: str
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class MergeSourceSnapshot:
    position_id: str
    sku: str | None
    internal_code: str | None
    barcode: str | None
    description: str | None
    quantity: int
    position_code: str | None
    declared_position_code: str | None
    source_image_id: str | None
    source_image_filename: str | None
    job_id: str | None
    confidence: float
    status: str
    review_resolution: str | None
    updated_at: datetime
    product_identity: str | None


@dataclass
class MergePlan:
    can_merge: bool
    conflicts: list[MergeConflict] = field(default_factory=list)
    warnings: list[MergeWarning] = field(default_factory=list)
    sources: list[MergeSourceSnapshot] = field(default_factory=list)
    survivor_id: str | None = None
    merged_quantity: int | None = None
    merged_sku: str | None = None
    merged_internal_code: str | None = None
    merged_position_code: str | None = None
    merged_description: str | None = None
    source_count: int = 0
    image_count: int = 0
    preview_token: str = ""
    product_identity: str | None = None


def normalize_result_ids(result_ids: Sequence[str]) -> list[str]:
    """Preserve first-seen order; strip empties. Callers detect duplicates separately."""
    out: list[str] = []
    for raw in result_ids:
        pid = str(raw or "").strip()
        if pid:
            out.append(pid)
    return out


def find_duplicate_ids(result_ids: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for raw in result_ids:
        pid = str(raw or "").strip()
        if not pid:
            continue
        if pid in seen and pid not in dupes:
            dupes.append(pid)
        seen.add(pid)
    return dupes


def declared_position_code(position: Position) -> str | None:
    """Operator/pipeline declared shelf code — excludes fallback to position id."""
    if position.corrected_position_code is not None and str(position.corrected_position_code).strip():
        return str(position.corrected_position_code).strip()
    summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
    for key in ("pallet_id", "position_barcode"):
        value = summary.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def product_identity_key(
    position: Position,
    primary_product: ProductRecord | None,
) -> str | None:
    if primary_product is not None:
        canon = canonicalize_sku(primary_product.sku)
        if canon:
            return canon
    summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
    internal = summary.get("internal_code")
    if isinstance(internal, str):
        return canonicalize_sku(internal)
    return None


def summary_internal_code(position: Position) -> str | None:
    summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
    raw = summary.get("internal_code")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def build_preview_token(
    positions: Sequence[Position],
    products: Sequence[ProductRecord] | None = None,
) -> str:
    """Fingerprint of the merge read-set (positions + product records that affect the plan)."""
    parts = [
        f"p:{p.id}:{p.updated_at.isoformat()}"
        for p in sorted(positions, key=lambda x: x.id)
    ]
    for product in sorted(products or (), key=lambda x: x.id):
        parts.append(f"pr:{product.id}:{product.updated_at.isoformat()}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest


def _single_product_or_none(
    products_by_position: Mapping[str, Sequence[ProductRecord]],
    position_id: str,
) -> tuple[ProductRecord | None, int]:
    """Return (sole product, count). Count > 1 means ambiguous Position for merge."""
    products = list(products_by_position.get(position_id) or ())
    if not products:
        return None, 0
    if len(products) == 1:
        return products[0], 1
    return None, len(products)


def _source_snapshot(
    position: Position,
    primary: ProductRecord | None,
) -> MergeSourceSnapshot:
    view = build_position_canonical_view(position, primary_product=primary)
    description = None
    if primary is not None and primary.description and str(primary.description).strip():
        description = str(primary.description).strip()
    else:
        snap = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
        label = snap.get("display_label") or snap.get("description")
        if isinstance(label, str) and label.strip():
            description = label.strip()
    return MergeSourceSnapshot(
        position_id=position.id,
        sku=view.product.public_sku,
        internal_code=summary_internal_code(position),
        barcode=view.product.barcode,
        description=description,
        quantity=view.quantity.final_display_quantity,
        position_code=view.position_code,
        declared_position_code=declared_position_code(position),
        source_image_id=view.traceability.source_image_id,
        source_image_filename=view.traceability.source_image_original_filename,
        job_id=position.job_id,
        confidence=float(position.confidence),
        status=position.status.value,
        review_resolution=(
            position.review_resolution.value if position.review_resolution is not None else None
        ),
        updated_at=position.updated_at,
        product_identity=product_identity_key(position, primary),
    )


def plan_position_merge(
    positions: Sequence[Position],
    *,
    products_by_position: Mapping[str, Sequence[ProductRecord]],
    aisle_id: str,
) -> MergePlan:
    """Build merge plan for already-loaded positions (no I/O)."""
    conflicts: list[MergeConflict] = []
    warnings: list[MergeWarning] = []

    if len(positions) < 2:
        conflicts.append(
            MergeConflict(
                code="insufficient_results",
                message="Se necesitan al menos 2 resultados para fusionar.",
            )
        )
        return MergePlan(can_merge=False, conflicts=conflicts, sources=[])

    for position in positions:
        if position.aisle_id != aisle_id:
            conflicts.append(
                MergeConflict(
                    code="aisle_mismatch",
                    message="Hay resultados que no pertenecen al pasillo indicado.",
                    values=(position.id,),
                )
            )
        if position.status == PositionStatus.DELETED:
            conflicts.append(
                MergeConflict(
                    code="result_deleted",
                    message="Hay resultados eliminados en la selección.",
                    values=(position.id,),
                )
            )
        if position.is_merged_source:
            conflicts.append(
                MergeConflict(
                    code="already_merged",
                    message="Hay resultados que ya fueron fusionados.",
                    values=(position.id,),
                )
            )
        product_count = len(list(products_by_position.get(position.id) or ()))
        if product_count > 1:
            conflicts.append(
                MergeConflict(
                    code="ambiguous_position_products",
                    message=(
                        "La posición tiene múltiples ProductRecords; "
                        "no se puede fusionar sin identificar un único producto lógico."
                    ),
                    values=(position.id,),
                )
            )
        if (
            position.merged_into_position_id is not None
            and str(position.merged_into_position_id).strip() == position.id
        ):
            conflicts.append(
                MergeConflict(
                    code="self_merge",
                    message="Un resultado no puede fusionarse consigo mismo.",
                    values=(position.id,),
                )
            )

    sources: list[MergeSourceSnapshot] = []
    for p in positions:
        sole, count = _single_product_or_none(products_by_position, p.id)
        # Snapshot still built for UI even when ambiguous (can_merge false).
        primary = sole if count <= 1 else None
        if count > 1:
            primary = select_display_primary_product(
                list(products_by_position.get(p.id) or ())
            )
        sources.append(_source_snapshot(p, primary))

    identities = {s.product_identity for s in sources if s.product_identity}
    missing_identity = [s.position_id for s in sources if not s.product_identity]
    if missing_identity:
        conflicts.append(
            MergeConflict(
                code="missing_product_identity",
                message="Uno o más resultados no tienen identidad de producto (SKU/internal_code).",
                values=tuple(missing_identity),
            )
        )
    if len(identities) > 1:
        conflicts.append(
            MergeConflict(
                code="sku_mismatch",
                message="Los resultados no comparten la misma identidad canónica de producto.",
                values=tuple(sorted(identities)),
            )
        )

    declared_codes = sorted(
        {s.declared_position_code for s in sources if s.declared_position_code}
    )
    if len(declared_codes) > 1:
        conflicts.append(
            MergeConflict(
                code="position_code_mismatch",
                message="Hay registros en distintas posiciones.",
                values=tuple(declared_codes),
            )
        )
    elif declared_codes and any(s.declared_position_code is None for s in sources):
        warnings.append(
            MergeWarning(
                code="position_code_partial",
                message="Algunos registros no tienen código de posición declarado.",
                values=tuple(declared_codes),
            )
        )

    descriptions = sorted({s.description for s in sources if s.description})
    if len(descriptions) > 1:
        warnings.append(
            MergeWarning(
                code="description_mismatch",
                message="Las descripciones de producto no coinciden; se conserva la del resultado sobreviviente.",
                values=tuple(descriptions),
            )
        )

    job_ids = sorted({(s.job_id or "") for s in sources})
    if len(job_ids) > 1:
        warnings.append(
            MergeWarning(
                code="job_mismatch",
                message="Los resultados provienen de distintas corridas/jobs.",
                values=tuple(j or "(legacy)" for j in job_ids),
            )
        )

    image_ids = sorted({s.source_image_id for s in sources if s.source_image_id})
    if len(image_ids) > 1:
        warnings.append(
            MergeWarning(
                code="multiple_images",
                message="La fusión combina evidencias de múltiples imágenes.",
                values=tuple(image_ids),
            )
        )

    barcodes = sorted({s.barcode for s in sources if s.barcode})
    if len(barcodes) > 1:
        warnings.append(
            MergeWarning(
                code="barcode_mismatch",
                message="Los códigos de barras / EAN no coinciden entre registros.",
                values=tuple(barcodes),
            )
        )

    can_merge = len(conflicts) == 0
    survivor = sorted(positions, key=lambda p: (p.created_at, p.id))[0] if can_merge else None
    survivor_snap = next((s for s in sources if s.position_id == survivor.id), None) if survivor else None
    total_qty = sum(s.quantity for s in sources) if can_merge else None
    identity = next(iter(identities), None) if len(identities) == 1 else None

    merged_position_code = None
    if can_merge and survivor is not None:
        if declared_codes:
            merged_position_code = declared_codes[0]
        else:
            merged_position_code = resolve_effective_position_code(survivor)

    return MergePlan(
        can_merge=can_merge,
        conflicts=conflicts,
        warnings=warnings,
        sources=sources,
        survivor_id=survivor.id if survivor else None,
        merged_quantity=total_qty,
        merged_sku=survivor_snap.sku if survivor_snap else None,
        merged_internal_code=survivor_snap.internal_code if survivor_snap else None,
        merged_position_code=merged_position_code,
        merged_description=survivor_snap.description if survivor_snap else None,
        source_count=len(sources),
        image_count=len(image_ids) if image_ids else len(
            {s.source_image_filename for s in sources if s.source_image_filename}
        ),
        preview_token=build_preview_token(
            positions,
            [
                pr
                for pid in {p.id for p in positions}
                for pr in (products_by_position.get(pid) or ())
            ],
        ),
        product_identity=identity,
    )


def apply_survivor_summary(
    survivor: Position,
    *,
    source_ids: Sequence[str],
    merged_quantity: int,
) -> dict[str, Any]:
    summary = (
        dict(survivor.detected_summary_json)
        if isinstance(survivor.detected_summary_json, dict)
        else {}
    )
    summary["final_quantity"] = int(merged_quantity)
    summary["aggregated_from_ids"] = list(source_ids)
    return summary

"""Map internal export row dicts to CSV fieldnames (legacy vs business profiles)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

ExportCsvProfile = Literal["legacy", "business"]

# Business operational CSV — human-readable columns first, technical IDs last.
BUSINESS_OPERATIONAL_CSV_FIELDS: tuple[str, ...] = (
    "Inventario",
    "Cliente",
    "Proveedor",
    "Pasillo",
    "Secuencia de pasillo",
    "Posición",
    "Producto",
    "SKU",
    "Código de barras",
    "Cantidad detectada",
    "Cantidad corregida",
    "Cantidad final",
    "Origen de cantidad",
    "Estado de posición",
    "Requiere revisión",
    "Estado de trazabilidad",
    "Incluido en totales",
    "Motivo de exclusión",
    "Costo unitario",
    "Costo total de línea",
    "Última actualización",
    "inventory_id",
    "aisle_id",
    "position_id",
    "source_image_id",
    "primary_evidence_id",
    "job_id",
)

BUSINESS_INVENTORY_SUMMARY_CSV_FIELDS: tuple[str, ...] = (
    "Inventario",
    "Cliente",
    "Fecha de exportación",
    "Total de pasillos",
    "Total de posiciones",
    "Posiciones válidas",
    "Posiciones inválidas",
    "Posiciones con revisión pendiente",
    "Total contabilizado",
    "Costo total del inventario",
)

BUSINESS_AISLES_SUMMARY_CSV_FIELDS: tuple[str, ...] = (
    "Inventario",
    "Pasillo",
    "Secuencia",
    "Proveedor",
    "Total de posiciones",
    "Posiciones válidas",
    "Posiciones inválidas",
    "Requieren revisión",
    "Total contabilizado",
    "Costo del pasillo",
    "Última actualización",
)

_EXCLUSION_REASON_LABELS: dict[str, str] = {
    "deleted": "Eliminada",
    "traceability_invalid": "Trazabilidad inválida",
}


class ExportCsvColumnMapper:
    """Convert internal row dictionaries to profile-specific CSV rows."""

    @staticmethod
    def operational_fieldnames(
        profile: ExportCsvProfile,
        *,
        technical: bool = False,
        legacy_fieldnames: Sequence[str],
        technical_fieldnames: Sequence[str],
    ) -> tuple[str, ...]:
        if technical:
            return tuple(technical_fieldnames)
        if profile == "business":
            return BUSINESS_OPERATIONAL_CSV_FIELDS
        return tuple(legacy_fieldnames)

    @staticmethod
    def map_operational_row(
        internal: Mapping[str, Any],
        *,
        profile: ExportCsvProfile,
        client_name: str = "",
        supplier_name: str = "",
        included_in_totals: bool | None = None,
        exclusion_reason: str | None = None,
        unit_cost: str = "",
        line_cost: str = "",
        job_id: str = "",
    ) -> dict[str, Any]:
        if profile == "legacy":
            return dict(internal)
        return {
            "Inventario": internal.get("inventory_name", ""),
            "Cliente": client_name,
            "Proveedor": supplier_name,
            "Pasillo": internal.get("aisle_code", ""),
            "Secuencia de pasillo": internal.get("aisle_sequence", ""),
            "Posición": internal.get("position_code", ""),
            "Producto": internal.get("product_display_label", ""),
            "SKU": internal.get("product_sku", ""),
            "Código de barras": internal.get("barcode", ""),
            "Cantidad detectada": internal.get("detected_quantity", ""),
            "Cantidad corregida": internal.get("corrected_quantity", ""),
            "Cantidad final": internal.get("final_quantity", ""),
            "Origen de cantidad": internal.get("qty_source", ""),
            "Estado de posición": internal.get("position_status", ""),
            "Requiere revisión": internal.get("needs_review", ""),
            "Estado de trazabilidad": internal.get("traceability_status", ""),
            "Incluido en totales": (
                "sí" if included_in_totals else "no" if included_in_totals is not None else ""
            ),
            "Motivo de exclusión": ExportCsvColumnMapper.exclusion_reason_label(exclusion_reason),
            "Costo unitario": unit_cost,
            "Costo total de línea": line_cost,
            "Última actualización": internal.get("updated_at", ""),
            "inventory_id": internal.get("inventory_id", ""),
            "aisle_id": internal.get("aisle_id", ""),
            "position_id": internal.get("position_id", ""),
            "source_image_id": internal.get("source_image_id", ""),
            "primary_evidence_id": internal.get("primary_evidence_id", ""),
            "job_id": job_id,
        }

    @staticmethod
    def exclusion_reason_label(reason: str | None) -> str:
        if not reason:
            return ""
        return _EXCLUSION_REASON_LABELS.get(reason, reason)

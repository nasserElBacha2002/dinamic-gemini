"""Storage path convention for supplier reference images — Phase C1."""

from __future__ import annotations

from src.application.utils.reference_image_mime import extension_from_mime_type


def supplier_reference_image_storage_path(
    client_supplier_id: str,
    reference_image_id: str,
    mime_type: str,
) -> str:
    """Build relative storage path for a supplier reference image."""
    ext = extension_from_mime_type(mime_type)
    return (
        f"client_suppliers/{client_supplier_id}/reference_images/"
        f"{reference_image_id}.{ext}"
    )

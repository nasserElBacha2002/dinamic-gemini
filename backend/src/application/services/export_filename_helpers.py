"""Readable export filenames with safe fallbacks to ids."""

from __future__ import annotations

import re


def sanitize_filename_part(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^\w\-.]+", "_", (value or "").strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._")
    return (cleaned[:80] if cleaned else fallback)


def inventory_export_basename(inventory_name: str, inventory_id: str) -> str:
    part = sanitize_filename_part(inventory_name, fallback=inventory_id)
    return f"inventory_{part}"


def aisle_operational_csv_filename(
    *,
    inventory_name: str,
    inventory_id: str,
    aisle_code: str,
    aisle_id: str,
    profile: str = "business",
) -> str:
    inv_part = sanitize_filename_part(inventory_name, fallback=inventory_id)
    aisle_part = sanitize_filename_part(aisle_code, fallback=aisle_id)
    suffix = "operational" if profile == "business" else "results"
    return f"inventory_{inv_part}_aisle_{aisle_part}_{suffix}.csv"


def inventory_package_zip_filename(inventory_name: str, inventory_id: str) -> str:
    return f"{inventory_export_basename(inventory_name, inventory_id)}_export.zip"


def inventory_summary_csv_filename(inventory_name: str, inventory_id: str) -> str:
    return f"{inventory_export_basename(inventory_name, inventory_id)}_summary.csv"


def inventory_aisles_summary_csv_filename(inventory_name: str, inventory_id: str) -> str:
    return f"{inventory_export_basename(inventory_name, inventory_id)}_aisles_summary.csv"

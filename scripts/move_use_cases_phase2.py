#!/usr/bin/env python3
"""Phase 2: git mv use_cases modules and rewrite imports (move-only)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UC = REPO / "backend" / "src" / "application" / "use_cases"

MODULE_TO_PKG: dict[str, str] = {
    "review_validation": "shared",
    "benchmark_compare_support": "shared",
    "capture_session_group_assignment_guard": "shared",
    "create_inventory": "inventories",
    "get_inventory": "inventories",
    "list_inventories": "inventories",
    "list_inventory_list_items": "inventories",
    "get_inventory_metrics": "inventories",
    "backfill_inventory_statuses": "inventories",
    "export_inventory_results": "inventories",
    "export_inventory_business": "inventories",
    "create_aisle": "aisles",
    "list_aisles_by_inventory": "aisles",
    "list_aisles_with_status": "aisles",
    "get_aisle_processing_status": "aisles",
    "start_aisle_processing": "aisles",
    "cancel_aisle_job": "aisles",
    "retry_aisle_job": "aisles",
    "list_aisle_jobs": "aisles",
    "promote_aisle_operational_job": "aisles",
    "resolve_aisle_job_for_inventory_read": "aisles",
    "run_aisle_merge": "aisles",
    "get_aisle_merge_results": "aisles",
    "upload_aisle_assets": "aisles",
    "list_aisle_assets": "aisles",
    "delete_aisle_source_asset": "aisles",
    "backfill_legacy_aisles": "aisles",
    "list_aisle_positions": "positions",
    "get_position_detail": "positions",
    "get_position_code_scan_evidence": "positions",
    "confirm_position": "positions",
    "delete_position": "positions",
    "update_position_code": "positions",
    "update_product_quantity": "positions",
    "update_product_sku": "positions",
    "mark_position_unknown": "positions",
    "mark_position_image_mismatch": "positions",
    "list_review_queue": "positions",
    "create_client": "clients",
    "get_client": "clients",
    "list_clients": "clients",
    "create_client_supplier": "suppliers",
    "get_client_supplier": "suppliers",
    "list_client_suppliers": "suppliers",
    "manage_supplier_prompt_configs": "suppliers",
    "manage_supplier_reference_images": "suppliers",
    "upload_supplier_reference_images": "suppliers",
    "backfill_legacy_client_supplier_defaults": "suppliers",
    "create_capture_session": "capture_sessions",
    "close_capture_session": "capture_sessions",
    "cancel_capture_session": "capture_sessions",
    "list_capture_sessions": "capture_sessions",
    "get_capture_session_detail": "capture_sessions",
    "upload_capture_session_staging_items": "capture_sessions",
    "update_capture_session_clock_offset": "capture_sessions",
    "compute_capture_session_assignment_preview": "capture_sessions",
    "compute_capture_session_groups": "capture_sessions",
    "get_capture_session_groups": "capture_sessions",
    "assign_capture_session_group_to_existing_aisle": "capture_sessions",
    "create_aisle_and_assign_capture_session_group": "capture_sessions",
    "compute_materialized_capture_session_group_preview": "capture_sessions",
    "materialize_capture_session": "capture_sessions",
    "materialize_capture_session_group": "capture_sessions",
    "run_aisle_code_scan": "code_scans",
    "list_aisle_code_scans": "code_scans",
    "summarize_aisle_code_scans": "code_scans",
    "match_aisle_code_scan_detections": "code_scans",
    "get_aisle_code_scan_review_signals": "code_scans",
    "export_aisle_code_scans": "code_scans",
    "compare_aisle_runs": "analytics",
    "compare_many_aisle_runs": "analytics",
    "export_aisle_benchmark": "analytics",
    "persist_aisle_result": "pipeline",
    "recompute_consolidated_counts": "pipeline",
}

# Longest module names first to avoid partial replacements
MODULES_SORTED = sorted(MODULE_TO_PKG.keys(), key=len, reverse=True)

IMPORT_FROM_RE = re.compile(
    r"from src\.application\.use_cases\.(?P<mod>[a-z_]+) import"
)

IMPORT_FROM_PKG_RE = re.compile(
    r"from src\.application\.use_cases\.(?P<pkg>[a-z_]+)\.(?P<mod>[a-z_]+) import"
)


def new_import_path(mod: str) -> str:
    pkg = MODULE_TO_PKG[mod]
    return f"from src.application.use_cases.{pkg}.{mod} import"


def rewrite_line(line: str) -> str:
    def _replace_from(m: re.Match[str]) -> str:
        mod = m.group("mod")
        if mod not in MODULE_TO_PKG:
            return m.group(0)
        return new_import_path(mod)

    line = IMPORT_FROM_RE.sub(_replace_from, line)

    # Fix double-prefix if file was already partially updated
    for mod, pkg in MODULE_TO_PKG.items():
        bad = f"from src.application.use_cases.{pkg}.{pkg}.{mod} import"
        good = f"from src.application.use_cases.{pkg}.{mod} import"
        line = line.replace(bad, good)
    return line


def git_mv_files() -> None:
    packages = sorted(set(MODULE_TO_PKG.values()))
    for pkg in packages:
        pkg_dir = UC / pkg
        pkg_dir.mkdir(parents=True, exist_ok=True)
        init = pkg_dir / "__init__.py"
        if not init.exists():
            init.write_text('"""Use cases — {}."""\n'.format(pkg), encoding="utf-8")

    moved = 0
    for mod, pkg in MODULE_TO_PKG.items():
        src = UC / f"{mod}.py"
        dst = UC / pkg / f"{mod}.py"
        if dst.exists():
            continue
        if not src.exists():
            print(f"SKIP missing: {src}", file=sys.stderr)
            continue
        subprocess.run(["git", "mv", str(src), str(dst)], check=True, cwd=REPO)
        moved += 1
    print(f"git mv: {moved} files")


def update_imports_in_tree() -> int:
    roots = [REPO / "backend"]
    changed_files = 0
    for root in roots:
        for path in root.rglob("*.py"):
            if path.name == "move_use_cases_phase2.py":
                continue
            text = path.read_text(encoding="utf-8")
            new_lines = [rewrite_line(line) for line in text.splitlines(keepends=True)]
            new_text = "".join(new_lines)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                changed_files += 1
    return changed_files


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "all"
    if action in ("mv", "all"):
        git_mv_files()
    if action in ("imports", "all"):
        n = update_imports_in_tree()
        print(f"import rewrite: {n} files")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# READ ONLY — NO DATA MODIFICATION
"""Dry-run analyzer: classify ``inventory_visual_references`` rows for future C6 migration.

Safety:
  - SELECT queries only (no INSERT/UPDATE/DELETE/MERGE/DDL).
  - No file copy/move/delete.
  - Default: exit 0 even when DB is unavailable (writes ``db_connected=false`` artifacts for audits).
  - ``--require-db``: exit non-zero if pyodbc/settings/connect/query fails (CI / gated runs).

Run from ``backend/``:
  python scripts/analyze_legacy_reference_migration.py --output-dir ../audit/raw
  python scripts/analyze_legacy_reference_migration.py --output-dir ../audit/raw --require-db
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from legacy_reference_migration_classifier import (  # noqa: E402
    ClassificationDetail,
    InventoryDryRunSummary,
    MigrationCategory,
    classify_legacy_reference_row,
)

logger = logging.getLogger(__name__)

_DEFAULT_REPO_RAW = _BACKEND_ROOT.parent / "audit" / "raw"
_LEGACY_DEFAULT_SUPPLIER_NAME = "Legacy Default Supplier"
_DRY_RUN_VERSION = "C5.1"


def _exit_db_failure(*, require_db: bool) -> int:
    return 1 if require_db else 0


def _json_sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_sanitize(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, MigrationCategory):
        return obj.value
    return obj


def _rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        out.append({cols[i]: row[i] for i in range(len(cols))})
    return out


def _execute_select(conn: Any, sql: str, params: Sequence[Any] | None = None) -> tuple[list[dict[str, Any]], str]:
    """Run SELECT; return rows and logged SQL name only (no row contents in logs)."""

    cur = conn.cursor()
    try:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return _rows_to_dicts(cur), sql.strip().split("\n")[0][:120]
    finally:
        cur.close()


def _local_legacy_file_missing(*, storage_path: str, output_dir: Path, legacy_read_enabled: bool) -> bool | None:
    """Return True if missing, False if present, None if check skipped / not applicable."""

    if not legacy_read_enabled:
        return None
    raw = (storage_path or "").strip()
    if not raw:
        return None
    prov = ""  # legacy-path-only rows
    if prov:
        return None
    base = output_dir / "v3_uploads"
    try:
        path = (base / raw).resolve()
        resolved_base = base.resolve()
        path.relative_to(resolved_base)
    except ValueError:
        return True
    except Exception:
        return None
    return not path.is_file()


def _limit_examples(ids: list[str], limit: int) -> list[str]:
    return ids[: max(0, limit)]


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def analyze(
    *,
    output_dir: Path,
    limit_examples: int,
    check_local_files: bool,
    accept_default_supplier_fallback: bool,
    require_db: bool,
) -> int:
    sql_log_lines: list[str] = []
    db_error: str | None = None
    legacy_refs: list[dict[str, Any]] = []
    aisles_rows: list[dict[str, Any]] = []
    default_suppliers: list[dict[str, Any]] = []
    supplier_images: list[dict[str, Any]] = []
    all_suppliers: list[dict[str, Any]] = []

    try:
        import pyodbc  # noqa: PLC0415
    except ImportError as exc:
        db_error = f"pyodbc not installed: {exc}"
        sql_log_lines.append(db_error)
        _write_reports_without_db(
            output_dir=output_dir,
            sql_log_lines=sql_log_lines,
            db_error=db_error,
            limit_examples=limit_examples,
            accept_default_supplier_fallback=accept_default_supplier_fallback,
            require_db_mode=require_db,
        )
        return _exit_db_failure(require_db=require_db)

    try:
        from src.config import load_settings  # noqa: PLC0415

        settings = load_settings()
        cs = settings.require_sqlserver_connection_string()
    except Exception as exc:  # noqa: BLE001 — script boundary
        db_error = f"database configuration/connect failed: {exc}"
        logger.warning("%s", db_error)
        sql_log_lines.append(db_error)
        _write_reports_without_db(
            output_dir=output_dir,
            sql_log_lines=sql_log_lines,
            db_error=db_error,
            limit_examples=limit_examples,
            accept_default_supplier_fallback=accept_default_supplier_fallback,
            require_db_mode=require_db,
        )
        return _exit_db_failure(require_db=require_db)

    try:
        conn = pyodbc.connect(cs)
        try:
            legacy_refs, q1 = _execute_select(
                conn,
                """
                SELECT
                    v.id,
                    v.inventory_id,
                    v.filename,
                    v.storage_path,
                    v.storage_provider,
                    v.storage_bucket,
                    v.storage_key,
                    v.mime_type,
                    v.file_size,
                    v.created_at,
                    i.id AS inventory_row_present,
                    i.client_id AS inventory_client_id
                FROM dbo.inventory_visual_references AS v
                LEFT JOIN dbo.inventories AS i ON i.id = v.inventory_id
                """,
            )
            sql_log_lines.append(f"OK {q1} rows={len(legacy_refs)}")

            inv_ids = sorted({str(r.get("inventory_id")) for r in legacy_refs if r.get("inventory_id")})
            aisles_rows, q2 = _execute_select(
                conn,
                """
                SELECT DISTINCT a.inventory_id, a.client_supplier_id
                FROM dbo.aisles AS a
                INNER JOIN dbo.inventory_visual_references AS v ON v.inventory_id = a.inventory_id
                WHERE a.client_supplier_id IS NOT NULL
                """,
            )
            sql_log_lines.append(f"OK aisles_suppliers_join query rows={len(aisles_rows)}")

            default_suppliers, q3 = _execute_select(
                conn,
                """
                SELECT id, client_id
                FROM dbo.client_suppliers
                WHERE name = ?
                """,
                [_LEGACY_DEFAULT_SUPPLIER_NAME],
            )
            sql_log_lines.append(f"OK {q3} rows={len(default_suppliers)}")

            supplier_images, q4 = _execute_select(
                conn,
                """
                SELECT id, client_supplier_id, storage_path, storage_key, filename
                FROM dbo.supplier_reference_images
                """,
            )
            sql_log_lines.append(f"OK {q4} rows={len(supplier_images)}")

            all_suppliers, q5 = _execute_select(
                conn,
                """
                SELECT id, client_id FROM dbo.client_suppliers
                """,
            )
            sql_log_lines.append(f"OK {q5} rows={len(all_suppliers)}")
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        db_error = f"SQL execution failed: {exc}"
        logger.warning("%s", db_error)
        sql_log_lines.append(db_error)
        _write_reports_without_db(
            output_dir=output_dir,
            sql_log_lines=sql_log_lines,
            db_error=db_error,
            limit_examples=limit_examples,
            accept_default_supplier_fallback=accept_default_supplier_fallback,
            require_db_mode=require_db,
        )
        return _exit_db_failure(require_db=require_db)

    supplier_client_map = {str(r["id"]): str(r["client_id"]) for r in all_suppliers if r.get("id")}
    legacy_default_by_client = {
        str(r["client_id"]): str(r["id"]) for r in default_suppliers if r.get("client_id") and r.get("id")
    }

    suppliers_per_inventory: dict[str, set[str]] = defaultdict(set)
    for ar in aisles_rows:
        inv = str(ar.get("inventory_id") or "")
        sid = ar.get("client_supplier_id")
        if not inv:
            continue
        if sid is not None and str(sid).strip():
            suppliers_per_inventory[inv].add(str(sid).strip())

    inventory_summaries: dict[str, InventoryDryRunSummary] = {}
    inv_clients: dict[str, str | None] = {}
    for r in legacy_refs:
        inv = str(r.get("inventory_id") or "")
        if inv and inv not in inv_clients:
            cid = r.get("inventory_client_id")
            inv_clients[inv] = str(cid).strip() if cid is not None and str(cid).strip() else None

    for inv in set(inv_ids) | set(inv_clients.keys()):
        inventory_summaries[inv] = InventoryDryRunSummary(
            inventory_id=inv,
            client_id=inv_clients.get(inv),
            distinct_aisle_supplier_ids=frozenset(suppliers_per_inventory.get(inv, set())),
        )

    migrated_pairs_paths: set[tuple[str, str]] = set()
    migrated_pairs_keys: set[tuple[str, str]] = set()
    filenames_by_supplier: dict[str, set[str]] = defaultdict(set)
    for sim in supplier_images:
        csid = str(sim.get("client_supplier_id") or "").strip()
        if not csid:
            continue
        fn = str(sim.get("filename") or "").strip()
        sp = str(sim.get("storage_path") or "").strip()
        sk = str(sim.get("storage_key") or "").strip()
        if fn:
            filenames_by_supplier[csid].add(fn)
        if sp:
            migrated_pairs_paths.add((csid, sp))
        if sk:
            migrated_pairs_keys.add((csid, sk))

    details: list[ClassificationDetail] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    out_csv = output_dir / "phase-c5-legacy-reference-migration-details.csv"

    legacy_read_enabled = False
    output_path = Path(".")
    try:
        from src.config import load_settings as _ls  # noqa: PLC0415

        _st = _ls()
        legacy_read_enabled = bool(_st.artifact_storage_legacy_local_read_enabled)
        output_path = Path(_st.output_dir)
    except Exception:
        pass

    fieldnames = [
        "reference_id",
        "inventory_id",
        "filename",
        "mime_type",
        "file_size",
        "storage_path",
        "storage_provider",
        "storage_key",
        "category",
        "reason_code",
        "target_client_id",
        "target_client_supplier_id",
        "duplicate_candidate",
        "local_file_missing",
    ]
    csv_rows: list[dict[str, Any]] = []

    for row in legacy_refs:
        inv_id = str(row.get("inventory_id") or "")
        inventory_missing = row.get("inventory_row_present") is None
        summary = inventory_summaries.get(inv_id)

        d = classify_legacy_reference_row(
            row=row,
            inventory_missing=inventory_missing,
            inventory_summary=summary,
            legacy_default_supplier_by_client=legacy_default_by_client,
            accept_default_supplier_fallback=accept_default_supplier_fallback,
            migrated_pairs_paths=frozenset(migrated_pairs_paths),
            migrated_pairs_keys=frozenset(migrated_pairs_keys),
            existing_filenames_by_supplier={k: frozenset(v) for k, v in filenames_by_supplier.items()},
            supplier_client_map=supplier_client_map,
        )

        local_miss: bool | None = None
        if check_local_files:
            prov = (row.get("storage_provider") or "").strip()
            if not prov:
                local_miss = _local_legacy_file_missing(
                    storage_path=str(row.get("storage_path") or ""),
                    output_dir=output_path,
                    legacy_read_enabled=legacy_read_enabled,
                )
        d.local_file_missing = local_miss
        details.append(d)

        csv_rows.append(
            {
                "reference_id": d.reference_id,
                "inventory_id": d.inventory_id,
                "filename": row.get("filename"),
                "mime_type": row.get("mime_type"),
                "file_size": row.get("file_size"),
                "storage_path": row.get("storage_path"),
                "storage_provider": row.get("storage_provider"),
                "storage_key": row.get("storage_key"),
                "category": d.category.value,
                "reason_code": d.reason_code,
                "target_client_id": d.target_client_id,
                "target_client_supplier_id": d.target_client_supplier_id,
                "duplicate_candidate": d.duplicate_candidate,
                "local_file_missing": d.local_file_missing,
            }
        )

    _write_csv(out_csv, fieldnames, csv_rows)

    counts = Counter(d.category for d in details)
    distinct_inv = {d.inventory_id for d in details}

    inv_with_refs_client = {
        inv for inv in distinct_inv if (inventory_summaries.get(inv) and inventory_summaries[inv].client_id)
    }
    inv_without_client = distinct_inv - inv_with_refs_client

    zero_sup = []
    one_sup = []
    multi_sup = []
    for inv in distinct_inv:
        s = inventory_summaries.get(inv)
        if not s:
            continue
        n = len(s.distinct_aisle_supplier_ids)
        if n == 0:
            zero_sup.append(inv)
        elif n == 1:
            one_sup.append(inv)
        else:
            multi_sup.append(inv)

    auto_mappable = counts[MigrationCategory.AUTO_SINGLE_SUPPLIER] + counts[
        MigrationCategory.AUTO_LEGACY_DEFAULT_SUPPLIER
    ]
    ambiguous = (
        counts[MigrationCategory.AMBIGUOUS_MULTI_SUPPLIER]
        + counts[MigrationCategory.AMBIGUOUS_MISSING_CLIENT]
        + counts[MigrationCategory.AMBIGUOUS_NO_SUPPLIER]
    )
    missing_storage = counts[MigrationCategory.SKIP_MISSING_STORAGE]

    summary_json: dict[str, Any] = {
        "dry_run_version": _DRY_RUN_VERSION,
        "require_db_mode": require_db,
        "db_connected": db_error is None,
        "db_error": db_error,
        "accept_default_supplier_fallback": accept_default_supplier_fallback,
        "legacy_default_supplier_name": _LEGACY_DEFAULT_SUPPLIER_NAME,
        "total_legacy_reference_rows": len(details),
        "distinct_inventories_with_legacy_references": len(distinct_inv),
        "inventories_with_client_id": len(inv_with_refs_client),
        "inventories_without_client_id": len(inv_without_client),
        "inventories_with_zero_supplier_assignments": len(set(zero_sup)),
        "inventories_with_one_supplier_assignment": len(set(one_sup)),
        "inventories_with_multiple_supplier_assignments": len(set(multi_sup)),
        "legacy_references_auto_single_supplier": counts[MigrationCategory.AUTO_SINGLE_SUPPLIER],
        "legacy_references_auto_legacy_default_supplier": counts[
            MigrationCategory.AUTO_LEGACY_DEFAULT_SUPPLIER
        ],
        "legacy_references_ambiguous_multi_supplier": counts[MigrationCategory.AMBIGUOUS_MULTI_SUPPLIER],
        "legacy_references_ambiguous_missing_client": counts[MigrationCategory.AMBIGUOUS_MISSING_CLIENT],
        "legacy_references_ambiguous_no_supplier": counts[MigrationCategory.AMBIGUOUS_NO_SUPPLIER],
        "legacy_references_skip_missing_storage": counts[MigrationCategory.SKIP_MISSING_STORAGE],
        "legacy_references_skip_invalid_row": counts[MigrationCategory.SKIP_INVALID_ROW],
        "legacy_references_skip_already_migrated": counts[MigrationCategory.SKIP_ALREADY_MIGRATED],
        "auto_mappable_rows": auto_mappable,
        "ambiguous_rows": ambiguous,
        "missing_storage_rows": missing_storage,
    }

    summary_path = output_dir / "phase-c5-legacy-reference-migration-summary.json"
    summary_path.write_text(json.dumps(_json_sanitize(summary_json), indent=2), encoding="utf-8")

    sql_results_path = output_dir / "phase-c5-legacy-reference-migration-sql-results.txt"
    sql_results_path.write_text("\n".join(sql_log_lines) + "\n", encoding="utf-8")

    _write_example_extracts(output_dir=output_dir, details=details, limit=limit_examples)

    _write_open_decisions(output_dir=output_dir, summary_json=summary_json)

    logger.info("Wrote %s", summary_path)
    logger.info("Wrote %s", out_csv)
    return 0


def _write_example_extracts(*, output_dir: Path, details: Sequence[ClassificationDetail], limit: int) -> None:
    by_cat: dict[MigrationCategory, list[ClassificationDetail]] = defaultdict(list)
    for d in details:
        by_cat[d.category].append(d)

    ambigs = [
        MigrationCategory.AMBIGUOUS_MULTI_SUPPLIER,
        MigrationCategory.AMBIGUOUS_MISSING_CLIENT,
        MigrationCategory.AMBIGUOUS_NO_SUPPLIER,
    ]
    miss_stor = [d for d in details if d.category == MigrationCategory.SKIP_MISSING_STORAGE]
    dup_cand = [d for d in details if d.duplicate_candidate]

    examples_md_path = output_dir / "phase-c5-legacy-reference-migration-examples-extract.md"
    lines: list[str] = ["# C5 — Example row ids (truncated)", ""]
    for cat in ambigs:
        ids = _limit_examples([d.reference_id for d in by_cat[cat]], limit)
        lines.append(f"## {cat.value}")
        lines.extend(f"- `{x}`" for x in ids)
        lines.append("")
    lines.append("## SKIP_MISSING_STORAGE")
    lines.extend(f"- `{x}`" for x in _limit_examples([d.reference_id for d in miss_stor], limit))
    lines.append("")
    lines.append("## duplicate_candidate")
    lines.extend(f"- `{x}`" for x in _limit_examples([d.reference_id for d in dup_cand], limit))
    lines.append("")
    examples_md_path.write_text("\n".join(lines), encoding="utf-8")


def _write_open_decisions(*, output_dir: Path, summary_json: Mapping[str, Any]) -> None:
    p = output_dir / "phase-c5-legacy-reference-migration-open-decisions.md"
    text = f"""# C5 — Open product decisions (blocking before C6)

Generated summary snapshot: `phase-c5-legacy-reference-migration-summary.json`.

## Required decisions

1. **Multi-supplier inventories** (`legacy_references_ambiguous_multi_supplier` = {summary_json.get("legacy_references_ambiguous_multi_supplier")})
   - Duplicate image per supplier vs Legacy/Default Supplier vs manual mapping vs primary-supplier rule.

2. **Missing client** (`legacy_references_ambiguous_missing_client` = {summary_json.get("legacy_references_ambiguous_missing_client")})
   - Assign inventory to client first vs migrate to Legacy/Default Client vs manual only.

3. **No aisle supplier + Legacy/Default Supplier** (`legacy_references_ambiguous_no_supplier` with fallback policy)
   - Accept auto-fallback (`accept_default_supplier_fallback` was {summary_json.get("accept_default_supplier_fallback", True)}) vs require explicit supplier on aisles.

4. **Retention / archival** before dropping `inventory_visual_references`.

5. **SKIP_ALREADY_MIGRATED heuristic** — confirm mapping table for authoritative idempotency in C6.

## Mapping table

Recommend adding `legacy_reference_image_migration_map` (see main C5 report) before destructive steps.
"""
    p.write_text(text, encoding="utf-8")


def _write_reports_without_db(
    *,
    output_dir: Path,
    sql_log_lines: list[str],
    db_error: str | None,
    limit_examples: int,
    accept_default_supplier_fallback: bool,
    require_db_mode: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json = {
        "dry_run_version": _DRY_RUN_VERSION,
        "require_db_mode": require_db_mode,
        "db_connected": False,
        "db_error": db_error,
        "accept_default_supplier_fallback": accept_default_supplier_fallback,
        "legacy_default_supplier_name": _LEGACY_DEFAULT_SUPPLIER_NAME,
        "note": "Database unavailable — counts are zero; classification not executed.",
        "total_legacy_reference_rows": 0,
        "distinct_inventories_with_legacy_references": 0,
        "inventories_with_client_id": 0,
        "inventories_without_client_id": 0,
        "inventories_with_zero_supplier_assignments": 0,
        "inventories_with_one_supplier_assignment": 0,
        "inventories_with_multiple_supplier_assignments": 0,
        "legacy_references_auto_single_supplier": 0,
        "legacy_references_auto_legacy_default_supplier": 0,
        "legacy_references_ambiguous_multi_supplier": 0,
        "legacy_references_ambiguous_missing_client": 0,
        "legacy_references_ambiguous_no_supplier": 0,
        "legacy_references_skip_missing_storage": 0,
        "legacy_references_skip_invalid_row": 0,
        "legacy_references_skip_already_migrated": 0,
        "auto_mappable_rows": 0,
        "ambiguous_rows": 0,
        "missing_storage_rows": 0,
    }
    (output_dir / "phase-c5-legacy-reference-migration-summary.json").write_text(
        json.dumps(summary_json, indent=2),
        encoding="utf-8",
    )
    (output_dir / "phase-c5-legacy-reference-migration-sql-results.txt").write_text(
        "\n".join(sql_log_lines) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        output_dir / "phase-c5-legacy-reference-migration-details.csv",
        [
            "reference_id",
            "inventory_id",
            "filename",
            "mime_type",
            "file_size",
            "storage_path",
            "storage_provider",
            "storage_key",
            "category",
            "reason_code",
            "target_client_id",
            "target_client_supplier_id",
            "duplicate_candidate",
            "local_file_missing",
        ],
        [],
    )
    _write_open_decisions(output_dir=output_dir, summary_json=summary_json)
    (output_dir / "phase-c5-legacy-reference-migration-examples-extract.md").write_text(
        f"# C5 examples\n\n(DB unavailable; limit_examples={limit_examples})\n",
        encoding="utf-8",
    )


def _derive_filtered_csvs(output_dir: Path) -> None:
    """Build auxiliary CSVs from details CSV if present."""

    details_path = output_dir / "phase-c5-legacy-reference-migration-details.csv"
    if not details_path.is_file():
        return
    rows: list[dict[str, str]] = []
    with details_path.open(encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)

    def write_filter(name: str, pred: Any) -> None:
        sub = [x for x in rows if pred(x)]
        if not sub:
            return
        _write_csv(output_dir / name, list(sub[0].keys()), sub)

    write_filter(
        "phase-c5-missing-storage-candidates.csv",
        lambda x: x.get("category") == MigrationCategory.SKIP_MISSING_STORAGE.value,
    )
    inv_multi: dict[str, list[str]] = defaultdict(list)
    for x in rows:
        if x.get("category") == MigrationCategory.AMBIGUOUS_MULTI_SUPPLIER.value:
            inv_multi[x.get("inventory_id") or ""].append(x.get("reference_id") or "")
    if inv_multi:
        multi_rows = [{"inventory_id": k, "reference_count": len(v)} for k, v in inv_multi.items()]
        _write_csv(
            output_dir / "phase-c5-ambiguous-multi-supplier-inventories.csv",
            ["inventory_id", "reference_count"],
            multi_rows,
        )

    inv_miss_client = {x.get("inventory_id") for x in rows if x.get("category") == "AMBIGUOUS_MISSING_CLIENT"}
    if inv_miss_client:
        mc = [{"inventory_id": i} for i in sorted(inv_miss_client) if i]
        _write_csv(output_dir / "phase-c5-missing-client-inventories.csv", ["inventory_id"], mc)

    def_candidates = [
        x
        for x in rows
        if x.get("category")
        in (
            MigrationCategory.AUTO_LEGACY_DEFAULT_SUPPLIER.value,
            MigrationCategory.AMBIGUOUS_NO_SUPPLIER.value,
        )
    ]
    if def_candidates:
        _write_csv(output_dir / "phase-c5-default-supplier-candidates.csv", list(def_candidates[0].keys()), def_candidates)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_REPO_RAW,
        help="Directory for JSON/CSV/sql log (default: ../audit/raw from backend)",
    )
    parser.add_argument("--limit-examples", type=int, default=20)
    parser.add_argument(
        "--check-local-files",
        action="store_true",
        help="Best-effort legacy v3_uploads existence check (path-only rows)",
    )
    parser.add_argument(
        "--no-check-local-files",
        action="store_true",
        help="Disable local file existence checks",
    )
    parser.add_argument(
        "--no-accept-default-supplier-fallback",
        action="store_true",
        help="Classify no-aisle-supplier rows as AMBIGUOUS_NO_SUPPLIER even if default exists",
    )
    parser.add_argument(
        "--require-db",
        action="store_true",
        help="Exit non-zero when DB driver/config/connect/query fails (strict mode)",
    )
    args = parser.parse_args(argv)
    accept = not args.no_accept_default_supplier_fallback
    check_local = args.check_local_files and not args.no_check_local_files
    rc = analyze(
        output_dir=args.output_dir.resolve(),
        limit_examples=args.limit_examples,
        check_local_files=check_local,
        accept_default_supplier_fallback=accept,
        require_db=args.require_db,
    )
    _derive_filtered_csvs(args.output_dir.resolve())
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""G1 — Read-only client-oriented drift metrics (Phase G).

Safety:
  - SELECT-only SQL (rejects statements containing risky tokens outside string literals — see
    ``_assert_select_only_sql``; best-effort, intended for controlled audit scripts).
  - No DDL/DML. No schema changes.
  - Default: exit 0 when DB unavailable; writes JSON with ``db_connected=false``.
  - ``--require-db``: exit 1 if connection or critical queries fail.

Run from ``backend/``:
  python scripts/client_oriented_drift_report.py
  python scripts/client_oriented_drift_report.py --output-json ../audit/raw/phase-g/g1-drift-report.json
  python scripts/client_oriented_drift_report.py --require-db --job-json-sample-limit 30

Outputs:
  - JSON report path (default: ``../audit/raw/phase-g/g1-drift-report.json`` relative to cwd or --output-json).
  - Summary to stdout.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

logger = logging.getLogger(__name__)

_FORBIDDEN_SQL_TOKENS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|MERGE|EXEC|EXECUTE|CREATE)\b",
    re.IGNORECASE,
)


def _assert_select_only_sql(sql: str) -> None:
    s = (sql or "").strip()
    if not s:
        raise ValueError("empty SQL")
    head = s.lstrip("(").strip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise ValueError("SQL must start with SELECT or WITH (CTE)")
    if _FORBIDDEN_SQL_TOKENS.search(s):
        raise ValueError(f"SQL failed read-only guard: {s[:200]!r}")


def _json_sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_sanitize(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def _rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        out.append({cols[i]: row[i] for i in range(len(cols))})
    return out


def _execute_select(conn: Any, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    _assert_select_only_sql(sql)
    cur = conn.cursor()
    try:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return _rows_to_dicts(cur)
    finally:
        cur.close()


def _table_exists(conn: Any, table: str) -> bool:
    rows = _execute_select(
        conn,
        """
        SELECT 1 AS ok
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?
        """,
        (table,),
    )
    return bool(rows)


def _flatten_json_keys(obj: Any, prefix: str = "", *, max_paths: int = 500) -> Counter[str]:
    """Count dot-paths for dict keys (for metadata discovery)."""
    counts: Counter[str] = Counter()

    def walk(o: Any, p: str) -> None:
        if len(counts) >= max_paths:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                key = str(k)
                np = f"{p}.{key}" if p else key
                counts[np] += 1
                walk(v, np)
        elif isinstance(o, list) and o and isinstance(o[0], (dict, list)):
            for i, item in enumerate(o[:20]):
                walk(item, f"{p}[{i}]")

    walk(obj, prefix)
    return counts


def _safe_json_loads(raw: str | None) -> Any | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_report(
    *,
    output_json: Path,
    job_json_sample_limit: int,
    recent_days: int,
    require_db: bool,
) -> tuple[int, dict[str, Any]]:
    report: dict[str, Any] = {
        "report_version": "g1_drift_v1",
        "generated_at_utc": _utc_now_iso(),
        "db_connected": False,
        "db_error": None,
        "queries": {},
        "inventory_client_drift": {},
        "aisle_supplier_drift": {},
        "supplier_reference_images": {},
        "legacy_inventory_visual_references": {},
        "supplier_prompt_configs": {},
        "inventory_jobs_json_sampling": {},
        "job_events_note": (
            "job_events in schema.sql references legacy ``jobs`` (Stage 8), not ``inventory_jobs``. "
            "Sampling job_events is optional and may not correlate to v3 inventory_jobs ids."
        ),
        "static_legacy_exposure": {
            "frontend_inventory_create_client_note": (
                "Phase G2: client required in CreateInventoryDialog; "
                "dialogs.inventory.client_placeholder replaces legacy none option."
            ),
            "backend_create_inventory_client_id_note": (
                "Phase G2: CreateInventoryRequest.client_id required for POST /api/v3/inventories; "
                "inventories.client_id column remains nullable for historical rows."
            ),
            "backend_optional_aisle_supplier_schema": "backend/src/api/schemas/aisle_schemas.py",
            "tests_legacy_null_client_inventory_note": (
                "Legacy null-client creation tests removed in G2; "
                "see test_create_inventory.py and API tests for required-client coverage."
            ),
        },
    }

    try:
        import pyodbc  # noqa: PLC0415
    except ImportError as exc:
        report["db_error"] = f"pyodbc not installed: {exc}"
        _write_json(output_json, report)
        return (1 if require_db else 0), report

    try:
        from src.config import load_settings  # noqa: PLC0415

        settings = load_settings()
        cs = settings.require_sqlserver_connection_string()
    except Exception as exc:  # noqa: BLE001
        report["db_error"] = f"settings/connection string: {exc}"
        _write_json(output_json, report)
        return (1 if require_db else 0), report

    conn: Any = None
    try:
        conn = pyodbc.connect(cs)
    except Exception as exc:  # noqa: BLE001
        report["db_error"] = f"connect failed: {exc}"
        _write_json(output_json, report)
        return (1 if require_db else 0), report

    try:
        report["db_connected"] = True
        report["meta"] = {"recent_days_window": recent_days, "job_json_sample_limit": job_json_sample_limit}

        # --- Inventories ---
        inv_total = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.inventories")
        inv_null = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.inventories WHERE client_id IS NULL")
        inv_set = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.inventories WHERE client_id IS NOT NULL")
        inv_orphan = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.inventories i
            LEFT JOIN dbo.clients c ON c.id = i.client_id
            WHERE i.client_id IS NOT NULL AND c.id IS NULL
            """,
        )
        inv_inactive_client = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.inventories i
            INNER JOIN dbo.clients c ON c.id = i.client_id
            WHERE LOWER(LTRIM(RTRIM(c.status))) <> 'active'
            """,
        )
        recent_cutoff_days = max(1, int(recent_days))
        inv_recent_null = _execute_select(
            conn,
            f"""
            SELECT COUNT(*) AS c
            FROM dbo.inventories
            WHERE client_id IS NULL
              AND created_at >= DATEADD(day, -{recent_cutoff_days}, SYSUTCDATETIME())
            """,
        )
        report["inventory_client_drift"] = {
            "total_inventories": int(inv_total[0]["c"]) if inv_total else None,
            "client_id_null": int(inv_null[0]["c"]) if inv_null else None,
            "client_id_not_null": int(inv_set[0]["c"]) if inv_set else None,
            "client_id_orphan_missing_client_row": int(inv_orphan[0]["c"]) if inv_orphan else None,
            "inventories_with_inactive_client": int(inv_inactive_client[0]["c"]) if inv_inactive_client else None,
            f"client_id_null_created_last_{recent_cutoff_days}_days": int(inv_recent_null[0]["c"])
            if inv_recent_null
            else None,
        }
        report["queries"]["inventories"] = "ok"

        # --- Aisles ---
        a_total = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.aisles")
        a_null_sup = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.aisles WHERE client_supplier_id IS NULL")
        a_has_sup = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.aisles WHERE client_supplier_id IS NOT NULL")
        a_inv_no_client = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.aisles a
            INNER JOIN dbo.inventories i ON i.id = a.inventory_id
            WHERE i.client_id IS NULL
            """,
        )
        a_supplier_but_inv_no_client = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.aisles a
            INNER JOIN dbo.inventories i ON i.id = a.inventory_id
            WHERE a.client_supplier_id IS NOT NULL AND i.client_id IS NULL
            """,
        )
        a_mismatch = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.aisles a
            INNER JOIN dbo.inventories i ON i.id = a.inventory_id
            INNER JOIN dbo.client_suppliers cs ON cs.id = a.client_supplier_id
            WHERE i.client_id IS NOT NULL
              AND a.client_supplier_id IS NOT NULL
              AND cs.client_id <> i.client_id
            """,
        )
        a_orphan_supplier = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.aisles a
            LEFT JOIN dbo.client_suppliers cs ON cs.id = a.client_supplier_id
            WHERE a.client_supplier_id IS NOT NULL AND cs.id IS NULL
            """,
        )
        a_inactive_supplier = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.aisles a
            INNER JOIN dbo.client_suppliers cs ON cs.id = a.client_supplier_id
            WHERE LOWER(LTRIM(RTRIM(cs.status))) <> 'active'
            """,
        )
        a_recent_null_sup = _execute_select(
            conn,
            f"""
            SELECT COUNT(*) AS c
            FROM dbo.aisles
            WHERE client_supplier_id IS NULL
              AND created_at >= DATEADD(day, -{recent_cutoff_days}, SYSUTCDATETIME())
            """,
        )
        report["aisle_supplier_drift"] = {
            "total_aisles": int(a_total[0]["c"]) if a_total else None,
            "client_supplier_id_null": int(a_null_sup[0]["c"]) if a_null_sup else None,
            "client_supplier_id_not_null": int(a_has_sup[0]["c"]) if a_has_sup else None,
            "aisles_whose_inventory_has_null_client": int(a_inv_no_client[0]["c"]) if a_inv_no_client else None,
            "aisles_supplier_set_but_inventory_no_client": int(a_supplier_but_inv_no_client[0]["c"])
            if a_supplier_but_inv_no_client
            else None,
            "aisles_supplier_client_mismatch": int(a_mismatch[0]["c"]) if a_mismatch else None,
            "aisles_orphan_client_supplier_id": int(a_orphan_supplier[0]["c"]) if a_orphan_supplier else None,
            "aisles_with_inactive_supplier": int(a_inactive_supplier[0]["c"]) if a_inactive_supplier else None,
            f"client_supplier_id_null_created_last_{recent_cutoff_days}_days": int(a_recent_null_sup[0]["c"])
            if a_recent_null_sup
            else None,
        }
        report["queries"]["aisles"] = "ok"

        # --- Supplier reference images ---
        cs_total = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.client_suppliers")
        sri_total = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.supplier_reference_images")
        sup_with_img = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.client_suppliers cs
            WHERE EXISTS (SELECT 1 FROM dbo.supplier_reference_images sri WHERE sri.client_supplier_id = cs.id)
            """,
        )
        sup_without_img = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.client_suppliers cs
            WHERE NOT EXISTS (SELECT 1 FROM dbo.supplier_reference_images sri WHERE sri.client_supplier_id = cs.id)
            """,
        )
        active_sup_no_img = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.client_suppliers cs
            WHERE LOWER(LTRIM(RTRIM(cs.status))) = 'active'
              AND NOT EXISTS (SELECT 1 FROM dbo.supplier_reference_images sri WHERE sri.client_supplier_id = cs.id)
            """,
        )
        report["supplier_reference_images"] = {
            "total_client_suppliers": int(cs_total[0]["c"]) if cs_total else None,
            "total_supplier_reference_images": int(sri_total[0]["c"]) if sri_total else None,
            "suppliers_with_at_least_one_image": int(sup_with_img[0]["c"]) if sup_with_img else None,
            "suppliers_with_zero_images": int(sup_without_img[0]["c"]) if sup_without_img else None,
            "active_suppliers_with_zero_images": int(active_sup_no_img[0]["c"]) if active_sup_no_img else None,
        }
        report["queries"]["supplier_reference_images"] = "ok"

        # --- Legacy inventory_visual_references ---
        if _table_exists(conn, "inventory_visual_references"):
            legacy_count = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.inventory_visual_references")
            report["legacy_inventory_visual_references"] = {
                "table_exists": True,
                "row_count": int(legacy_count[0]["c"]) if legacy_count else None,
            }
        else:
            report["legacy_inventory_visual_references"] = {
                "table_exists": False,
                "row_count": None,
                "note": "Table absent (migration 0029 may have dropped it in this environment).",
            }
        report["queries"]["legacy_visual_refs"] = "ok"

        # --- Supplier prompt configs ---
        spc_total = _execute_select(conn, "SELECT COUNT(*) AS c FROM dbo.supplier_prompt_configs")
        sup_active_cfg = _execute_select(
            conn,
            """
            SELECT COUNT(DISTINCT client_supplier_id) AS c
            FROM dbo.supplier_prompt_configs
            WHERE is_active = 1
            """,
        )
        sup_no_active = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.client_suppliers cs
            WHERE NOT EXISTS (
                SELECT 1 FROM dbo.supplier_prompt_configs spc
                WHERE spc.client_supplier_id = cs.id AND spc.is_active = 1
            )
            """,
        )
        by_provider = _execute_select(
            conn,
            """
            SELECT LTRIM(RTRIM(ISNULL(provider_name, ''))) AS provider_key, COUNT(*) AS cnt
            FROM dbo.supplier_prompt_configs
            GROUP BY LTRIM(RTRIM(ISNULL(provider_name, '')))
            ORDER BY cnt DESC
            """,
        )
        multi_active = _execute_select(
            conn,
            """
            SELECT client_supplier_id, provider_scope_key, model_scope_key, SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_n
            FROM dbo.supplier_prompt_configs
            GROUP BY client_supplier_id, provider_scope_key, model_scope_key
            HAVING SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) > 1
            """,
        )
        report["supplier_prompt_configs"] = {
            "total_prompt_config_rows": int(spc_total[0]["c"]) if spc_total else None,
            "distinct_suppliers_with_active_config": int(sup_active_cfg[0]["c"]) if sup_active_cfg else None,
            "suppliers_without_active_config": int(sup_no_active[0]["c"]) if sup_no_active else None,
            "rows_by_provider_name_key": by_provider[:50],
            "scopes_with_multiple_active_rows": multi_active[:50],
            "multiple_active_violation_count": len(multi_active),
        }
        report["queries"]["supplier_prompt_configs"] = "ok"

        # --- inventory_jobs JSON sampling ---
        ij_sample = _execute_select(
            conn,
            f"""
            SELECT TOP ({int(job_json_sample_limit)})
                id, job_type, status, created_at, updated_at,
                CASE WHEN result_json IS NULL THEN 0 ELSE 1 END AS has_result_json,
                CASE WHEN payload_json IS NULL THEN 0 ELSE 1 END AS has_payload_json,
                result_json, payload_json
            FROM dbo.inventory_jobs
            ORDER BY COALESCE(updated_at, created_at) DESC
            """,
        )
        path_counter: Counter[str] = Counter()
        string_hits = Counter(
            {
                "sample_rows_result_or_payload_contains_fallback_used": 0,
                "sample_rows_result_or_payload_contains_effective_prompt_hash": 0,
                "sample_rows_result_or_payload_contains_prompt_composition": 0,
                "sample_rows_result_or_payload_contains_client_supplier_id": 0,
                "sample_rows_result_or_payload_contains_supplier_reference_resolution": 0,
            }
        )
        for row in ij_sample:
            rj = row.get("result_json")
            pj = row.get("payload_json")
            blob = ""
            if isinstance(rj, str):
                blob += rj
            if isinstance(pj, str):
                blob += pj
            if "fallback_used" in blob:
                string_hits["sample_rows_result_or_payload_contains_fallback_used"] += 1
            if "effective_prompt_hash" in blob:
                string_hits["sample_rows_result_or_payload_contains_effective_prompt_hash"] += 1
            if "prompt_composition" in blob:
                string_hits["sample_rows_result_or_payload_contains_prompt_composition"] += 1
            if "client_supplier_id" in blob:
                string_hits["sample_rows_result_or_payload_contains_client_supplier_id"] += 1
            if "supplier_reference_resolution" in blob:
                string_hits["sample_rows_result_or_payload_contains_supplier_reference_resolution"] += 1
            for col in ("result_json", "payload_json"):
                raw = row.get(col)
                parsed = _safe_json_loads(raw) if isinstance(raw, str) else None
                if isinstance(parsed, dict):
                    path_counter.update(_flatten_json_keys(parsed, prefix=col))

        top_paths = path_counter.most_common(80)
        report["inventory_jobs_json_sampling"] = {
            "sample_size": len(ij_sample),
            "substring_hits_among_sample_rows": dict(string_hits),
            "top_json_dot_paths_in_sample": [{"path": p, "count": c} for p, c in top_paths],
            "note": (
                "Paths are aggregated across parsed JSON of result_json and payload_json for recent jobs. "
                "Invalid JSON rows are skipped for path counting but may still appear in substring hits."
            ),
        }

        # Optional: substring counts across more rows (lightweight)
        fb_like = _execute_select(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM dbo.inventory_jobs
            WHERE result_json LIKE N'%fallback_used%true%'
            """,
        )
        report["inventory_jobs_json_sampling"]["approx_jobs_result_json_fallback_used_true_like"] = (
            int(fb_like[0]["c"]) if fb_like else None
        )

        report["queries"]["inventory_jobs_sample"] = "ok"

    except Exception as exc:  # noqa: BLE001
        report["db_error"] = f"query phase: {exc}"
        report["db_connected"] = False
        _write_json(output_json, report)
        return (1 if require_db else 0), report
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    _write_json(output_json, report)
    return 0, report


def _write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(_json_sanitize(report), f, indent=2, ensure_ascii=False)


def _g2_readiness(report: dict[str, Any]) -> str:
    inv = report.get("inventory_client_drift") or {}
    if not report.get("db_connected"):
        return "READY_FOR_G2_WITH_OBSERVATIONS"
    meta = report.get("meta") or {}
    recent_w = max(1, int(meta.get("recent_days_window") or 30))
    orphan = int(inv.get("client_id_orphan_missing_client_row") or 0)
    recent_null = int(inv.get(f"client_id_null_created_last_{recent_w}_days") or 0)
    if orphan > 0:
        return "NOT_READY_FOR_G2"
    if recent_null > 0:
        return "READY_FOR_G2_WITH_OBSERVATIONS"
    total_null = int(inv.get("client_id_null") or 0)
    if total_null > 0:
        return "READY_FOR_G2_WITH_OBSERVATIONS"
    return "READY_FOR_G2"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="G1 client-oriented drift report (read-only)")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Write JSON report (default: <repo>/audit/raw/phase-g/g1-drift-report.json)",
    )
    parser.add_argument("--job-json-sample-limit", type=int, default=40, help="Rows to sample from inventory_jobs")
    parser.add_argument("--recent-days", type=int, default=30, help="Window for recent NULL counts")
    parser.add_argument("--require-db", action="store_true", help="Exit non-zero if DB unavailable or query errors")
    args = parser.parse_args()

    repo_root = _BACKEND_ROOT.parent
    out = args.output_json or (repo_root / "audit/raw/phase-g/g1-drift-report.json")

    code, report = run_report(
        output_json=out,
        job_json_sample_limit=max(1, min(500, args.job_json_sample_limit)),
        recent_days=max(1, min(3650, args.recent_days)),
        require_db=args.require_db,
    )
    g2 = _g2_readiness(report)
    report["readiness_for_g2_enforce_new_inventory_client"] = g2

    # Re-write with readiness line
    _write_json(out, report)

    print("=== G1 client-oriented drift report ===")
    print(f"db_connected={report.get('db_connected')} db_error={report.get('db_error')}")
    print(f"output_json={out}")
    ic = report.get("inventory_client_drift") or {}
    print(
        f"inventories total={ic.get('total_inventories')} "
        f"client_null={ic.get('client_id_null')} client_set={ic.get('client_id_not_null')}"
    )
    ac = report.get("aisle_supplier_drift") or {}
    print(
        f"aisles total={ac.get('total_aisles')} supplier_null={ac.get('client_supplier_id_null')} "
        f"mismatch={ac.get('aisles_supplier_client_mismatch')}"
    )
    print(f"readiness_for_g2_enforce_new_inventory_client={g2}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

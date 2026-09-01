#!/usr/bin/env python3
"""Apply and verify pruebas b supplier recognition correction (business state only).

Uses the productive create+activate+effective_source flow — no manual wiring INSERT.

Usage (repo root):
  cd backend && .venv/bin/python ../scripts/apply_pruebas_b_supplier_correction.py --apply
  cd backend && .venv/bin/python ../scripts/apply_pruebas_b_supplier_correction.py --verify-all
  cd backend && .venv/bin/python ../scripts/apply_pruebas_b_supplier_correction.py --start-job --wait
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

CLIENT_ID = "8a3c9a01-7494-4be0-99be-595ecbf2b9bd"
SUPPLIER_ID = "c314c8c3-b6fd-490c-98dc-7b1ac40dca47"
INVENTORY_ID = "ec321684-5bd3-4e48-b75d-6caaf0225199"
AISLE_ID = "68a652c5-65f6-487d-a417-4349b8e3e81c"
ITEM_PAYLOAD = "LPNA000184|SKU773421|24"
POSITION_PAYLOAD = "A04-R-02|04|RIGHT|02"


def _container():
    from src.runtime.app_container import get_app_container

    return get_app_container()


def _build_start_processing_use_case():
    from src.application.services.aisle_job_launch_service import AisleJobLaunchService
    from src.application.services.inventory_access_policy import InventoryAccessPolicy
    from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
    from src.application.services.job_stale_reconciler import JobStaleReconciler
    from src.application.use_cases.aisles.start_aisle_processing import StartAisleProcessingUseCase
    from src.config import load_settings

    c = _container()
    settings = load_settings()
    return StartAisleProcessingUseCase(
        inventory_repo=c.get_inventory_repo(),
        aisle_repo=c.get_aisle_repo(),
        asset_repo=c.get_source_asset_repo(),
        job_repo=c.get_job_repo(),
        launch_service=AisleJobLaunchService(
            aisle_repo=c.get_aisle_repo(),
            job_repo=c.get_job_repo(),
            worker_launch_service=c.get_worker_launch_service(),
            clock=c.get_clock(),
            status_reconciler=InventoryStatusReconciler(
                inventory_repo=c.get_inventory_repo(),
                aisle_repo=c.get_aisle_repo(),
                clock=c.get_clock(),
            ),
        ),
        stale_reconciler=JobStaleReconciler(
            job_repo=c.get_job_repo(),
            aisle_repo=c.get_aisle_repo(),
            clock=c.get_clock(),
            stale_after_seconds=int(getattr(settings, "worker_stale_running_timeout_sec", 0) or 0),
            artifact_publication_outbox=None,
        ),
        access_policy=InventoryAccessPolicy(
            c.get_inventory_repo(),
            aisle_repo=c.get_aisle_repo(),
        ),
        client_repo=c.get_client_repo(),
        extraction_profile_repo=c.get_supplier_extraction_profile_repo(),
        client_supplier_repo=c.get_client_supplier_repo(),
        supplier_prompt_config_repo=c.get_supplier_prompt_config_repo(),
        label_profile_repo=c.get_client_supplier_label_profile_repo(),
        ordered_session_repo=c.get_ordered_capture_session_repo(),
        ordered_processing_reservation=c.get_ordered_capture_processing_reservation(),
    )


def apply_profiles() -> dict:
    from src.application.services.supplier_extraction_profiles.pruebas_b_segmented_configurations import (
        pruebas_b_item_configuration_dict,
        pruebas_b_position_configuration_dict,
    )
    from src.application.use_cases.suppliers.manage_supplier_extraction_profiles import (
        CreateSupplierExtractionProfileVersionCommand,
    )
    from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource

    c = _container()
    uc = c.get_create_supplier_extraction_profile_version_use_case()
    out: dict = {"item": None, "position": None}

    item = uc.execute(
        CreateSupplierExtractionProfileVersionCommand(
            client_id=CLIENT_ID,
            supplier_id=SUPPLIER_ID,
            configuration=pruebas_b_item_configuration_dict(),
            activate=True,
            label_kind=LabelKind.ITEM,
            effective_source=LabelProfileSource.SUPPLIER,
            created_by="apply_pruebas_b_supplier_correction",
        )
    )
    out["item"] = {"id": item.id, "version": item.version, "status": item.status.value}

    pos = uc.execute(
        CreateSupplierExtractionProfileVersionCommand(
            client_id=CLIENT_ID,
            supplier_id=SUPPLIER_ID,
            configuration=pruebas_b_position_configuration_dict(),
            activate=True,
            label_kind=LabelKind.POSITION,
            effective_source=LabelProfileSource.SUPPLIER,
            created_by="apply_pruebas_b_supplier_correction",
        )
    )
    out["position"] = {"id": pos.id, "version": pos.version, "status": pos.status.value}
    return out


def verify_db() -> dict:
    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient
    from src.domain.client_supplier.extraction_profile import ExtractionProfileStatus

    client = SqlServerClient(load_settings().require_sqlserver_connection_string())
    out: dict = {}
    with client.cursor() as cur:
        cur.execute(
            """
            SELECT label_kind, source, id, updated_at
            FROM client_supplier_label_profiles
            WHERE client_supplier_id = ?
            ORDER BY label_kind
            """,
            (SUPPLIER_ID,),
        )
        wiring = [
            {"label_kind": r[0], "source": r[1], "id": str(r[2]), "updated_at": str(r[3])}
            for r in cur.fetchall()
        ]
        out["wiring"] = wiring
        for kind in ("ITEM", "POSITION"):
            cur.execute(
                """
                SELECT id, version, status, activated_at
                FROM supplier_extraction_profiles
                WHERE supplier_id = ? AND label_kind = ? AND status = 'ACTIVE'
                """,
                (SUPPLIER_ID, kind),
            )
            rows = cur.fetchall()
            out[f"active_{kind.lower()}"] = [
                {"id": str(r[0]), "version": r[1], "status": r[2], "activated_at": str(r[3])}
                for r in rows
            ]
    out["wiring_ok"] = (
        len(wiring) == 2
        and all(r["source"] == "SUPPLIER" for r in wiring)
        and {r["label_kind"] for r in wiring} == {"ITEM", "POSITION"}
    )
    out["single_active_per_kind"] = all(
        len(out[f"active_{k}"]) == 1 for k in ("item", "position")
    )
    return out


def verify_resolver() -> dict:
    from src.application.services.label_profile_resolver import (
        LabelProfileResolutionContext,
        LabelProfileResolver,
    )

    c = _container()
    aisle = c.get_aisle_repo().get_by_id(AISLE_ID)
    resolver = LabelProfileResolver(
        label_profile_repo=c.get_client_supplier_label_profile_repo(),
        client_supplier_repo=c.get_client_supplier_repo(),
        extraction_profile_repo=c.get_supplier_extraction_profile_repo(),
        supplier_prompt_config_repo=c.get_supplier_prompt_config_repo(),
    )
    resolved = resolver.resolve(
        LabelProfileResolutionContext(
            client_id=CLIENT_ID,
            client_supplier_id=SUPPLIER_ID,
            aisle=aisle,
        )
    )
    return {
        "item": {
            "source": resolved.item.source.value,
            "resolution_source": resolved.item.resolution_source,
            "extraction_profile_id": resolved.item.extraction_profile_id,
            "extraction_profile_version": resolved.item.extraction_profile_version,
        },
        "position": {
            "source": resolved.position.source.value,
            "resolution_source": resolved.position.resolution_source,
            "extraction_profile_id": resolved.position.extraction_profile_id,
            "extraction_profile_version": resolved.position.extraction_profile_version,
        },
        "ok": (
            resolved.item.source.value == "SUPPLIER"
            and resolved.position.source.value == "SUPPLIER"
            and resolved.item.resolution_source == "CLIENT_SUPPLIER"
            and resolved.position.resolution_source == "CLIENT_SUPPLIER"
            and bool(resolved.item.extraction_profile_id)
            and bool(resolved.position.extraction_profile_id)
        ),
    }


def verify_payloads() -> dict:
    from src.application.use_cases.suppliers.test_label_recognition_code import (
        LabelRecognitionCodeTestCommand,
    )
    from src.domain.label_profiles.kinds import LabelKind

    c = _container()
    tester = c.get_test_label_recognition_code_use_case()
    profile_repo = c.get_supplier_extraction_profile_repo()
    active_item = profile_repo.get_active_by_kind(CLIENT_ID, SUPPLIER_ID, LabelKind.ITEM)
    active_pos = profile_repo.get_active_by_kind(CLIENT_ID, SUPPLIER_ID, LabelKind.POSITION)
    if active_item is None or active_pos is None:
        raise RuntimeError("ACTIVE profiles missing for payload dry-run")

    item = tester.execute(
        LabelRecognitionCodeTestCommand(
            client_id=CLIENT_ID,
            supplier_id=SUPPLIER_ID,
            label_kind=LabelKind.ITEM,
            raw_payload=ITEM_PAYLOAD,
            symbology="QR",
            profile_id=active_item.id,
        )
    )
    pos = tester.execute(
        LabelRecognitionCodeTestCommand(
            client_id=CLIENT_ID,
            supplier_id=SUPPLIER_ID,
            label_kind=LabelKind.POSITION,
            raw_payload=POSITION_PAYLOAD,
            symbology="QR",
            profile_id=active_pos.id,
        )
    )
    item_fields = item.get("extracted_fields") or {}
    pos_fields = pos.get("extracted_fields") or {}
    return {
        "item": item,
        "position": pos,
        "item_ok": (
            item.get("validation_status") == "VALID"
            and item_fields.get("label_id") == "LPNA000184"
            and item_fields.get("sku") == "SKU773421"
            and item_fields.get("quantity") == 24
        ),
        "position_ok": (
            pos.get("validation_status") == "VALID"
            and pos_fields.get("position_id") == "A04-R-02"
            and pos_fields.get("pallet") == "04"
            and pos_fields.get("side") == "RIGHT"
            and pos_fields.get("level") == "02"
        ),
    }


def start_job() -> str:
    from src.application.dto.access_principal import AccessPrincipal
    from src.application.use_cases.aisles.start_aisle_processing import (
        StartAisleProcessingCommand,
    )

    uc = _build_start_processing_use_case()
    key = f"pruebas-b-correction-{uuid.uuid4()}"
    result = uc.execute(
        StartAisleProcessingCommand(
            inventory_id=INVENTORY_ID,
            aisle_id=AISLE_ID,
            resolve_execution_keys=True,
            requested_processing_mode="CODE_SCAN_ONLY",
            idempotency_key=key,
            principal=AccessPrincipal(
                actor_id="apply_pruebas_b_supplier_correction",
                client_id=CLIENT_ID,
                roles=frozenset({"admin"}),
                is_platform=True,
            ),
        )
    )
    return result.job_id


def verify_job_snapshot(job_id: str) -> dict:
    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient

    client = SqlServerClient(load_settings().require_sqlserver_connection_string())
    with client.cursor() as cur:
        cur.execute(
            """
            SELECT CAST(engine_params_json AS NVARCHAR(MAX))
            FROM inventory_jobs WHERE id = ?
            """,
            (job_id,),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError(f"job not found: {job_id}")
    engine = json.loads(row[0])
    ident = engine.get("identification_execution") or {}
    lp = ident.get("label_profiles") or {}
    item = lp.get("item") or {}
    pos = lp.get("position") or {}

    def _kind_ok(kind: dict) -> bool:
        return (
            kind.get("source") == "SUPPLIER"
            and kind.get("extraction_profile_id")
            and kind.get("extraction_profile_version") is not None
            and isinstance(kind.get("configuration"), dict)
        )

    return {
        "job_id": job_id,
        "item": {
            "source": item.get("source"),
            "profile_id": item.get("extraction_profile_id"),
            "profile_version": item.get("extraction_profile_version"),
            "has_configuration": isinstance(item.get("configuration"), dict),
        },
        "position": {
            "source": pos.get("source"),
            "profile_id": pos.get("extraction_profile_id"),
            "profile_version": pos.get("extraction_profile_version"),
            "has_configuration": isinstance(pos.get("configuration"), dict),
        },
        "ok": _kind_ok(item) and _kind_ok(pos),
    }


def wait_for_job(job_id: str, *, timeout_sec: int = 120) -> dict:
    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient

    client = SqlServerClient(load_settings().require_sqlserver_connection_string())
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        with client.cursor() as cur:
            cur.execute(
                """
                SELECT status,
                       CAST(result_json AS NVARCHAR(MAX)),
                       failure_code
                FROM inventory_jobs WHERE id = ?
                """,
                (job_id,),
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError(f"job not found: {job_id}")
        status, result_raw, failure = row[0], row[1], row[2]
        if status in ("succeeded", "failed", "cancelled"):
            result = json.loads(result_raw) if result_raw else {}
            return {"status": status, "failure_code": failure, "result": result}
        time.sleep(2)
    raise TimeoutError(f"job {job_id} did not finish within {timeout_sec}s")


def verify_job_results(job_id: str) -> dict:
    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient

    client = SqlServerClient(load_settings().require_sqlserver_connection_string())
    out: dict = {"asset_states": [], "events": []}
    with client.cursor() as cur:
        cur.execute(
            """
            SELECT asset_id, status, error_code
            FROM job_asset_processing_states WHERE job_id = ?
            ORDER BY asset_id
            """,
            (job_id,),
        )
        out["asset_states"] = [
            {"asset_id": str(r[0]), "status": r[1], "error_code": r[2]} for r in cur.fetchall()
        ]
        cur.execute(
            """
            SELECT event_type, asset_id, error_code,
                   CAST(metadata_json AS NVARCHAR(MAX))
            FROM processing_events
            WHERE job_id = ? AND event_type LIKE 'code_scan.%'
            ORDER BY created_at
            """,
            (job_id,),
        )
        out["events"] = [
            {
                "event_type": r[0],
                "asset_id": str(r[1]) if r[1] else None,
                "error_code": r[2],
                "metadata": json.loads(r[3]) if r[3] else {},
            }
            for r in cur.fetchall()
        ]
        cur.execute(
            """
            SELECT COUNT(*) FROM positions WHERE aisle_id = ?
            """,
            (AISLE_ID,),
        )
        out["positions_count"] = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*) FROM product_records pr
            INNER JOIN positions p ON p.id = pr.position_id
            WHERE p.aisle_id = ?
            """,
            (AISLE_ID,),
        )
        out["product_records_count"] = cur.fetchone()[0]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Pruebas b supplier recognition correction")
    parser.add_argument("--apply", action="store_true", help="Create+activate segmented profiles")
    parser.add_argument("--verify-db", action="store_true")
    parser.add_argument("--verify-resolver", action="store_true")
    parser.add_argument("--verify-payloads", action="store_true")
    parser.add_argument("--start-job", action="store_true")
    parser.add_argument("--wait", action="store_true", help="With --start-job, poll until complete")
    parser.add_argument("--verify-job", metavar="JOB_ID")
    parser.add_argument(
        "--verify-all",
        action="store_true",
        help="verify-db, resolver, payloads (no job)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="apply + all verifications + start job + wait + verify results",
    )
    args = parser.parse_args()

    if not any(
        [
            args.apply,
            args.verify_db,
            args.verify_resolver,
            args.verify_payloads,
            args.start_job,
            args.verify_job,
            args.verify_all,
            args.full,
        ]
    ):
        parser.print_help()
        return 1

    results: dict = {}

    if args.full:
        args.apply = True
        args.verify_all = True
        args.start_job = True
        args.wait = True

    if args.apply:
        print("=== APPLY PROFILES ===")
        results["apply"] = apply_profiles()
        print(json.dumps(results["apply"], indent=2))

    if args.verify_db or args.verify_all:
        print("=== VERIFY DB ===")
        results["db"] = verify_db()
        print(json.dumps(results["db"], indent=2))
        if not results["db"].get("wiring_ok") or not results["db"].get("single_active_per_kind"):
            print("FAIL: DB wiring or ACTIVE profile check", file=sys.stderr)
            return 2

    if args.verify_resolver or args.verify_all:
        print("=== VERIFY RESOLVER ===")
        results["resolver"] = verify_resolver()
        print(json.dumps(results["resolver"], indent=2))
        if not results["resolver"].get("ok"):
            print("FAIL: resolver did not return SUPPLIER for both kinds", file=sys.stderr)
            return 2

    if args.verify_payloads or args.verify_all:
        print("=== VERIFY PAYLOADS ===")
        results["payloads"] = verify_payloads()
        print(json.dumps(results["payloads"], indent=2, default=str))
        if not results["payloads"].get("item_ok") or not results["payloads"].get("position_ok"):
            print("FAIL: payload dry-run", file=sys.stderr)
            return 2

    job_id = args.verify_job
    if args.start_job:
        print("=== START JOB ===")
        job_id = start_job()
        print(f"job_id={job_id}")
        results["job_id"] = job_id
        snap = verify_job_snapshot(job_id)
        results["job_snapshot"] = snap
        print(json.dumps(snap, indent=2))
        if not snap.get("ok"):
            print("FAIL: job snapshot not SUPPLIER with embedded config", file=sys.stderr)
            return 2

    if args.wait and job_id:
        print(f"=== WAIT JOB {job_id} ===")
        results["job_wait"] = wait_for_job(job_id)
        print(json.dumps(results["job_wait"], indent=2, default=str))
        results["job_results"] = verify_job_results(job_id)
        print(json.dumps(results["job_results"], indent=2, default=str))

    print(json.dumps({"status": "OK", "results": results}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

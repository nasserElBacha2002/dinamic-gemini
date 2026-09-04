"""Read-only diagnostic dump for an inventory job (timeline + asset states).

Usage (from repo root, with backend venv / PYTHONPATH):

    python scripts/debug_job.py --job-id <uuid>
    python scripts/debug_job.py --aisle-id <uuid>

Or:

    cd backend && .venv/bin/python ../scripts/debug_job.py --job-id <uuid>

Only SELECT queries. Does not download blobs or print credentials.

Exit codes:
  0 — success
  1 — not found / usage error
  2 — UUID is a different entity than expected (e.g. aisle passed as --job-id)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _validate_uuid(value: str) -> str:
    text = value.strip()
    if not _UUID_RE.match(text):
        raise argparse.ArgumentTypeError(f"invalid UUID: {value!r}")
    UUID(text)  # normalize / raise
    return text


def _parse_meta(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _fmt_ts(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="milliseconds")
    return str(value)


def _ms(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{int(value)} ms"
    except (TypeError, ValueError):
        return str(value)


def _short(uid: Any, n: int = 8) -> str:
    text = str(uid or "")
    return text[:n] if text else "-"


def resolve_uuid_entity(cur, uuid_value: str) -> dict[str, Any]:
    """Classify a UUID against jobs / aisles / inventories / assets (read-only)."""
    found: dict[str, Any] = {"uuid": uuid_value, "kinds": []}

    cur.execute(
        """
        SELECT id, status, target_type, target_id, execution_id, created_at, finished_at
        FROM inventory_jobs WHERE id = ?
        """,
        (uuid_value,),
    )
    job = cur.fetchone()
    if job is not None:
        cols = [c[0] for c in cur.description]
        found["job"] = dict(zip(cols, job))
        found["kinds"].append("job")

    cur.execute(
        "SELECT id, inventory_id, code, status FROM aisles WHERE id = ?",
        (uuid_value,),
    )
    aisle = cur.fetchone()
    if aisle is not None:
        cols = [c[0] for c in cur.description]
        found["aisle"] = dict(zip(cols, aisle))
        found["kinds"].append("aisle")

    cur.execute("SELECT id, name, status FROM inventories WHERE id = ?", (uuid_value,))
    inv = cur.fetchone()
    if inv is not None:
        cols = [c[0] for c in cur.description]
        found["inventory"] = dict(zip(cols, inv))
        found["kinds"].append("inventory")

    cur.execute(
        "SELECT id, aisle_id, storage_key FROM source_assets WHERE id = ?",
        (uuid_value,),
    )
    asset = cur.fetchone()
    if asset is not None:
        cols = [c[0] for c in cur.description]
        found["asset"] = dict(zip(cols, asset))
        found["kinds"].append("asset")

    return found


def fetch_latest_jobs_for_aisle(cur, aisle_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 50))
    cur.execute(
        f"""
        SELECT TOP ({lim}) id, status, identification_mode, execution_strategy,
               created_at, started_at, finished_at, failure_code
        FROM inventory_jobs
        WHERE target_type = 'aisle' AND target_id = ?
        ORDER BY created_at DESC
        """,
        (aisle_id,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def print_aisle_summary(cur, aisle_id: str) -> int:
    cur.execute(
        "SELECT id, inventory_id, code, status FROM aisles WHERE id = ?",
        (aisle_id,),
    )
    row = cur.fetchone()
    if row is None:
        print(f"Aisle not found: {aisle_id}", file=sys.stderr)
        return 1
    cols = [c[0] for c in cur.description]
    aisle = dict(zip(cols, row))
    print("AISLE")
    print(f"  id: {aisle.get('id')}")
    print(f"  inventory_id: {aisle.get('inventory_id')}")
    print(f"  code: {aisle.get('code')}")
    print(f"  status: {aisle.get('status')}")
    jobs = fetch_latest_jobs_for_aisle(cur, aisle_id)
    print(f"\nLATEST JOBS ({len(jobs)})")
    if not jobs:
        print("  (none)")
        return 0
    for j in jobs:
        print(
            f"  {_short(j.get('id'), 36)}  status={j.get('status')} "
            f"mode={j.get('identification_mode')} strategy={j.get('execution_strategy')} "
            f"created={_fmt_ts(j.get('created_at'))} failure={j.get('failure_code') or '-'}"
        )
    print("\nHint: re-run with --job-id <uuid> for full timeline.")
    return 0


def _infer_observability_generation(events: list[dict[str, Any]]) -> str:
    types = {str(e.get("event_type") or "") for e in events}
    metas = [_parse_meta(e.get("metadata_json")) for e in events]
    if any(m.get("observability_generation") == "phase-timed" for m in metas):
        return "phase-timed"
    if "code_scan.decode_started" in types and any(
        m.get("source_load_ms") is not None for m in metas
    ):
        return "phase-timed"
    if any(m.get("timeout_scope") == "decode" for m in metas):
        return "phase-timed"
    if "code_scan.source_load_started" in types or "asset.source_loaded" in types:
        # Older runs may still have source events without decode-budget separation.
        if any(
            m.get("timeout_scope") == "ASSET_WIDE_LEGACY" or m.get("timeout_phase") == "source"
            for m in metas
        ):
            return "legacy"
        if any("source_load_ms" in m for m in metas):
            return "phase-timed"
    return "legacy"


def _print_wrong_entity_as_job(cur, resolved: dict[str, Any], job_id: str) -> int:
    print(f"UUID no corresponde a Job: {job_id}", file=sys.stderr)
    kinds = resolved.get("kinds") or []
    if not kinds:
        print("No encontrado en jobs / aisles / inventories / source_assets.", file=sys.stderr)
        return 1
    if "aisle" in kinds:
        aisle = resolved["aisle"]
        print(f"\nEncontrado:\n  Aisle ID: {aisle.get('id')}", file=sys.stderr)
        print(f"  inventory_id: {aisle.get('inventory_id')}", file=sys.stderr)
        print(f"  code: {aisle.get('code')}", file=sys.stderr)
        jobs = fetch_latest_jobs_for_aisle(cur, str(aisle.get("id")))
        if jobs:
            latest = jobs[0]
            print("\nÚltimo Job del pasillo:", file=sys.stderr)
            print(f"  {latest.get('id')}", file=sys.stderr)
            print(
                f"  status={latest.get('status')} created={_fmt_ts(latest.get('created_at'))}",
                file=sys.stderr,
            )
            print(
                f"\nReintentar: python scripts/debug_job.py --job-id {latest.get('id')}",
                file=sys.stderr,
            )
            print(
                f"O listar pasillo: python scripts/debug_job.py --aisle-id {aisle.get('id')}",
                file=sys.stderr,
            )
        return 2
    if "inventory" in kinds:
        inv = resolved["inventory"]
        print(f"\nEncontrado:\n  Inventory ID: {inv.get('id')}", file=sys.stderr)
        return 2
    if "asset" in kinds:
        asset = resolved["asset"]
        print(f"\nEncontrado:\n  Asset ID: {asset.get('id')}", file=sys.stderr)
        print(f"  aisle_id: {asset.get('aisle_id')}", file=sys.stderr)
        return 2
    return 1


def _print_recognition_trace(
    *,
    ident: dict[str, Any],
    events: list[dict[str, Any]],
    states: list[dict[str, Any]],
) -> None:
    """Print CODE_SCAN profile / payload / validation trace from job snapshot + events."""
    profiles = ident.get("label_profiles") or {}
    if not isinstance(profiles, dict):
        profiles = {}

    def _profile_block(kind: str) -> None:
        block = profiles.get(kind.lower()) or profiles.get(kind) or {}
        if not isinstance(block, dict):
            block = {}
        print(f"\n{kind} PROFILE")
        print(f"  source: {block.get('source') or '-'}")
        print(f"  profile_id: {block.get('profile_id') or block.get('extraction_profile_id') or '-'}")
        print(f"  profile_version: {block.get('profile_version') or block.get('extraction_profile_version') or '-'}")
        cfg = block.get("configuration")
        if isinstance(cfg, dict) and cfg:
            det = cfg.get("deterministic") or {}
            print(f"  payload_structure: {(det.get('payload_structure') if isinstance(det, dict) else None) or '-'}")
            print(f"  required_fields: {cfg.get('required_fields') or '-'}")

    _profile_block("ITEM")
    _profile_block("POSITION")

    wiring_warnings = ident.get("supplier_wiring_warnings")
    if wiring_warnings:
        print("\nWIRING WARNINGS")
        for w in wiring_warnings if isinstance(wiring_warnings, list) else [wiring_warnings]:
            print(f"  - {w}")

    recognition_events = (
        "code_scan.profile_resolved",
        "code_scan.payload_decoded",
        "code_scan.payload_extracted",
        "code_scan.validation_completed",
        "code_scan.symbols_detected",
        "code_scan.decode_completed",
    )
    rec_events = [
        e
        for e in events
        if str(e.get("event_type") or "") in recognition_events
    ]

    by_asset: dict[str, list[dict[str, Any]]] = {}
    for ev in rec_events:
        aid = str(ev.get("asset_id") or "_job")
        by_asset.setdefault(aid, []).append(ev)

    asset_ids = sorted(set(str(s.get("asset_id")) for s in states) | set(by_asset.keys()))
    if not asset_ids:
        asset_ids = ["_job"]

    for aid in asset_ids:
        print(f"\nASSET {aid}")
        asset_events = by_asset.get(aid, [])
        decoded = [e for e in asset_events if e.get("event_type") == "code_scan.payload_decoded"]
        if decoded:
            print("  DECODED")
            for ev in decoded:
                meta = _parse_meta(ev.get("metadata_json"))
                print(f"    symbology={meta.get('symbology') or '-'}")
                raw_hash = meta.get("raw_payload_sha256") or meta.get("raw_payload")
                print(f"    payload={raw_hash or '-'}")
        resolved = [e for e in asset_events if e.get("event_type") == "code_scan.profile_resolved"]
        if resolved:
            print("  PROFILE RESOLVED (runtime)")
            for ev in resolved:
                meta = _parse_meta(ev.get("metadata_json"))
                print(
                    f"    kind={meta.get('label_kind') or '-'} "
                    f"source={meta.get('source') or '-'} "
                    f"id={meta.get('profile_id') or '-'} "
                    f"v={meta.get('profile_version') or '-'}"
                )
        extracted = [e for e in asset_events if e.get("event_type") == "code_scan.payload_extracted"]
        if extracted:
            print("  EXTRACTION")
            for ev in extracted:
                meta = _parse_meta(ev.get("metadata_json"))
                print(f"    structure={meta.get('structure') or '-'} fields={meta.get('fields') or meta}")
        validated = [e for e in asset_events if e.get("event_type") == "code_scan.validation_completed"]
        if validated:
            print("  VALIDATION")
            for ev in validated:
                meta = _parse_meta(ev.get("metadata_json"))
                print(f"    {meta}")
        st = next((s for s in states if str(s.get("asset_id")) == aid), None)
        if st:
            print("  FINAL")
            print(f"    status={st.get('status')} error={st.get('error_code') or '-'}")


def dump_job(cur, job_id: str, *, show_recognition: bool = False) -> int:
    cur.execute(
        """
        SELECT id, status, identification_mode, execution_strategy, execution_id,
               target_type, target_id, attempt_count, failure_code, failure_message,
               error_message, provider_name, model_name,
               CAST(engine_params_json AS NVARCHAR(MAX)) AS engine_params_json,
               CAST(result_json AS NVARCHAR(MAX)) AS result_json,
               created_at, started_at, finished_at
        FROM inventory_jobs
        WHERE id = ?
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if row is None:
        return -1  # signal caller to resolve entity
    cols = [c[0] for c in cur.description]
    job = dict(zip(cols, row))

    inventory_id = None
    aisle_id = None
    if str(job.get("target_type") or "").lower() == "aisle":
        aisle_id = job.get("target_id")
        cur.execute("SELECT inventory_id FROM aisles WHERE id = ?", (aisle_id,))
        inv_row = cur.fetchone()
        if inv_row is not None:
            inventory_id = inv_row[0]

    print("JOB")
    print(f"  id: {job_id}")
    print(f"  inventory_id: {inventory_id or '-'}")
    print(f"  aisle_id: {aisle_id or '-'}")
    print(f"  status: {job.get('status')}")
    print(f"  identification_mode: {job.get('identification_mode')}")
    print(f"  execution_strategy: {job.get('execution_strategy')}")
    print(f"  execution_id: {job.get('execution_id') or '-'}")
    print(f"  attempt_count: {job.get('attempt_count')}")
    print(f"  failure_code: {job.get('failure_code')}")
    print(f"  provider/model: {job.get('provider_name')} / {job.get('model_name')}")

    engine = _parse_meta(job.get("engine_params_json"))
    ident = engine.get("identification_execution") or {}
    if isinstance(ident, dict):
        print(f"  processing_mode: {ident.get('processing_mode')}")
        print(f"  requested_mode: {ident.get('requested_mode')}")
        fb = ident.get("external_fallback") or {}
        if isinstance(fb, dict):
            print(f"  fallback_enabled: {fb.get('fallback_enabled')}")

    result = _parse_meta(job.get("result_json"))
    if result:
        print(f"  result.asset_progress: {result.get('asset_progress')}")
        print(f"  result.code_scan_outcome: {result.get('code_scan_outcome')}")

    cur.execute(
        """
        SELECT asset_id, status, attempt_count, duration_ms, error_code, error_message,
               last_strategy, started_at, finished_at, execution_scope, updated_at
        FROM job_asset_processing_states
        WHERE job_id = ?
        ORDER BY started_at, asset_id
        """,
        (job_id,),
    )
    state_cols = [c[0] for c in cur.description]
    states = [dict(zip(state_cols, r)) for r in cur.fetchall()]

    cur.execute(
        """
        SELECT created_at, event_type, asset_id, strategy, severity, error_code,
               message, duration_ms, CAST(metadata_json AS NVARCHAR(MAX)) AS metadata_json
        FROM processing_events
        WHERE job_id = ?
        ORDER BY created_at, id
        """,
        (job_id,),
    )
    ev_cols = [c[0] for c in cur.description]
    events = [dict(zip(ev_cols, r)) for r in cur.fetchall()]

    gen = _infer_observability_generation(events)
    print(f"\nOBSERVABILITY")
    print(f"  observability_generation: {gen}")
    if gen == "legacy":
        print("  note: CODE_SCAN_TIMEOUT may reflect ASSET_WIDE_LEGACY budget (pre source_load fix)")
    else:
        print("  decode_budget_started_after_source_load: true (inferred from phase events)")

    if show_recognition and isinstance(ident, dict):
        print("\nRECOGNITION TRACE")
        _print_recognition_trace(ident=ident, events=events, states=states)

    # Per-asset phase timings from events
    by_asset: dict[str, dict[str, Any]] = {}
    for ev in events:
        aid = str(ev.get("asset_id") or "")
        if not aid:
            continue
        slot = by_asset.setdefault(aid, {})
        meta = _parse_meta(ev.get("metadata_json"))
        et = str(ev.get("event_type") or "")
        if et in {"asset.source_loaded", "code_scan.source_load_started"} or "source_load" in et:
            if meta.get("source_load_ms") is not None:
                slot["source_load_ms"] = meta.get("source_load_ms")
            if meta.get("storage_fetch_ms") is not None:
                slot["storage_fetch_ms"] = meta.get("storage_fetch_ms")
            if meta.get("storage_backend"):
                slot["storage_backend"] = meta.get("storage_backend")
        if "decode" in et or et.endswith("decode_completed") or et == "code_scan.decode_started":
            for k in ("decode_ms", "decode_elapsed_ms", "prepare_ms", "configured_budget_ms"):
                if meta.get(k) is not None:
                    slot[k] = meta.get(k)
        if et == "asset.storage_fetch_slow":
            slot["storage_slow"] = True
        if ev.get("error_code") == "CODE_SCAN_TIMEOUT":
            slot["timeout"] = True
            if meta.get("timeout_scope"):
                slot["timeout_scope"] = meta.get("timeout_scope")
            elif gen == "legacy":
                slot["timeout_scope"] = "ASSET_WIDE_LEGACY"

    print(f"\nASSETS ({len(states)})")
    for st in states:
        aid = str(st.get("asset_id"))
        timings = by_asset.get(aid, {})
        print(f"  asset {aid}")
        print(
            f"    status={st.get('status')} error={st.get('error_code')} "
            f"duration={_ms(st.get('duration_ms'))}"
        )
        print(
            f"    storage_load={_ms(timings.get('storage_fetch_ms') or timings.get('source_load_ms'))} "
            f"decode={_ms(timings.get('decode_ms') or timings.get('decode_elapsed_ms'))} "
            f"backend={timings.get('storage_backend') or '-'}"
        )
        if timings.get("storage_slow"):
            print("    storage_fetch_slow=true")
        if timings.get("timeout"):
            print(f"    CODE_SCAN_TIMEOUT timeout_scope={timings.get('timeout_scope') or '-'}")
        if st.get("error_message"):
            print(f"    message={st.get('error_message')}")

    # Fallback summary from engine/result if present
    print("\nFALLBACK")
    fb_enabled = None
    if isinstance(ident, dict):
        fb = ident.get("external_fallback") or {}
        if isinstance(fb, dict):
            fb_enabled = fb.get("fallback_enabled")
    print(f"  eligible/configured: {fb_enabled}")
    fp = result.get("fallback_progress") if isinstance(result, dict) else None
    if isinstance(fp, dict):
        print(f"  invoked: fallback_requested={fp.get('fallback_requested')}")
        print(f"  resolved_external={fp.get('resolved_external')} failed={fp.get('external_failed')}")
    else:
        print("  invoked: (no fallback_progress in result_json)")

    print(f"\nTIMELINE ({len(events)} events)")
    prev: datetime | None = None
    for ev in events:
        ts = ev.get("created_at")
        delta = ""
        if isinstance(ts, datetime) and isinstance(prev, datetime):
            delta = f"  +{int((ts - prev).total_seconds() * 1000)}ms"
        meta = _parse_meta(ev.get("metadata_json"))
        interesting = {
            k: meta[k]
            for k in (
                "byte_length",
                "source_load_ms",
                "storage_fetch_ms",
                "storage_backend",
                "bucket",
                "prepare_ms",
                "decode_ms",
                "decode_elapsed_ms",
                "configured_budget_ms",
                "elapsed_budget_ms",
                "remaining_budget_ms",
                "timeout_phase",
                "timeout_scope",
                "decode_budget_started_after_source_load",
                "observability_generation",
                "retry_status",
                "slow",
                "variants_attempted",
                "symbol_count",
                "status",
            )
            if k in meta
        }
        print(
            f"  {_fmt_ts(ts)}{delta}  {ev.get('event_type')}  "
            f"asset={ev.get('asset_id') or '-'}  err={ev.get('error_code') or '-'}"
        )
        if interesting:
            print(f"    meta={interesting}")
        if ev.get("duration_ms") is not None:
            print(f"    duration_ms={ev.get('duration_ms')}")
        prev = ts if isinstance(ts, datetime) else prev

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only job/aisle timeline debugger (CODE_SCAN / processing events)"
    )
    parser.add_argument("--job-id", type=_validate_uuid, default=None)
    parser.add_argument("--aisle-id", type=_validate_uuid, default=None)
    parser.add_argument(
        "--show-recognition",
        action="store_true",
        help="Print label profile snapshot + CODE_SCAN recognition events per asset",
    )
    args = parser.parse_args(argv)

    if not args.job_id and not args.aisle_id:
        parser.error("provide --job-id and/or --aisle-id")

    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient

    settings = load_settings()
    client = SqlServerClient(settings.require_sqlserver_connection_string())

    with client.cursor() as cur:
        if args.aisle_id and not args.job_id:
            return print_aisle_summary(cur, args.aisle_id)

        assert args.job_id is not None
        rc = dump_job(cur, args.job_id, show_recognition=args.show_recognition)
        if rc == 0:
            return 0
        resolved = resolve_uuid_entity(cur, args.job_id)
        return _print_wrong_entity_as_job(cur, resolved, args.job_id)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Idempotent disposable-lab seed for Dinamic Gemini Phase 4B.

Run from backend venv with lab env loaded::

    cd backend
    set -a && source ../audit/lab/.env.lab && set +a
    .venv/bin/python ../audit/lab/scripts/seed_lab.py

Creates clients A/B, suppliers, inventories, aisles with fixed UUIDs from
``audit/lab/fixtures/manifest.json``. Mints fixture JWTs to
``audit/lab/data/fixture-tokens.json`` (gitignored). Writes ``seed.ok`` on success.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_LAB_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _LAB_ROOT.parents[1]
_BACKEND_ROOT = _REPO_ROOT / "backend"
_MANIFEST_PATH = _LAB_ROOT / "fixtures" / "manifest.json"
_DATA_DIR = _LAB_ROOT / "data"
_TOKENS_PATH = _DATA_DIR / "fixture-tokens.json"
_RUNTIME_MANIFEST_PATH = _DATA_DIR / "runtime-manifest.json"
_SEED_OK_PATH = _DATA_DIR / "seed.ok"

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _die(msg: str) -> None:
    raise SystemExit(f"seed_lab: {msg}")


def _assert_lab_safe() -> None:
    if (os.getenv("LAB_DISPOSABLE_ENABLED") or "").strip().lower() not in {
        "true",
        "1",
        "yes",
    }:
        _die("LAB_DISPOSABLE_ENABLED must be true")
    marker = (os.getenv("LAB_FIXTURE_KEY_MARKER") or "lab-fixture-only").strip()
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        val = (os.getenv(name) or "").strip()
        if val and val != marker:
            _die(f"{name} is set to a non-fixture value")
    if (os.getenv("LAB_LLM_MOCKED") or "").strip().lower() not in {"true", "1", "yes"}:
        _die("LAB_LLM_MOCKED must be true")
    provider = (os.getenv("ARTIFACT_STORAGE_PROVIDER") or "local").strip().lower()
    if provider != "local":
        _die("ARTIFACT_STORAGE_PROVIDER must be local")
    server = (os.getenv("SQLSERVER_SERVER") or "").strip().lower()
    host = server.split(",", 1)[0]
    if host not in {"127.0.0.1", "localhost", "::1"}:
        _die(f"SQLSERVER_SERVER must be loopback (got {server!r})")


def _load_manifest() -> dict:
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        _die("manifest must be a JSON object")
    return raw


def _atomic_write_json(path: Path, payload: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(_DATA_DIR), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _ensure_client(repo, *, client_id: str, name: str, now: datetime) -> None:
    from src.domain.client.entities import Client, ClientStatus

    existing = repo.get_by_id(client_id)
    if existing is not None:
        return
    repo.save(
        Client(
            id=client_id,
            name=name,
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )


def _ensure_supplier(repo, *, supplier_id: str, client_id: str, name: str, now: datetime) -> None:
    from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus

    existing = repo.get_by_id(supplier_id)
    if existing is not None:
        return
    by_name = repo.get_by_client_and_name(client_id, name)
    if by_name is not None:
        return
    repo.save(
        ClientSupplier(
            id=supplier_id,
            client_id=client_id,
            name=name,
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )


def _ensure_inventory(
    repo,
    *,
    inventory_id: str,
    client_id: str,
    name: str,
    now: datetime,
) -> None:
    from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus

    existing = repo.get_by_id(inventory_id)
    if existing is not None:
        return
    repo.save(
        Inventory(
            id=inventory_id,
            name=name,
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
            client_id=client_id,
        )
    )


def _ensure_aisle(
    repo,
    *,
    aisle_id: str,
    inventory_id: str,
    code: str,
    client_supplier_id: str,
    now: datetime,
) -> None:
    from src.domain.aisle.entities import Aisle, AisleStatus

    existing = repo.get_by_id(aisle_id)
    if existing is not None:
        return
    by_code = repo.get_by_inventory_and_code(inventory_id, code)
    if by_code is not None:
        return
    repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inventory_id,
            code=code,
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
            client_supplier_id=client_supplier_id,
        )
    )


def _mint_tokens(manifest: dict, runtime_ids: dict) -> dict:
    from src.auth.security import create_access_token

    secret = (os.getenv("AUTH_TOKEN_SECRET") or "").strip()
    if not secret:
        _die("AUTH_TOKEN_SECRET missing")
    expire_minutes = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES") or "480")
    principals = manifest["principals"]
    clients = runtime_ids["clients"]
    out: dict[str, dict] = {}
    for key, spec in principals.items():
        client_key = spec.get("client_key")
        client_id = clients[client_key] if client_key else None
        token = create_access_token(
            "admin",
            username=spec["username"],
            role=spec["role"],
            principal_id=spec["principal_id"],
            client_id=client_id,
            secret=secret,
            expires_minutes=expire_minutes,
        )
        out[key] = {
            "principal_id": spec["principal_id"],
            "username": spec["username"],
            "role": spec["role"],
            "client_id": client_id,
            "access_token": token,
        }
    return out


def main() -> int:
    _assert_lab_safe()
    manifest = _load_manifest()
    now = datetime.now(timezone.utc)

    from src.runtime.app_container import get_app_container, reset_app_container_for_tests

    reset_app_container_for_tests()
    container = get_app_container()
    client_repo = container.get_client_repo()
    supplier_repo = container.get_client_supplier_repo()
    inventory_repo = container.get_inventory_repo()
    aisle_repo = container.get_aisle_repo()

    runtime = {
        "lab_run_id": (os.getenv("LAB_RUN_ID") or manifest.get("lab_run_id") or "").strip()
        or "LAB_RUN_PLACEHOLDER",
        "clients": {},
        "suppliers": {},
        "inventories": {},
        "aisles": {},
        "seeded_at": now.isoformat(),
    }

    try:
        for key, spec in manifest["clients"].items():
            _ensure_client(client_repo, client_id=spec["id"], name=spec["name"], now=now)
            runtime["clients"][key] = spec["id"]

        for key, spec in manifest["suppliers"].items():
            client_id = runtime["clients"][spec["client_key"]]
            _ensure_supplier(
                supplier_repo,
                supplier_id=spec["id"],
                client_id=client_id,
                name=spec["name"],
                now=now,
            )
            runtime["suppliers"][key] = spec["id"]

        for key, spec in manifest["inventories"].items():
            client_id = runtime["clients"][spec["client_key"]]
            _ensure_inventory(
                inventory_repo,
                inventory_id=spec["id"],
                client_id=client_id,
                name=spec["name"],
                now=now,
            )
            runtime["inventories"][key] = spec["id"]

        for key, spec in manifest["aisles"].items():
            inventory_id = runtime["inventories"][spec["inventory_key"]]
            supplier_id = runtime["suppliers"][spec["supplier_key"]]
            _ensure_aisle(
                aisle_repo,
                aisle_id=spec["id"],
                inventory_id=inventory_id,
                code=spec["code"],
                client_supplier_id=supplier_id,
                now=now,
            )
            runtime["aisles"][key] = spec["id"]

        # Verify all fixed ids present (fail closed on partial write).
        for key, cid in runtime["clients"].items():
            if client_repo.get_by_id(cid) is None:
                _die(f"client missing after seed: {key}")
        for key, iid in runtime["inventories"].items():
            if inventory_repo.get_by_id(iid) is None:
                _die(f"inventory missing after seed: {key}")
        for key, aid in runtime["aisles"].items():
            if aisle_repo.get_by_id(aid) is None:
                _die(f"aisle missing after seed: {key}")

        tokens = _mint_tokens(manifest, runtime)
        _atomic_write_json(_RUNTIME_MANIFEST_PATH, runtime)
        _atomic_write_json(_TOKENS_PATH, {"tokens": tokens, "note": "lab-only; do not commit"})
        _SEED_OK_PATH.write_text(
            json.dumps(
                {
                    "ok": True,
                    "seeded_at": now.isoformat(),
                    "lab_run_id": runtime["lab_run_id"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        # Best-effort: do not leave seed.ok on failure
        try:
            _SEED_OK_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    print(
        "seed_lab: OK "
        f"(clients={len(runtime['clients'])} inventories={len(runtime['inventories'])} "
        f"aisles={len(runtime['aisles'])}; tokens written, redacted)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

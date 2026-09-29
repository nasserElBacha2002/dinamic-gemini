"""Provision a client-scoped Raspberry device token (displayed once)."""

from __future__ import annotations

import argparse
import hashlib
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.domain.raspberry_device.entities import RaspberryDevice, RaspberryDeviceStatus  # noqa: E402
from src.runtime.app_container import get_app_container  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an ACTIVE Raspberry device credential for one client."
    )
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    client_id = args.client_id.strip()
    name = args.name.strip()
    if not client_id:
        parser.error("--client-id must not be blank")
    if not name:
        parser.error("--name must not be blank")
    if len(name) > 200:
        parser.error("--name must be at most 200 characters")

    container = get_app_container()
    if container.get_repository_backend_mode_value() != "sql":
        parser.error("Raspberry device provisioning requires the SQL repository backend")
    if container.get_client_repo().get_by_id(client_id) is None:
        parser.error(f"client not found: {client_id}")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    device = RaspberryDevice(
        id=str(uuid4()),
        client_id=client_id,
        name=name,
        token_hash=token_hash,
        status=RaspberryDeviceStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
    )
    container.get_raspberry_device_repo().create(device)

    print(f"Device created: {device.id}")
    print("Copy this token now. It will not be shown again.")
    print(f"X-Device-Token: {token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
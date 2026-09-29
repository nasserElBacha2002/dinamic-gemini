"""SQL Server persistence for Raspberry device credentials."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.errors import RepositoryRowMappingError
from src.application.ports.raspberry_device_repository import RaspberryDeviceRepository
from src.database.sqlserver import SqlServerClient
from src.domain.raspberry_device.entities import RaspberryDevice, RaspberryDeviceStatus


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _device_from_row(row: object) -> RaspberryDevice:
    device_id = getattr(row, "id", None)
    raw_status = getattr(row, "status", None)
    try:
        status = RaspberryDeviceStatus(str(raw_status))
    except ValueError as exc:
        raise RepositoryRowMappingError(
            f"raspberry_devices invalid status={raw_status!r} id={device_id!r}"
        ) from exc
    created_at = _ensure_utc(getattr(row, "created_at", None))
    if created_at is None:
        raise RepositoryRowMappingError(
            f"raspberry_devices row missing created_at id={device_id!r}"
        )
    return RaspberryDevice(
        id=str(device_id),
        client_id=str(getattr(row, "client_id")),
        name=str(getattr(row, "name", None) or ""),
        token_hash=str(getattr(row, "token_hash", None) or ""),
        status=status,
        created_at=created_at,
        last_used_at=_ensure_utc(getattr(row, "last_used_at", None)),
    )


_DEVICE_COLUMNS = "id, client_id, name, token_hash, status, created_at, last_used_at"


class SqlRaspberryDeviceRepository(RaspberryDeviceRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def create(self, device: RaspberryDevice) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dbo.raspberry_devices (
                    id, client_id, name, token_hash, status, created_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device.id,
                    device.client_id,
                    device.name,
                    device.token_hash,
                    device.status.value,
                    _ensure_utc(device.created_at),
                    _ensure_utc(device.last_used_at),
                ),
            )

    def get_by_token_hash(self, token_hash: str) -> RaspberryDevice | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_DEVICE_COLUMNS} FROM dbo.raspberry_devices WHERE token_hash = ?",
                (token_hash,),
            )
            row = cur.fetchone()
        return _device_from_row(row) if row else None

    def update_last_used_at(self, device_id: str, used_at: datetime) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                "UPDATE dbo.raspberry_devices SET last_used_at = ? WHERE id = ?",
                (_ensure_utc(used_at), device_id),
            )

    def set_status(self, device_id: str, status: RaspberryDeviceStatus) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                "UPDATE dbo.raspberry_devices SET status = ? WHERE id = ?",
                (status.value, device_id),
            )
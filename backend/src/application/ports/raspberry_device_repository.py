"""Persistence port for Raspberry device credentials."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.raspberry_device.entities import RaspberryDevice, RaspberryDeviceStatus


class RaspberryDeviceRepository(Protocol):
    def create(self, device: RaspberryDevice) -> None: ...

    def get_by_token_hash(self, token_hash: str) -> RaspberryDevice | None: ...

    def update_last_used_at(self, device_id: str, used_at: datetime) -> None: ...

    def set_status(self, device_id: str, status: RaspberryDeviceStatus) -> None: ...
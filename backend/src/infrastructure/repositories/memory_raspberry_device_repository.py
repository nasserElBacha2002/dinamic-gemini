"""In-memory Raspberry device repository."""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime

from src.application.ports.raspberry_device_repository import RaspberryDeviceRepository
from src.domain.raspberry_device.entities import RaspberryDevice, RaspberryDeviceStatus


class MemoryRaspberryDeviceRepository(RaspberryDeviceRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, RaspberryDevice] = {}
        self._id_by_token_hash: dict[str, str] = {}
        self._lock = threading.Lock()

    def create(self, device: RaspberryDevice) -> None:
        with self._lock:
            if device.id in self._by_id:
                raise ValueError("Raspberry device id already exists")
            if device.token_hash in self._id_by_token_hash:
                raise ValueError("Raspberry device token hash already exists")
            self._by_id[device.id] = device
            self._id_by_token_hash[device.token_hash] = device.id

    def get_by_token_hash(self, token_hash: str) -> RaspberryDevice | None:
        with self._lock:
            device_id = self._id_by_token_hash.get(token_hash)
            return self._by_id.get(device_id) if device_id is not None else None

    def update_last_used_at(self, device_id: str, used_at: datetime) -> None:
        with self._lock:
            device = self._by_id.get(device_id)
            if device is not None:
                self._by_id[device_id] = replace(device, last_used_at=used_at)

    def set_status(self, device_id: str, status: RaspberryDeviceStatus) -> None:
        with self._lock:
            device = self._by_id.get(device_id)
            if device is not None:
                self._by_id[device_id] = replace(device, status=status)
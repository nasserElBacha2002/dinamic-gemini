"""Validation and query helpers for multi-client offline recognition snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

SUPPORTED_SCHEMA_VERSION = 1
VALID_SOURCES = {"DINAMIC", "SUPPLIER"}
VALID_LABEL_KINDS = {"ITEM", "POSITION"}


class SnapshotValidationError(ValueError):
    """Raised when a downloaded or persisted snapshot violates the local contract."""


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _source(value: Any, field: str) -> str:
    source = _required_string(value, field)
    if source not in VALID_SOURCES:
        raise SnapshotValidationError(
            f"{field} has unsupported value: {source}"
        )
    return source


def _validate_generated_at(value: Any) -> str:
    generated_at = _required_string(value, "generated_at")

    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotValidationError(
            "generated_at must be ISO-8601"
        ) from exc

    return generated_at


@dataclass(frozen=True)
class SupplierConfig:
    client_supplier_id: str
    name: str
    item_source: str
    position_source: str

    @classmethod
    def from_dict(cls, data: Any) -> "SupplierConfig":
        if not isinstance(data, dict):
            raise SnapshotValidationError("supplier must be an object")

        return cls(
            client_supplier_id=_required_string(
                data.get("client_supplier_id"),
                "supplier.client_supplier_id",
            ),
            name=_required_string(
                data.get("name"),
                "supplier.name",
            ),
            item_source=_source(
                data.get("item_source"),
                "supplier.item_source",
            ),
            position_source=_source(
                data.get("position_source"),
                "supplier.position_source",
            ),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "client_supplier_id": self.client_supplier_id,
            "name": self.name,
            "item_source": self.item_source,
            "position_source": self.position_source,
        }


@dataclass(frozen=True)
class RecognitionProfile:
    client_supplier_id: str
    label_kind: str
    source: str
    profile_id: str
    profile_version: int
    configuration_schema_version: int
    recognition_mode: str | None
    semantic_type: str | None
    configuration: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> "RecognitionProfile":
        if not isinstance(data, dict):
            raise SnapshotValidationError("profile must be an object")

        kind = _required_string(
            data.get("label_kind"),
            "profile.label_kind",
        )
        if kind not in VALID_LABEL_KINDS:
            raise SnapshotValidationError(
                f"profile.label_kind has unsupported value: {kind}"
            )

        source = _required_string(
            data.get("source"),
            "profile.source",
        )
        if source != "SUPPLIER":
            raise SnapshotValidationError(
                "profile.source must be SUPPLIER"
            )

        version = data.get("profile_version")
        schema_version = data.get("configuration_schema_version")

        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version < 1
        ):
            raise SnapshotValidationError(
                "profile.profile_version must be a positive integer"
            )

        if (
            not isinstance(schema_version, int)
            or isinstance(schema_version, bool)
            or schema_version < 1
        ):
            raise SnapshotValidationError(
                "profile.configuration_schema_version must be a positive integer"
            )

        configuration = data.get("configuration")
        if not isinstance(configuration, dict):
            raise SnapshotValidationError(
                "profile.configuration must be an object"
            )

        recognition_mode = data.get("recognition_mode")
        semantic_type = data.get("semantic_type")

        if recognition_mode is not None and not isinstance(
            recognition_mode,
            str,
        ):
            raise SnapshotValidationError(
                "profile.recognition_mode must be a string or null"
            )

        if semantic_type is not None and not isinstance(
            semantic_type,
            str,
        ):
            raise SnapshotValidationError(
                "profile.semantic_type must be a string or null"
            )

        return cls(
            client_supplier_id=_required_string(
                data.get("client_supplier_id"),
                "profile.client_supplier_id",
            ),
            label_kind=kind,
            source=source,
            profile_id=_required_string(
                data.get("profile_id"),
                "profile.profile_id",
            ),
            profile_version=version,
            configuration_schema_version=schema_version,
            recognition_mode=recognition_mode,
            semantic_type=semantic_type,
            configuration=configuration,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "client_supplier_id": self.client_supplier_id,
            "label_kind": self.label_kind,
            "source": self.source,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "configuration_schema_version": (
                self.configuration_schema_version
            ),
            "recognition_mode": self.recognition_mode,
            "semantic_type": self.semantic_type,
            "configuration": self.configuration,
        }


def _validate_supplier_configuration(
    suppliers: tuple[SupplierConfig, ...],
    profiles: tuple[RecognitionProfile, ...],
    *,
    client_id: str,
) -> None:
    supplier_ids = {
        supplier.client_supplier_id
        for supplier in suppliers
    }

    if len(supplier_ids) != len(suppliers):
        raise SnapshotValidationError(
            f"duplicate client_supplier_id in client {client_id}"
        )

    profile_keys: set[tuple[str, str]] = set()

    for profile in profiles:
        if profile.client_supplier_id not in supplier_ids:
            raise SnapshotValidationError(
                f"profile references supplier not present in client {client_id}"
            )

        key = (
            profile.client_supplier_id,
            profile.label_kind,
        )

        if key in profile_keys:
            raise SnapshotValidationError(
                f"duplicate supplier/label_kind profile in client {client_id}"
            )

        profile_keys.add(key)

    for supplier in suppliers:
        for kind, source in (
            ("ITEM", supplier.item_source),
            ("POSITION", supplier.position_source),
        ):
            if (
                source == "SUPPLIER"
                and (
                    supplier.client_supplier_id,
                    kind,
                )
                not in profile_keys
            ):
                raise SnapshotValidationError(
                    f"supplier {supplier.client_supplier_id} "
                    f"requires missing {kind} profile"
                )


@dataclass(frozen=True)
class ClientRecognitionConfig:
    client_id: str
    name: str
    bundle_revision: str
    suppliers: tuple[SupplierConfig, ...]
    profiles: tuple[RecognitionProfile, ...]

    @classmethod
    def from_dict(cls, data: Any) -> "ClientRecognitionConfig":
        if not isinstance(data, dict):
            raise SnapshotValidationError(
                "client recognition config must be an object"
            )

        client_id = _required_string(
            data.get("client_id"),
            "client.client_id",
        )

        raw_suppliers = data.get("suppliers")
        raw_profiles = data.get("profiles")

        if not isinstance(raw_suppliers, list):
            raise SnapshotValidationError(
                f"client {client_id} suppliers must be an array"
            )

        if not isinstance(raw_profiles, list):
            raise SnapshotValidationError(
                f"client {client_id} profiles must be an array"
            )

        suppliers = tuple(
            SupplierConfig.from_dict(row)
            for row in raw_suppliers
        )
        profiles = tuple(
            RecognitionProfile.from_dict(row)
            for row in raw_profiles
        )

        _validate_supplier_configuration(
            suppliers,
            profiles,
            client_id=client_id,
        )

        return cls(
            client_id=client_id,
            name=_required_string(
                data.get("name"),
                "client.name",
            ),
            bundle_revision=_required_string(
                data.get("bundle_revision"),
                "client.bundle_revision",
            ),
            suppliers=suppliers,
            profiles=profiles,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "name": self.name,
            "suppliers": [
                supplier.as_dict()
                for supplier in self.suppliers
            ],
            "profiles": [
                profile.as_dict()
                for profile in self.profiles
            ],
            "bundle_revision": self.bundle_revision,
        }

    def supplier(
        self,
        supplier_id: str,
    ) -> SupplierConfig | None:
        return next(
            (
                supplier
                for supplier in self.suppliers
                if supplier.client_supplier_id == supplier_id
            ),
            None,
        )

    def profile(
        self,
        supplier_id: str,
        label_kind: str,
    ) -> RecognitionProfile | None:
        return next(
            (
                profile
                for profile in self.profiles
                if profile.client_supplier_id == supplier_id
                and profile.label_kind == label_kind
            ),
            None,
        )


@dataclass(frozen=True)
class RecognitionSnapshot:
    bundle_schema_version: int
    generated_at: str
    bundle_revision: str
    clients: tuple[ClientRecognitionConfig, ...]

    @classmethod
    def from_dict(cls, data: Any) -> "RecognitionSnapshot":
        if not isinstance(data, dict):
            raise SnapshotValidationError(
                "snapshot must be an object"
            )

        schema_version = data.get("bundle_schema_version")

        if schema_version != SUPPORTED_SCHEMA_VERSION:
            raise SnapshotValidationError(
                "unsupported bundle_schema_version: "
                f"{schema_version}; expected {SUPPORTED_SCHEMA_VERSION}"
            )

        generated_at = _validate_generated_at(
            data.get("generated_at")
        )

        raw_clients = data.get("clients")
        if not isinstance(raw_clients, list):
            raise SnapshotValidationError(
                "clients must be an array"
            )

        clients = tuple(
            ClientRecognitionConfig.from_dict(row)
            for row in raw_clients
        )

        client_ids = {
            client.client_id
            for client in clients
        }

        if len(client_ids) != len(clients):
            raise SnapshotValidationError(
                "duplicate client_id in snapshot"
            )

        return cls(
            bundle_schema_version=schema_version,
            generated_at=generated_at,
            bundle_revision=_required_string(
                data.get("bundle_revision"),
                "bundle_revision",
            ),
            clients=clients,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_schema_version": self.bundle_schema_version,
            "generated_at": self.generated_at,
            "clients": [
                client.as_dict()
                for client in self.clients
            ],
            "bundle_revision": self.bundle_revision,
        }

    def client(
        self,
        client_id: str,
    ) -> ClientRecognitionConfig | None:
        return next(
            (
                client
                for client in self.clients
                if client.client_id == client_id
            ),
            None,
        )
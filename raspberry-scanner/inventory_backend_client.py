"""HTTP client for v3 inventory package preview/confirm (stdlib only)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


class InventoryBackendClientError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(message)


@dataclass(frozen=True)
class InventoryBackendClientConfig:
    base_url: str
    bearer_token: str
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class PackageApiResponse:
    raw: dict[str, Any]
    package_id: str
    export_id: str
    inventory_id: str
    status: str
    duplicate: bool


def inventory_backend_client_from_environment() -> InventoryBackendClientConfig:
    base_url = (os.environ.get("DINAMIC_BACKEND_URL") or "").strip().rstrip("/")
    bearer_token = (
        os.environ.get("DINAMIC_BACKEND_BEARER_TOKEN")
        or os.environ.get("DINAMIC_BACKEND_TOKEN")
        or ""
    ).strip()
    if not base_url:
        raise InventoryBackendClientError(
            "BACKEND_NOT_CONFIGURED",
            "DINAMIC_BACKEND_URL is required for package upload",
        )
    if not bearer_token:
        raise InventoryBackendClientError(
            "BACKEND_AUTH_NOT_CONFIGURED",
            "DINAMIC_BACKEND_BEARER_TOKEN is required for package upload",
        )
    timeout = float(os.environ.get("DINAMIC_BACKEND_TIMEOUT_SEC", "60"))
    return InventoryBackendClientConfig(
        base_url=base_url,
        bearer_token=bearer_token,
        timeout_seconds=max(1.0, timeout),
    )


class InventoryBackendClient:
    def __init__(self, config: InventoryBackendClientConfig) -> None:
        self._config = config

    def preview_local_inventory_package(
        self,
        *,
        inventory_id: str,
        zip_bytes: bytes,
        file_name: str,
    ) -> PackageApiResponse:
        url = (
            f"{self._config.base_url}/api/v3/inventories/"
            f"{urllib.parse.quote(inventory_id, safe='')}"
            f"/local-inventory-packages/preview"
        )
        body, content_type = _multipart_zip_body(zip_bytes, file_name)
        return self._post(url, body=body, content_type=content_type)

    def confirm_local_inventory_package(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str = "SKIP",
    ) -> PackageApiResponse:
        url = (
            f"{self._config.base_url}/api/v3/inventories/"
            f"{urllib.parse.quote(inventory_id, safe='')}"
            f"/local-inventory-packages/confirm"
        )
        payload = {
            "export_id": export_id,
            "conflict_policy": conflict_policy,
        }
        return self._post(
            url,
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )

    def _post(
        self,
        url: str,
        *,
        body: bytes,
        content_type: str,
    ) -> PackageApiResponse:
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._config.bearer_token}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._config.timeout_seconds,
            ) as response:
                raw_bytes = response.read()
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError):
                raise InventoryBackendClientError(
                    "BACKEND_TIMEOUT",
                    "backend request timed out",
                ) from exc
            raise InventoryBackendClientError(
                "BACKEND_UNAVAILABLE",
                f"backend unavailable: {reason}",
            ) from exc
        except TimeoutError as exc:
            raise InventoryBackendClientError(
                "BACKEND_TIMEOUT",
                "backend request timed out",
            ) from exc

        if status < 200 or status >= 300:
            raise InventoryBackendClientError(
                "BACKEND_HTTP_ERROR",
                f"unexpected HTTP status {status}",
                http_status=status,
            )
        try:
            raw = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InventoryBackendClientError(
                "BACKEND_INVALID_JSON",
                "backend returned invalid JSON",
            ) from exc
        if not isinstance(raw, dict):
            raise InventoryBackendClientError(
                "BACKEND_INVALID_JSON",
                "backend response must be a JSON object",
            )
        return _parse_package_response(raw)


def _parse_package_response(raw: dict[str, Any]) -> PackageApiResponse:
    export_id = str(raw.get("export_id") or "").strip()
    package_id = str(raw.get("package_id") or "").strip()
    inventory_id = str(raw.get("inventory_id") or "").strip()
    status = str(raw.get("status") or "").strip().upper()
    if not export_id or not package_id or not inventory_id:
        raise InventoryBackendClientError(
            "BACKEND_INVALID_PACKAGE_RESPONSE",
            "preview/confirm response missing required fields",
        )
    duplicate = bool(raw.get("duplicate"))
    return PackageApiResponse(
        raw=raw,
        package_id=package_id,
        export_id=export_id,
        inventory_id=inventory_id,
        status=status,
        duplicate=duplicate,
    )


def _http_error(exc: urllib.error.HTTPError) -> InventoryBackendClientError:
    body = exc.read() if exc.fp is not None else b""
    code = "BACKEND_HTTP_ERROR"
    message = f"HTTP {exc.code}"
    if exc.code in {401, 403}:
        code = "BACKEND_AUTH_FORBIDDEN"
    try:
        payload = json.loads(body.decode("utf-8"))
        if isinstance(payload, dict):
            api_code = payload.get("code") or payload.get("error_code")
            detail = payload.get("detail")
            if isinstance(api_code, str) and api_code.strip():
                code = api_code.strip()
            if isinstance(detail, str) and detail.strip():
                message = detail.strip()
            elif detail is not None:
                message = str(detail)
    except (UnicodeDecodeError, json.JSONDecodeError):
        if body:
            message = body.decode("utf-8", errors="replace")[:500]
    return InventoryBackendClientError(code, message, http_status=exc.code)


def _multipart_zip_body(zip_bytes: bytes, file_name: str) -> tuple[bytes, str]:
    boundary = f"dinamic-raspberry-{uuid.uuid4().hex}"
    safe_name = file_name.replace('"', "_")
    parts: list[bytes] = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
            f"Content-Type: application/zip\r\n\r\n"
        ).encode(),
        zip_bytes,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    content_type = f"multipart/form-data; boundary={boundary}"
    return b"".join(parts), content_type

"""Feature-flag matrix: CSV / ZIP package / TXT routes are independently gated."""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import require_inventory_client_scope
from src.api.server import app
from src.application.dto.access_principal import AccessPrincipal
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.config import reload_settings
from src.domain.local_inventory_package.errors import PACKAGE_IMPORT_DISABLED

client = TestClient(app)

CSV_DISABLED = "LOCAL_CSV_IMPORT_DISABLED"
TXT_DISABLED = "DINAMIC_SCANNER_TXT_IMPORT_DISABLED"


def _auth_override() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="test-user",
        client_id="client-1",
        roles=frozenset({"administrator"}),
        is_platform=True,
    )


@pytest.fixture(autouse=True)
def _route_auth():
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    app.dependency_overrides[require_inventory_client_scope] = _auth_override
    yield
    app.dependency_overrides.pop(require_inventory_client_scope, None)
    app.dependency_overrides.pop(get_current_admin, None)


def _set_flags(
    monkeypatch: pytest.MonkeyPatch,
    *,
    csv: str,
    package: str,
    txt: str,
) -> None:
    monkeypatch.setenv("SERVER_CSV_IMPORT_ENABLED", csv)
    monkeypatch.setenv("SERVER_LOCAL_INVENTORY_PACKAGE_ENABLED", package)
    monkeypatch.setenv("SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED", txt)
    reload_settings()


def _json_code(response) -> str | None:
    if response.status_code == 404:
        body = response.json()
        return body.get("code")
    return None


@pytest.mark.parametrize(
    ("csv", "package", "txt"),
    [
        ("false", "false", "false"),
        ("true", "false", "false"),
        ("false", "true", "false"),
        ("false", "false", "true"),
        ("true", "true", "true"),
    ],
)
def test_import_endpoint_matrix_independent_gates(
    monkeypatch: pytest.MonkeyPatch,
    csv: str,
    package: str,
    txt: str,
) -> None:
    _set_flags(monkeypatch, csv=csv, package=package, txt=txt)
    inv = "inventory-flags"
    csv_resp = client.post(
        f"/api/v3/inventories/{inv}/local-csv-imports/preview",
        files={"file": ("x.csv", BytesIO(b"schema_version\n1\n"), "text/csv")},
    )
    pkg_resp = client.post(
        f"/api/v3/inventories/{inv}/local-inventory-packages/preview",
        files={"file": ("x.zip", BytesIO(b"PK\x03\x04"), "application/zip")},
    )
    txt_resp = client.post(
        f"/api/v3/inventories/{inv}/dinamic-scanner-txt-imports/preview",
        files={"file": ("A1.txt", BytesIO(b"POSITION|P|01|LEFT\n"), "text/plain")},
    )

    if csv == "false":
        assert _json_code(csv_resp) == CSV_DISABLED
    else:
        assert _json_code(csv_resp) != CSV_DISABLED
        assert csv_resp.status_code < 500, csv_resp.text

    if package == "false":
        assert _json_code(pkg_resp) == PACKAGE_IMPORT_DISABLED
    else:
        assert _json_code(pkg_resp) != PACKAGE_IMPORT_DISABLED
        assert pkg_resp.status_code < 500, pkg_resp.text

    if txt == "false":
        assert _json_code(txt_resp) == TXT_DISABLED
    else:
        assert _json_code(txt_resp) != TXT_DISABLED
        assert txt_resp.status_code < 500, txt_resp.text

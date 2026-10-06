import json
import os
from pathlib import Path


def install_test_inventory_context(
    root: Path,
    *,
    inventory_id: str = "inventory-1",
    aisle_code: str = "A1",
    aisle_id: str = "aisle-1",
    client_id: str | None = "client-a",
    extra_aisles: list[tuple[str, str]] | None = None,
) -> Path:
    os.environ["DINAMIC_EXPORT_DIRECTORY"] = str(root / "exports")
    os.environ.pop("DINAMIC_INVENTORY_CONTEXT_PATH", None)
    os.environ.pop("DINAMIC_INVENTORY_CONFIG_PATH", None)
    os.environ.pop("DINAMIC_INVENTORY_ID", None)
    path = root / "inventory-context.json"
    aisles = [{"aisle_id": aisle_id, "aisle_code": aisle_code}]
    for code, row_id in extra_aisles or []:
        aisles.append({"aisle_id": row_id, "aisle_code": code})
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "inventory_id": inventory_id,
        "aisles": aisles,
    }
    if client_id:
        payload["client_id"] = client_id
    path.write_text(
        json.dumps(payload, ensure_ascii=True),
        encoding="utf-8",
    )
    return path

import json
import os
from pathlib import Path


def install_test_inventory_context(
    root: Path,
    *,
    inventory_id: str = "inventory-1",
    aisle_code: str = "A1",
    aisle_id: str = "aisle-1",
    extra_aisles: list[tuple[str, str]] | None = None,
) -> Path:
    path = root / "inventory-context.json"
    aisles = [{"aisle_id": aisle_id, "aisle_code": aisle_code}]
    for code, row_id in extra_aisles or []:
        aisles.append({"aisle_id": row_id, "aisle_code": code})
    path.write_text(
        json.dumps(
            {
                "inventory_id": inventory_id,
                "aisles": aisles,
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    os.environ["DINAMIC_INVENTORY_CONTEXT_PATH"] = str(path)
    return path

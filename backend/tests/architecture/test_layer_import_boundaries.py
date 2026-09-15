"""Architecture import boundaries — domain↛pipeline/api/infra; application↛api."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src"

_FORBIDDEN_DOMAIN = ("src.pipeline", "src.api", "src.infrastructure")
_FORBIDDEN_APPLICATION = ("src.api",)


def _iter_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def _violations(root: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for path in _iter_py_files(root):
        rel = path.relative_to(BACKEND_SRC)
        for mod in _imported_modules(path):
            for prefix in forbidden_prefixes:
                if mod == prefix or mod.startswith(prefix + "."):
                    hits.append(f"{rel}: imports {mod}")
    return hits


def test_domain_does_not_import_pipeline_api_or_infrastructure() -> None:
    hits = _violations(BACKEND_SRC / "domain", _FORBIDDEN_DOMAIN)
    assert hits == [], "Domain layer boundary violations:\n" + "\n".join(hits)


def test_application_does_not_import_api() -> None:
    hits = _violations(BACKEND_SRC / "application", _FORBIDDEN_APPLICATION)
    assert hits == [], "Application→API boundary violations:\n" + "\n".join(hits)


def test_provider_image_manifest_order_key_lives_in_domain() -> None:
    from src.domain.execution_image_manifest import PROVIDER_IMAGE_MANIFEST_ORDER_KEY
    from src.pipeline.services import provider_execution_request as per

    assert PROVIDER_IMAGE_MANIFEST_ORDER_KEY == "provider_image_manifest_order"
    assert per.PROVIDER_IMAGE_MANIFEST_ORDER_KEY is PROVIDER_IMAGE_MANIFEST_ORDER_KEY


def test_llm_cost_snapshot_public_does_not_import_api() -> None:
    path = BACKEND_SRC / "application" / "services" / "llm_cost_snapshot_public.py"
    mods = _imported_modules(path)
    assert not any(m == "src.api" or m.startswith("src.api.") for m in mods)

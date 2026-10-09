"""Regression coverage for Phase 6 layering cleanup and facade simplification."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import src.api.dependencies as public_dependencies
from src.api.deps import imports, infrastructure
from src.application.use_cases.inventories.manage_local_csv_import import ConfirmLocalCsvImport
from src.config import load_settings
from src.runtime import import_composition
from src.runtime.app_container import AppContainer

RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "src" / "runtime"


def _iter_runtime_py_files() -> list[Path]:
    return sorted(path for path in RUNTIME_ROOT.rglob("*.py") if path.name != "__pycache__")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_phase6_confirm_builder_identity_is_neutral_composition() -> None:
    assert (
        public_dependencies.build_confirm_local_csv_import
        is imports.build_confirm_local_csv_import
    )
    assert (
        public_dependencies.build_confirm_local_csv_import
        is import_composition.build_confirm_local_csv_import
    )


def test_phase6_observability_guard_identity_is_infrastructure() -> None:
    assert (
        public_dependencies.get_observability_inventory_guard
        is infrastructure.get_observability_inventory_guard
    )


def test_phase6_facade_has_no_implementation_functions() -> None:
    tree = ast.parse(Path(public_dependencies.__file__).read_text())
    defined = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert defined == []


def test_phase6_app_container_csv_recovery_uses_neutral_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.config as config_module

    monkeypatch.setattr(config_module, "_settings", None)
    container = AppContainer(load_settings())
    recovery_service = container.get_local_csv_import_recovery_service()

    assert recovery_service is container.get_local_csv_import_recovery_service()
    assert isinstance(recovery_service._confirm, ConfirmLocalCsvImport)


def test_phase6_runtime_does_not_import_api_composition() -> None:
    forbidden_prefixes = ("src.api.dependencies", "src.api.deps")
    offenders: list[str] = []
    for path in _iter_runtime_py_files():
        for module in _imported_modules(path):
            if module == "src.api" or module.startswith(forbidden_prefixes):
                offenders.append(f"{path.relative_to(RUNTIME_ROOT.parent.parent)}:{module}")
    assert offenders == []

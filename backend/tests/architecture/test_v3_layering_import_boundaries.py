"""Architecture guardrails (Phase 6) — layering and forbidden imports."""

from __future__ import annotations

from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parents[2] / "src"
_APPLICATION = _BACKEND_SRC / "application"
_DOMAIN = _BACKEND_SRC / "domain"


def _iter_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _file_imports_forbidden(path: Path, needles: tuple[str, ...]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    hits: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for needle in needles:
            if needle in line:
                hits.append(f"{path.relative_to(_BACKEND_SRC)}:{i}: {stripped}")
    return hits


def test_application_does_not_import_fastapi() -> None:
    hits: list[str] = []
    for path in _iter_py_files(_APPLICATION):
        hits.extend(
            _file_imports_forbidden(
                path,
                (
                    "from fastapi",
                    "import fastapi",
                    "from starlette",
                    "import starlette",
                ),
            )
        )
    assert hits == [], "application must not import FastAPI/Starlette:\n" + "\n".join(hits)


def test_domain_does_not_import_infrastructure_or_api() -> None:
    hits: list[str] = []
    for path in _iter_py_files(_DOMAIN):
        hits.extend(
            _file_imports_forbidden(
                path,
                (
                    "from src.infrastructure",
                    "import src.infrastructure",
                    "from src.api",
                    "import src.api",
                    "from src.database",
                    "import src.database",
                ),
            )
        )
    assert hits == [], "domain must not import infrastructure/api/database:\n" + "\n".join(hits)


def test_job_result_uow_protocol_declares_fence_job_lease() -> None:
    from src.application.ports import job_result_unit_of_work as mod

    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "def fence_job_lease" in text


def test_persist_aisle_result_does_not_getattr_fence() -> None:
    path = _APPLICATION / "use_cases" / "pipeline" / "persist_aisle_result.py"
    text = path.read_text(encoding="utf-8")
    assert 'getattr(uow, "fence_job_lease"' not in text
    assert "uow.fence_job_lease(" in text

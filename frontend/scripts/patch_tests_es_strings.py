#!/usr/bin/env python3
"""One-off batch replacements for Spanish-primary UI tests."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

REPLACEMENTS: list[tuple[str, str]] = [
    ("getByRole('button', { name: 'Cancel' })", "getByRole('button', { name: 'Cancelar' })"),
    ('getByRole("button", { name: "Cancel" })', 'getByRole("button", { name: "Cancelar" })'),
    ("getByLabelText(/username/i", "getByLabelText(/usuario|username/i"),
    ("getByLabelText(/password/i", "getByLabelText(/contraseña|password/i"),
    (r"getByText(/login title/i)", r"getByText(/iniciar sesión|login title/i)"),
    (r"getByRole('button', { name: /login/i })", r"getByRole('button', { name: /ingresar|login/i })"),
    (r"getByRole('button', { name: /signing in/i })", r"getByRole('button', { name: /ingresando|signing in/i })"),
    (r"toBe('Authentication failed')", r"toBe('Error de autenticación')"),
    (r"getByText('Valid')", r"getByText('Válida')"),
    (r"getByText('Missing')", r"getByText('Ausente')"),
    (r"getByText('Invalid')", r"getByText('Inválida')"),
    (r"getByText('Unvalidated')", r"getByText('Sin validar')"),
    (r"getByText(/unauthorized title/i)", r"getByText(/acceso restringido|unauthorized title/i)"),
    (
        "screen.getByText(/AI configuration|IA y proveedores/i)",
        "screen.getByText(/Configuración de IA|AI configuration|IA y proveedores/i)",
    ),
    (r"toMatch(/operational/i)", r"toMatch(/operativo|operational/i)"),
    (r"getByText(/Promote body/i)", r"getByText(/promover esta corrida|promote body/i)"),
    (r"getByRole('button', { name: 'Preview' })", r"getByRole('button', { name: /vista previa|preview/i })"),
    (r"getByRole('button', { name: 'Delete' })", r"getByRole('button', { name: /eliminar|delete/i })"),
]

REGEX_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"/load failed\|request failed\|something went wrong\|could not load/i"
        ),
        "/no se pudo cargar|la solicitud falló|ocurrió un error|cargar|load failed|request failed|something went wrong|could not load/i",
    ),
    (
        re.compile(
            r"/something went wrong\|load metrics\|request failed\|unexpected/i"
        ),
        "/ocurrió un error|métricas|something went wrong|load metrics|request failed|unexpected|la solicitud falló/i",
    ),
    (
        re.compile(
            r"/Load results\|something went wrong\|preview failed\|could not complete the operation/i"
        ),
        "/resultados|cargar|ocurrió|something went wrong|preview failed|could not complete|la solicitud falló/i",
    ),
    (
        re.compile(r"/forbidden\|something went wrong\|not allowed\|could not complete/i"),
        "/prohibido|ocurrió|something went wrong|not allowed|could not complete|acceso denegado/i",
    ),
    (
        re.compile(r"/Compare readonly explain\|readonly/i"),
        "/solo lectura|compare readonly|readonly/i",
    ),
    (
        re.compile(r"/open compare/i"),
        "/abrir comparación|open compare/i",
    ),
]


def main() -> None:
    for path in sorted(TESTS.rglob("*.tsx")) + sorted(TESTS.rglob("*.ts")):
        text = path.read_text(encoding="utf-8")
        orig = text
        for a, b in REPLACEMENTS:
            text = text.replace(a, b)
        for pat, repl in REGEX_REPLACEMENTS:
            text = pat.sub(repl, text)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            print("patched", path.relative_to(ROOT))


if __name__ == "__main__":
    main()

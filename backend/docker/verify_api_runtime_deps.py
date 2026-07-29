"""Image build-time verification of ODBC / pyzbar / tesseract (API image)."""

from __future__ import annotations

import pyodbc
import pytesseract
from pyzbar.pyzbar import decode as _pyzbar_decode  # noqa: F401

drivers = {d.strip() for d in pyodbc.drivers() if d.strip()}
required = {"ODBC Driver 18 for SQL Server"}
print("pyodbc OK; ODBC drivers:", sorted(drivers))
if not (drivers & required):
    raise SystemExit(
        "Build verification failed: ODBC Driver 18 for SQL Server not registered. "
        f"Got: {sorted(drivers)}"
    )
print("pyzbar-ok")

_ver = str(pytesseract.get_tesseract_version())
print(f"pytesseract OK; tesseract version={_ver}")
_langs = {x.strip() for x in pytesseract.get_languages(config="") if x.strip()}
if not ({"spa", "eng"} <= _langs):
    raise SystemExit(
        f"Build verification failed: tesseract languages must include spa and eng. Got: {sorted(_langs)}"
    )
print("tesseract spa+eng language packs available for INTERNAL_OCR")

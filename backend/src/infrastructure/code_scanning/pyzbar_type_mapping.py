"""Map pyzbar symbol types to domain CodeType."""

from __future__ import annotations

from src.domain.code_scans.entities import CodeType

_QR_TYPES = frozenset({"QRCODE", "QR_CODE", "MICROQR", "RMQR"})
_BARCODE_TYPES = frozenset(
    {
        "CODE128",
        "CODE39",
        "EAN13",
        "EAN8",
        "UPCA",
        "UPCE",
        "I25",
        "CODABAR",
        "DATABAR",
        "DATABAR_EXP",
        "DATABAR_LIMITED",
    }
)
_DATAMATRIX_TYPES = frozenset({"DATAMATRIX"})


def map_pyzbar_type_name(type_name: str) -> CodeType:
    name = (type_name or "").strip().upper()
    if name in _QR_TYPES:
        return CodeType.QR
    if name in _DATAMATRIX_TYPES:
        return CodeType.DATAMATRIX
    if name in _BARCODE_TYPES:
        return CodeType.BARCODE
    return CodeType.UNKNOWN


def decode_symbol_bytes(data: bytes | None) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")

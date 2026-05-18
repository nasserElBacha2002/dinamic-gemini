"""Package pre-built CSV payloads into a ZIP archive (no business rules)."""

from __future__ import annotations

import io
import zipfile


class ExportZipPackager:
    @staticmethod
    def build_zip(entries: dict[str, str]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path, content in entries.items():
                zf.writestr(path, content.encode("utf-8"))
        return buf.getvalue()

#!/usr/bin/env python3
"""Regenerate nested locale JSON from extracted keys + flat English overrides."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
OVERRIDES_PATH = Path(__file__).resolve().parent / "i18n.overrides.en.json"


def extract_keys() -> list[str]:
    keys: set[str] = set()
    patterns = [
        re.compile(r"""i18n\.t\(\s*['"]([^'"]+)['"]"""),
        re.compile(r"""\bt\(\s*['"]([^'"]+)['"]"""),
        re.compile(r"""i18n\.exists\(\s*['"]([^'"]+)['"]"""),
        # Second argument to resolveApiErrorMessage(..., 'errors.foo')
        re.compile(r"""resolveApiErrorMessage\([^,]+,\s*['"]([^'"]+)['"]"""),
    ]
    errors_literal = re.compile(r"""['"](errors\.[a-z0-9_.]+)['"]""")
    for base in (SRC, TESTS):
        if not base.exists():
            continue
        for p in list(base.rglob("*.tsx")) + list(base.rglob("*.ts")):
            text = p.read_text(encoding="utf-8", errors="ignore")
            for pat in patterns:
                keys.update(pat.findall(text))
            keys.update(errors_literal.findall(text))
    return sorted(k for k in keys if re.match(r"^[a-z][a-z0-9_.]*$", k) and "{{" not in k)


def default_en_value(key: str) -> str:
    last = key.split(".")[-1]
    if last.startswith("breadcrumb_"):
        tail = last[len("breadcrumb_") :]
        s = " ".join(tail.split("_"))
        return s[0].upper() + s[1:] if s else last
    s = " ".join(last.split("_"))
    return s[0].upper() + s[1:] if s else last


def nest(flat: dict[str, str]) -> dict:
    root: dict = {}
    for k, v in flat.items():
        parts = k.split(".")
        d = root
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = v
    return root


def main() -> None:
    keys = extract_keys()
    flat_en = {k: default_en_value(k) for k in keys}
    if OVERRIDES_PATH.is_file():
        extra = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        if not isinstance(extra, dict):
            raise SystemExit("i18n.overrides.en.json must be a flat JSON object")
        flat_en.update({str(k): str(v) for k, v in extra.items()})

    nested_en = nest(flat_en)
    nested_es = json.loads(json.dumps(nested_en))

    out_en = SRC / "i18n" / "locales" / "en" / "translation.json"
    out_es = SRC / "i18n" / "locales" / "es" / "translation.json"
    out_en.parent.mkdir(parents=True, exist_ok=True)
    out_es.parent.mkdir(parents=True, exist_ok=True)
    out_en.write_text(json.dumps(nested_en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_es.write_text(json.dumps(nested_es, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(keys)} keys -> {out_en.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

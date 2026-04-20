#!/usr/bin/env python3
"""Basic i18n health check for frontend.

Checks:
1) Missing static keys used by t()/i18n.t()/i18n.exists().
2) Missing dynamic layout keys from navConfig + shellTopBarCopy.
3) Structural drift between en/es locale trees.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LOCALE_EN = SRC / "i18n" / "locales" / "en" / "translation.json"
LOCALE_ES = SRC / "i18n" / "locales" / "es" / "translation.json"
LAYOUT_DYNAMIC_FILES = [SRC / "layout" / "navConfig.tsx", SRC / "layout" / "shellTopBarCopy.ts"]


def flatten(tree: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for key, value in tree.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out |= flatten(value, dotted)
        else:
            out.add(dotted)
    return out


def extract_static_keys() -> set[str]:
    patterns = [
        re.compile(r"""i18n\.t\(\s*['"]([^'"]+)['"]"""),
        re.compile(r"""\bt\(\s*['"]([^'"]+)['"]"""),
        re.compile(r"""i18n\.exists\(\s*['"]([^'"]+)['"]"""),
    ]
    keys: set[str] = set()
    for path in list(SRC.rglob("*.ts")) + list(SRC.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            keys.update(pattern.findall(text))
    return keys


def extract_layout_dynamic_keys() -> set[str]:
    keys: set[str] = set()
    regex = re.compile(r"""(?:labelKey|titleKey|subtitleKey):\s*['"]([^'"]+)['"]""")
    for path in LAYOUT_DYNAMIC_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        keys.update(regex.findall(text))
    return keys


def main() -> int:
    en = json.loads(LOCALE_EN.read_text(encoding="utf-8"))
    es = json.loads(LOCALE_ES.read_text(encoding="utf-8"))
    en_keys = flatten(en)
    es_keys = flatten(es)
    static_keys = extract_static_keys()
    dynamic_keys = extract_layout_dynamic_keys()
    used_keys = static_keys | dynamic_keys

    missing_en = sorted(k for k in used_keys if k not in en_keys)
    missing_es = sorted(k for k in used_keys if k not in es_keys)
    only_en = sorted(k for k in en_keys if k not in es_keys)
    only_es = sorted(k for k in es_keys if k not in en_keys)

    has_error = False

    if missing_en:
        has_error = True
        print("Missing keys in en:")
        for key in missing_en:
            print(f"  - {key}")
    if missing_es:
        has_error = True
        print("Missing keys in es:")
        for key in missing_es:
            print(f"  - {key}")
    if only_en:
        has_error = True
        print("Keys only in en (structure drift):")
        for key in only_en:
            print(f"  - {key}")
    if only_es:
        has_error = True
        print("Keys only in es (structure drift):")
        for key in only_es:
            print(f"  - {key}")

    if not has_error:
        print("i18n check passed: en/es structures are aligned and all used keys exist.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

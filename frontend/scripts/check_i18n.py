#!/usr/bin/env python3
"""Basic i18n health check for frontend (Spanish locale is authoritative for the running app).

Also notes gaps in ``locales/en/translation.json`` when present — English JSON is kept for
reference/future use and is not loaded at runtime (see ``src/i18n/index.ts``).

Checks:
1) Missing static keys used by t()/i18n.t()/i18n.exists().
2) Missing dynamic layout keys from navConfig + shellTopBarCopy.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LOCALE_ES = SRC / "i18n" / "locales" / "es" / "translation.json"
LOCALE_EN = SRC / "i18n" / "locales" / "en" / "translation.json"
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


def flatten_values(tree: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in tree.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten_values(value, dotted))
        else:
            out[dotted] = str(value)
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
    es = json.loads(LOCALE_ES.read_text(encoding="utf-8"))
    es_keys = flatten(es)
    es_values = flatten_values(es)
    static_keys = extract_static_keys()
    dynamic_keys = extract_layout_dynamic_keys()
    used_keys = static_keys | dynamic_keys

    placeholder_re = re.compile(
        r"""^(?:title|subtitle|label|empty title|empty message|search label|list title|list subtitle|"""
        r"""created date label|visual refs title|compare runs link|not found|"""
        r"""column [a-z ]+|kpi [a-z ]+|filter [a-z ]+|placeholder [a-z ]+)$""",
        re.IGNORECASE,
    )
    suspicious_es = []
    for key in sorted(used_keys):
        es_val = es_values.get(key, "")
        if placeholder_re.match(es_val.strip()):
            suspicious_es.append((key, es_val))

    missing_es = sorted(k for k in used_keys if k not in es_keys)
    extra_es = sorted(k for k in es_keys if k not in used_keys)

    has_error = False

    if missing_es:
        has_error = True
        print("Missing keys in es/translation.json:")
        for key in missing_es:
            print(f"  - {key}")

    if suspicious_es:
        print("Warnings: suspicious placeholder-like values in es:")
        for key, value in suspicious_es[:60]:
            print(f"  - {key}: {value}")
        if len(suspicious_es) > 60:
            print(f"  ... and {len(suspicious_es) - 60} more")

    if extra_es:
        print("Note: keys defined in es but not referenced by static extraction (may be dynamic):")
        for key in extra_es[:40]:
            print(f"  - {key}")
        if len(extra_es) > 40:
            print(f"  ... and {len(extra_es) - 40} more")

    if LOCALE_EN.is_file():
        en = json.loads(LOCALE_EN.read_text(encoding="utf-8"))
        en_keys = flatten(en)
        missing_in_en = sorted(k for k in used_keys if k not in en_keys)
        if missing_in_en:
            print("Note: keys used in app but missing in en/translation.json (reference locale):")
            for key in missing_in_en[:40]:
                print(f"  - {key}")
            if len(missing_in_en) > 40:
                print(f"  ... and {len(missing_in_en) - 40} more")

    if not has_error:
        print("i18n check passed: all used keys exist in es locale.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

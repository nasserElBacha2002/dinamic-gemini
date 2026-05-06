#!/usr/bin/env python3
"""Regenerate locale JSON from extracted keys + flat overrides.

Writes:
- ``src/i18n/locales/es/translation.json`` — full regenerate from keys + ``i18n.overrides.es.json``.
- ``src/i18n/locales/en/translation.json`` — **merge**: keeps existing English strings, adds new
  keys with placeholders, preserves keys no longer referenced (for reference / future use).
  Optional overrides: ``i18n.overrides.en.json``.

The app runtime loads **Spanish only** (see ``src/i18n/index.ts``); English JSON stays in-repo
for documentation, future locales, and parity checks — never delete it.

Run ``scripts/check_i18n.py`` after edits.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
OVERRIDES_ES = Path(__file__).resolve().parent / "i18n.overrides.es.json"
OVERRIDES_EN = Path(__file__).resolve().parent / "i18n.overrides.en.json"
OUT_ES = SRC / "i18n" / "locales" / "es" / "translation.json"
OUT_EN = SRC / "i18n" / "locales" / "en" / "translation.json"


def extract_keys() -> list[str]:
    keys: set[str] = set()
    patterns = [
        re.compile(r"""i18n\.t\(\s*['"]([^'"]+)['"]"""),
        re.compile(r"""\bt\(\s*['"]([^'"]+)['"]"""),
        re.compile(r"""i18n\.exists\(\s*['"]([^'"]+)['"]"""),
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


def flatten_string_values(tree: dict, prefix: str = "") -> dict[str, str]:
    """Leaf string values only (same shape as check_i18n)."""
    out: dict[str, str] = {}
    for key, value in tree.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten_string_values(value, dotted))
        else:
            out[dotted] = str(value)
    return out


def default_placeholder(key: str) -> str:
    """Human-readable placeholder from key tail (review before ship; ES overrides fix Spanish)."""
    last = key.split(".")[-1]
    if last.startswith("breadcrumb_"):
        tail = last[len("breadcrumb_") :]
        s = " ".join(tail.split("_"))
        return (s[0].upper() + s[1:]) if s else last
    s = " ".join(last.split("_"))
    return (s[0].upper() + s[1:]) if s else last


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
    keys_set = set(keys)
    flat_es = {k: default_placeholder(k) for k in keys}
    if OVERRIDES_ES.is_file():
        extra = json.loads(OVERRIDES_ES.read_text(encoding="utf-8"))
        if not isinstance(extra, dict):
            raise SystemExit("i18n.overrides.es.json must be a flat JSON object")
        flat_es.update({str(k): str(v) for k, v in extra.items()})

    nested_es = nest(flat_es)
    OUT_ES.parent.mkdir(parents=True, exist_ok=True)
    OUT_ES.write_text(json.dumps(nested_es, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(keys)} keys -> {OUT_ES.relative_to(ROOT)}")

    flat_old_en: dict[str, str] = {}
    if OUT_EN.is_file():
        existing = json.loads(OUT_EN.read_text(encoding="utf-8"))
        if isinstance(existing, dict):
            flat_old_en = flatten_string_values(existing)

    flat_en: dict[str, str] = {}
    for k in keys_set:
        if k in flat_old_en:
            flat_en[k] = flat_old_en[k]
        else:
            flat_en[k] = default_placeholder(k)
    for k, v in flat_old_en.items():
        if k not in flat_en:
            flat_en[k] = v

    if OVERRIDES_EN.is_file():
        extra_en = json.loads(OVERRIDES_EN.read_text(encoding="utf-8"))
        if not isinstance(extra_en, dict):
            raise SystemExit("i18n.overrides.en.json must be a flat JSON object")
        flat_en.update({str(k): str(v) for k, v in extra_en.items()})

    nested_en = nest(flat_en)
    OUT_EN.parent.mkdir(parents=True, exist_ok=True)
    OUT_EN.write_text(json.dumps(nested_en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(flat_en)} keys -> {OUT_EN.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

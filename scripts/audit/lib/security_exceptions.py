"""Structured security exceptions loader (Phase 4 corrections)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = (
    "finding_id",
    "severity",
    "component",
    "reason",
    "reachability",
    "mitigation",
    "owner",
    "ticket",
    "created_at",
    "expires_at",
)


class SecurityExceptionsError(ValueError):
    """Invalid or expired security exceptions document."""


@dataclass(frozen=True)
class SecurityException:
    finding_id: str
    severity: str
    component: str
    reason: str
    reachability: str
    mitigation: str
    owner: str
    ticket: str
    created_at: date
    expires_at: date
    raw: dict[str, Any]


def _parse_iso_date(value: Any, *, field: str, finding_id: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise SecurityExceptionsError(f"{finding_id}: missing/invalid {field}")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise SecurityExceptionsError(f"{finding_id}: invalid {field}={value!r}") from exc


def load_security_exceptions(path: Path) -> list[SecurityException]:
    if not path.is_file():
        raise SecurityExceptionsError(f"security exceptions file missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SecurityExceptionsError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SecurityExceptionsError("root must be an object")
    items = data.get("exceptions")
    if not isinstance(items, list):
        raise SecurityExceptionsError("'exceptions' must be a list")

    seen: set[str] = set()
    out: list[SecurityException] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise SecurityExceptionsError(f"exceptions[{idx}] must be an object")
        for field in REQUIRED_FIELDS:
            if field not in item or item[field] in (None, ""):
                raise SecurityExceptionsError(
                    f"exceptions[{idx}]: missing required field {field}"
                )
        fid = str(item["finding_id"]).strip()
        if fid in seen:
            raise SecurityExceptionsError(f"duplicate finding_id: {fid}")
        seen.add(fid)
        created = _parse_iso_date(item["created_at"], field="created_at", finding_id=fid)
        expires = _parse_iso_date(item["expires_at"], field="expires_at", finding_id=fid)
        if expires < created:
            raise SecurityExceptionsError(f"{fid}: expires_at before created_at")
        out.append(
            SecurityException(
                finding_id=fid,
                severity=str(item["severity"]).strip().lower(),
                component=str(item["component"]).strip(),
                reason=str(item["reason"]).strip(),
                reachability=str(item["reachability"]).strip().lower(),
                mitigation=str(item["mitigation"]).strip(),
                owner=str(item["owner"]).strip(),
                ticket=str(item["ticket"]).strip(),
                created_at=created,
                expires_at=expires,
                raw=dict(item),
            )
        )
    return out


def validate_security_exceptions_not_expired(
    exceptions: list[SecurityException],
    *,
    today: date | None = None,
) -> None:
    day = today or date.today()
    expired = [e.finding_id for e in exceptions if e.expires_at < day]
    if expired:
        raise SecurityExceptionsError(
            "expired security exceptions: " + ", ".join(sorted(expired))
        )


def render_security_exceptions_markdown(exceptions: list[SecurityException]) -> str:
    lines = [
        "# Phase 4 — Security exceptions (generated)",
        "",
        "Source of truth: `audit/security-exceptions.json`. Do not edit this Markdown by hand.",
        "",
        "| finding_id | severity | component | reachability | owner | ticket | created_at | expires_at |",
        "| ---------- | -------- | --------- | ------------ | ----- | ------ | ---------- | ---------- |",
    ]
    for e in exceptions:
        lines.append(
            f"| {e.finding_id} | {e.severity} | `{e.component}` | {e.reachability} | "
            f"{e.owner} | {e.ticket} | {e.created_at.isoformat()} | {e.expires_at.isoformat()} |"
        )
    lines.extend(
        [
            "",
            "## Details",
            "",
        ]
    )
    for e in exceptions:
        lines.append(f"### {e.finding_id}")
        lines.append("")
        lines.append(f"- **Reason:** {e.reason}")
        lines.append(f"- **Mitigation:** {e.mitigation}")
        lines.append("")
    lines.append(f"_Generated at {datetime.now().date().isoformat()}_")
    lines.append("")
    return "\n".join(lines)


def default_exceptions_path(repo_root: Path) -> Path:
    return repo_root / "audit" / "security-exceptions.json"

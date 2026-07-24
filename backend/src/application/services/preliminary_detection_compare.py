"""Pure comparison of local preliminary vs remote authoritative CODE_SCAN result."""

from __future__ import annotations

from dataclasses import dataclass


COMPARISON_VERSION = "1"

OUTCOME_MATCH_CODE_AND_QUANTITY = "MATCH_CODE_AND_QUANTITY"
OUTCOME_MATCH_CODE_BOTH_QUANTITY_MISSING = "MATCH_CODE_BOTH_QUANTITY_MISSING"
OUTCOME_MATCH_CODE_LOCAL_QUANTITY_MISSING = "MATCH_CODE_LOCAL_QUANTITY_MISSING"
OUTCOME_MATCH_CODE_REMOTE_QUANTITY_MISSING = "MATCH_CODE_REMOTE_QUANTITY_MISSING"
OUTCOME_MATCH_CODE_QUANTITY_DIFFERENT = "MATCH_CODE_QUANTITY_DIFFERENT"
OUTCOME_CODE_MISMATCH = "CODE_MISMATCH"
OUTCOME_LOCAL_ONLY = "LOCAL_ONLY"
OUTCOME_REMOTE_ONLY = "REMOTE_ONLY"
OUTCOME_BOTH_UNRESOLVED = "BOTH_UNRESOLVED"
OUTCOME_LOCAL_AMBIGUOUS = "LOCAL_AMBIGUOUS"
OUTCOME_REMOTE_AMBIGUOUS = "REMOTE_AMBIGUOUS"
OUTCOME_BOTH_AMBIGUOUS = "BOTH_AMBIGUOUS"
OUTCOME_NOT_COMPARABLE = "NOT_COMPARABLE"


def normalize_code(value: str | None) -> str | None:
    """Controlled trim only — no case fold, no zero-stripping, no numeric coercion."""
    if value is None:
        return None
    text = value.strip()
    return text or None


def normalize_quantity(value: int | float | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        return int(value)
    return int(value)


@dataclass(frozen=True)
class LocalCompareInput:
    status: str
    internal_code: str | None
    quantity: int | None
    candidate_count: int = 0


@dataclass(frozen=True)
class RemoteCompareInput:
    status: str | None
    internal_code: str | None
    quantity: int | None
    ambiguous: bool = False


@dataclass(frozen=True)
class ComparisonResult:
    outcome: str
    local_code: str | None
    local_quantity: int | None
    remote_code: str | None
    remote_quantity: int | None


def compare_preliminary_vs_remote(
    local: LocalCompareInput,
    remote: RemoteCompareInput,
) -> ComparisonResult:
    local_code = normalize_code(local.internal_code)
    remote_code = normalize_code(remote.internal_code)
    local_qty = normalize_quantity(local.quantity)
    remote_qty = normalize_quantity(remote.quantity)

    local_ambiguous = (local.status or "").upper() == "AMBIGUOUS" or local.candidate_count > 1
    remote_ambiguous = remote.ambiguous

    if local_ambiguous and remote_ambiguous:
        return ComparisonResult(
            OUTCOME_BOTH_AMBIGUOUS, local_code, local_qty, remote_code, remote_qty
        )
    if local_ambiguous:
        return ComparisonResult(
            OUTCOME_LOCAL_AMBIGUOUS, local_code, local_qty, remote_code, remote_qty
        )
    if remote_ambiguous:
        return ComparisonResult(
            OUTCOME_REMOTE_AMBIGUOUS, local_code, local_qty, remote_code, remote_qty
        )

    local_resolved = bool(local_code) and (local.status or "").upper() in {
        "RESOLVED",
        "DETECTED_UNVERIFIED",
    }
    # Remote authority: presence of code is resolved; UNRECOGNIZED without code is unresolved
    remote_resolved = bool(remote_code)

    if not local_resolved and not remote_resolved:
        return ComparisonResult(
            OUTCOME_BOTH_UNRESOLVED, local_code, local_qty, remote_code, remote_qty
        )
    if local_resolved and not remote_resolved:
        return ComparisonResult(
            OUTCOME_LOCAL_ONLY, local_code, local_qty, remote_code, remote_qty
        )
    if not local_resolved and remote_resolved:
        return ComparisonResult(
            OUTCOME_REMOTE_ONLY, local_code, local_qty, remote_code, remote_qty
        )

    # Both have codes — exact string equality after trim only
    if local_code != remote_code:
        return ComparisonResult(
            OUTCOME_CODE_MISMATCH, local_code, local_qty, remote_code, remote_qty
        )

    if local_qty is None and remote_qty is None:
        return ComparisonResult(
            OUTCOME_MATCH_CODE_BOTH_QUANTITY_MISSING,
            local_code,
            local_qty,
            remote_code,
            remote_qty,
        )
    if local_qty is None and remote_qty is not None:
        return ComparisonResult(
            OUTCOME_MATCH_CODE_LOCAL_QUANTITY_MISSING,
            local_code,
            local_qty,
            remote_code,
            remote_qty,
        )
    if local_qty is not None and remote_qty is None:
        return ComparisonResult(
            OUTCOME_MATCH_CODE_REMOTE_QUANTITY_MISSING,
            local_code,
            local_qty,
            remote_code,
            remote_qty,
        )
    if local_qty != remote_qty:
        return ComparisonResult(
            OUTCOME_MATCH_CODE_QUANTITY_DIFFERENT,
            local_code,
            local_qty,
            remote_code,
            remote_qty,
        )
    return ComparisonResult(
        OUTCOME_MATCH_CODE_AND_QUANTITY, local_code, local_qty, remote_code, remote_qty
    )

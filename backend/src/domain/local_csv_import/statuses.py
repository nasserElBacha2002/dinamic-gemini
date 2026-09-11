"""Local CSV/TXT/ZIP import header status machine (Phase 4).

PREVIEWED → MATERIALIZING → CONFIRMED

Failure / intervention:
  MATERIALIZING | MATERIALIZATION_FAILED → (lease expired + retry) → CONFIRMED
  → REQUIRES_REVIEW when permanent / exhausted (operator may still re-confirm)

CONFIRMED means productive rows and required position materialization succeeded.
Shared by CSV imports and inventory packages (same logical workflow).
"""

from __future__ import annotations

LOCAL_CSV_IMPORT_STATUS_PREVIEWED = "PREVIEWED"
LOCAL_CSV_IMPORT_STATUS_MATERIALIZING = "MATERIALIZING"
LOCAL_CSV_IMPORT_STATUS_CONFIRMED = "CONFIRMED"
LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED = "MATERIALIZATION_FAILED"
LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW = "REQUIRES_REVIEW"

# Alias used by package repository / use cases — same vocabulary.
LOCAL_IMPORT_PACKAGE_STATUSES = frozenset(
    {
        LOCAL_CSV_IMPORT_STATUS_PREVIEWED,
        LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
        LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
        LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
        LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW,
    }
)

LOCAL_CSV_IMPORT_STATUSES = LOCAL_IMPORT_PACKAGE_STATUSES

LOCAL_CSV_IMPORT_CLAIMED_STATUSES = frozenset(
    {
        LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
        LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
        LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
        LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW,
    }
)

# May be claimed when lease expired (MATERIALIZING), failed, or operator retries after review.
LOCAL_CSV_IMPORT_RESUMABLE_STATUSES = frozenset(
    {
        LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
        LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
        LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW,
    }
)

# Soft-terminal: CONFIRMED is final; REQUIRES_REVIEW blocks recovery automation but
# operator confirm may reclaim (see build_lease_claim).
LOCAL_CSV_IMPORT_TERMINAL_STATUSES = frozenset(
    {
        LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    }
)

# Productive results are inventory-visible only for these header statuses.
LOCAL_CSV_IMPORT_PUBLISHED_STATUSES = frozenset(
    {
        LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    }
)

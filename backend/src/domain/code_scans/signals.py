"""Read-only review signal types for aisle code scan operationalization (Phase 6A)."""

from __future__ import annotations

from enum import Enum


class CodeScanSignalSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ATTENTION = "attention"


class CodeScanSignalType(str, Enum):
    CODE_MATCH_FOUND = "code_match_found"
    CODE_NO_MATCH = "code_no_match"
    CODE_MULTIPLE_CANDIDATES = "code_multiple_candidates"
    CODE_CONFLICT = "code_conflict"
    CODE_DETECTED_WITHOUT_RESULT = "code_detected_without_result"
    RESULT_HAS_CODE_EVIDENCE = "result_has_code_evidence"
    RESULT_WITHOUT_CODE_EVIDENCE = "result_without_code_evidence"
    MANY_UNMATCHED_CODES_IN_AISLE = "many_unmatched_codes_in_aisle"
    MANY_MULTIPLE_CANDIDATE_CODES_IN_AISLE = "many_multiple_candidate_codes_in_aisle"
    MATCHING_NOT_EVALUATED = "matching_not_evaluated"

"""Safe supplier payload regex compile — shared by config parse and validation."""

from __future__ import annotations

import re
from functools import lru_cache
from re import Pattern

try:
    from re import _parser as sre_parse  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    import sre_parse  # type: ignore[no-redef]

from src.domain.label_validation import LabelValidationErrorCode

_COMPILED_PATTERN_CACHE_SIZE = 256


class PayloadPatternError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _pattern_has_unsafe_nested_quantifiers(pattern: str) -> bool:
    try:
        tree = sre_parse.parse(pattern)
    except re.error:
        return False

    def walk(ops: object, *, inside_quantified: bool) -> bool:
        for op, av in ops:  # type: ignore[attr-defined]
            if op in (sre_parse.MAX_REPEAT, sre_parse.MIN_REPEAT):
                _min_r, _max_r, sub = av
                if inside_quantified:
                    return True
                if walk(sub, inside_quantified=True):
                    return True
            elif op is sre_parse.SUBPATTERN:
                sub = av[-1]
                if walk(sub, inside_quantified=inside_quantified):
                    return True
            elif op is sre_parse.BRANCH:
                if inside_quantified:
                    return True
                for branch in av[1]:
                    if walk(branch, inside_quantified=inside_quantified):
                        return True
            elif op is sre_parse.GROUPREF_EXISTS:
                if inside_quantified:
                    return True
                yes = av[1]
                no = av[2] if len(av) > 2 else None
                if walk(yes, inside_quantified=inside_quantified):
                    return True
                if no is not None and walk(no, inside_quantified=inside_quantified):
                    return True
            elif op is sre_parse.ASSERT or op is sre_parse.ASSERT_NOT:
                if walk(av[1], inside_quantified=inside_quantified):
                    return True
        return False

    return walk(tree, inside_quantified=False)


@lru_cache(maxsize=_COMPILED_PATTERN_CACHE_SIZE)
def compile_payload_pattern(pattern: str) -> Pattern[str]:
    text = (pattern or "").strip()
    if not text:
        raise PayloadPatternError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            "custom_payload_pattern must not be empty",
        )
    if len(text) > 200:
        raise PayloadPatternError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            "custom_payload_pattern exceeds 200 characters",
        )
    if _pattern_has_unsafe_nested_quantifiers(text):
        raise PayloadPatternError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            "custom_payload_pattern has nested quantifiers or quantified alternation",
        )
    try:
        return re.compile(text)
    except re.error as exc:
        raise PayloadPatternError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            f"invalid custom_payload_pattern: {exc}",
        ) from exc

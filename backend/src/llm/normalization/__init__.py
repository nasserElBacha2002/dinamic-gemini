"""LLM response normalization (multi-provider compatibility)."""

from src.llm.normalization.entity_normalizer import (
    EXTRACTION_CONTRACT_VERSION_KEY,
    EXTRACTION_CONTRACT_VERSION_VALUE,
    normalize_llm_response,
    resolve_provider_family,
)
from src.llm.normalization.numeric_coercion import (
    coerce_v21_product_label_quantities,
    normalize_optional_int,
)

__all__ = [
    "EXTRACTION_CONTRACT_VERSION_KEY",
    "EXTRACTION_CONTRACT_VERSION_VALUE",
    "coerce_v21_product_label_quantities",
    "normalize_optional_int",
    "normalize_llm_response",
    "resolve_provider_family",
]

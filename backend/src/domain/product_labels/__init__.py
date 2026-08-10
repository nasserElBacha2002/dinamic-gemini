"""Physical product-label identity (label_id + read checksum) — distinct from position labels."""

from src.domain.product_labels.format import (
    LABEL_ID_ALPHABET,
    LABEL_ID_LENGTH,
    PRODUCT_LABEL_FORMAT_VERSION,
    PRODUCT_LABEL_PREFIX,
    ParsedProductLabelPayload,
    ProductLabelValidationStatus,
    build_product_label_payload,
    compute_product_label_checksum,
    generate_product_label_id,
    normalize_product_label_raw,
    parse_product_label_payload,
)

__all__ = [
    "LABEL_ID_ALPHABET",
    "LABEL_ID_LENGTH",
    "PRODUCT_LABEL_FORMAT_VERSION",
    "PRODUCT_LABEL_PREFIX",
    "ParsedProductLabelPayload",
    "ProductLabelValidationStatus",
    "build_product_label_payload",
    "compute_product_label_checksum",
    "generate_product_label_id",
    "normalize_product_label_raw",
    "parse_product_label_payload",
]

"""IssuedProductLabelResolver — registry SoT for D1 scans."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.issued_product_label_repository import IssuedProductLabel
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.product_labels.format import (
    build_product_label_payload,
    parse_product_label_payload,
)
from src.domain.product_labels.processed import ProductLabelOutcomeStatus
from src.infrastructure.repositories.memory_issued_product_label_repository import (
    MemoryIssuedProductLabelRepository,
)


def _issue(repo: MemoryIssuedProductLabelRepository, *, client_id: str = "client-a") -> IssuedProductLabel:
    payload = build_product_label_payload(
        label_id="A1B2C3D4E5", internal_code="SKU100", quantity=4
    )
    parsed = parse_product_label_payload(payload)
    row = IssuedProductLabel(
        id="iss-1",
        client_id=client_id,
        label_id="A1B2C3D4E5",
        internal_code="SKU100",
        quantity=4,
        format_version="D1",
        checksum=str(parsed.checksum_received),
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    repo.save(row)
    return row


def test_valid_issued_accepts() -> None:
    repo = MemoryIssuedProductLabelRepository()
    _issue(repo)
    resolver = IssuedProductLabelResolver(issued_repo=repo)
    parsed = parse_product_label_payload(
        build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU100", quantity=4)
    )
    out = resolver.resolve_parsed(parsed=parsed, expected_client_id="client-a")
    assert out.status is ProductLabelOutcomeStatus.VALID
    assert out.product is not None
    assert out.product.internal_code == "SKU100"


def test_unknown_label_rejects() -> None:
    resolver = IssuedProductLabelResolver(issued_repo=MemoryIssuedProductLabelRepository())
    parsed = parse_product_label_payload(
        build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU100", quantity=4)
    )
    out = resolver.resolve_parsed(parsed=parsed, expected_client_id="client-a")
    assert out.status is ProductLabelOutcomeStatus.UNKNOWN_LABEL


def test_client_mismatch_rejects() -> None:
    repo = MemoryIssuedProductLabelRepository()
    _issue(repo, client_id="client-a")
    resolver = IssuedProductLabelResolver(issued_repo=repo)
    parsed = parse_product_label_payload(
        build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU100", quantity=4)
    )
    out = resolver.resolve_parsed(parsed=parsed, expected_client_id="client-b")
    assert out.status is ProductLabelOutcomeStatus.CLIENT_MISMATCH


def test_sku_tamper_rejects() -> None:
    repo = MemoryIssuedProductLabelRepository()
    _issue(repo)
    resolver = IssuedProductLabelResolver(issued_repo=repo)
    # Valid checksum for tampered SKU but not matching issued SoT.
    tampered = build_product_label_payload(
        label_id="A1B2C3D4E5", internal_code="OTHER", quantity=4
    )
    parsed = parse_product_label_payload(tampered)
    out = resolver.resolve_parsed(parsed=parsed, expected_client_id="client-a")
    assert out.status is ProductLabelOutcomeStatus.PAYLOAD_MISMATCH


def test_qty_tamper_rejects() -> None:
    repo = MemoryIssuedProductLabelRepository()
    _issue(repo)
    resolver = IssuedProductLabelResolver(issued_repo=repo)
    tampered = build_product_label_payload(
        label_id="A1B2C3D4E5", internal_code="SKU100", quantity=9
    )
    parsed = parse_product_label_payload(tampered)
    out = resolver.resolve_parsed(parsed=parsed, expected_client_id="client-a")
    assert out.status is ProductLabelOutcomeStatus.PAYLOAD_MISMATCH

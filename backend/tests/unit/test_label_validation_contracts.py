"""Unit tests — Phase 2 CandidateLabel / NormalizedLabel contracts."""

from __future__ import annotations

import pytest

from src.domain.label_profiles.kinds import LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    NormalizedItemLabel,
    NormalizedPositionLabel,
    RecognitionSource,
)


def test_candidate_item_requires_payload_or_identity() -> None:
    with pytest.raises(ValueError):
        CandidateLabel(raw_payload="   ")


def test_candidate_item_ok() -> None:
    c = CandidateLabel(
        raw_payload="SUP00000001",
        recognition_source=RecognitionSource.CODE_SCAN,
        symbology="CODE_128",
    )
    assert c.raw_payload == "SUP00000001"


def test_normalized_item_requires_sku() -> None:
    with pytest.raises(ValueError):
        NormalizedItemLabel(
            label_id="x",
            sku="  ",
            quantity=1,
            raw_payload="x",
            profile_source=LabelProfileSource.SUPPLIER,
        )


def test_normalized_item_ok() -> None:
    n = NormalizedItemLabel(
        label_id="SUP00000001",
        sku="SUP00000001",
        quantity=None,
        raw_payload="SUP00000001",
        profile_source=LabelProfileSource.SUPPLIER,
    )
    assert n.kind.value == "ITEM"


def test_normalized_position_requires_position_id() -> None:
    with pytest.raises(ValueError):
        NormalizedPositionLabel(
            position_id="",
            pallet=None,
            side=None,
            raw_payload="{}",
            profile_source=LabelProfileSource.DINAMIC,
        )


def test_normalized_position_ok() -> None:
    n = NormalizedPositionLabel(
        position_id="POS-1",
        pallet="P1",
        side="A",
        raw_payload='{"type":"DINAMIC_POSITION"}',
        profile_source=LabelProfileSource.DINAMIC,
    )
    assert n.kind.value == "POSITION"

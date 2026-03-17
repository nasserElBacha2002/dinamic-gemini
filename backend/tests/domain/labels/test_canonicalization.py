"""Unit tests for SKU canonicalization — v3.2.3."""

import pytest

from src.domain.labels.canonicalization import canonicalize_sku


def test_canonicalize_trim():
    assert canonicalize_sku("  SKU-1  ") == "SKU-1"
    assert canonicalize_sku("\tABC\n") == "ABC"


def test_canonicalize_uppercase():
    assert canonicalize_sku("abc") == "ABC"
    assert canonicalize_sku("AbC") == "ABC"


def test_canonicalize_repeated_spaces():
    assert canonicalize_sku("A  B   C") == "A B C"


def test_canonicalize_separators():
    assert canonicalize_sku("A__B---C") == "A-B-C"
    assert canonicalize_sku("SKU--001") == "SKU-001"


def test_canonicalize_empty_none():
    assert canonicalize_sku(None) is None
    assert canonicalize_sku("") is None
    assert canonicalize_sku("   ") is None
    assert canonicalize_sku(" - _ ") is None


def test_canonicalize_preserves_valid():
    assert canonicalize_sku("SKU-001") == "SKU-001"
    assert canonicalize_sku("ITEM 1") == "ITEM 1"

"""``engine_params_json`` coercion for optional job tuning flags."""

from __future__ import annotations

import pytest

from src.application.services.job_engine_params import coerce_prompt_parity_mode


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, False),
        ("not-a-dict", False),
        ({}, False),
        ({"prompt_parity_mode": False}, False),
        ({"prompt_parity_mode": True}, True),
        ({"prompt_parity_mode": "true"}, True),
        ({"prompt_parity_mode": "TRUE"}, True),
        ({"prompt_parity_mode": "1"}, True),
        ({"prompt_parity_mode": "yes"}, True),
        ({"prompt_parity_mode": "on"}, True),
        ({"prompt_parity_mode": "false"}, False),
        ({"prompt_parity_mode": 0}, False),
        ({"prompt_parity_mode": 1}, True),
    ],
)
def test_coerce_prompt_parity_mode(raw: object, expected: bool) -> None:
    assert coerce_prompt_parity_mode(raw) is expected

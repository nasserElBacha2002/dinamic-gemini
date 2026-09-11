from __future__ import annotations

import json
from pathlib import Path

from src.api.schemas.preliminary_detection_schemas import (
    PreliminaryDetectionUpsertRequest,
    PreliminaryDetectionUpsertResponse,
)

_CONTRACT_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "position-sync" / "v2"


def test_shared_position_sync_v2_request_fixture() -> None:
    payload = json.loads((_CONTRACT_ROOT / "request-unmaterialized.json").read_text())

    parsed = PreliminaryDetectionUpsertRequest.model_validate(payload)

    assert parsed.schema_version == "2"
    assert parsed.position_reference is not None
    assert parsed.position_reference.remote_position_id is None


def test_shared_position_sync_v2_response_fixture() -> None:
    payload = json.loads((_CONTRACT_ROOT / "response-accepted-unmaterialized.json").read_text())

    parsed = PreliminaryDetectionUpsertResponse.model_validate(payload)

    assert parsed.position_result is not None
    assert parsed.position_result.status == "ACCEPTED_UNMATERIALIZED"

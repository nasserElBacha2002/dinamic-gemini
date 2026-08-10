"""Unit tests — Phase 3 position label parser / classifier / validation / resolver / use case."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.application.services.position_label_detection.code_classifier import CodeClassifier
from src.application.services.position_label_detection.payload_parser import (
    PositionLabelPayloadParser,
)
from src.application.services.position_label_detection.resolver import PositionLabelResolver
from src.application.services.position_label_detection.validation_service import (
    PositionLabelValidationService,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.application.use_cases.position_label_detection.detect_image_position_labels import (
    ImagePositionDetectionCommand,
    ImagePositionDetectionUseCase,
)
from src.domain.aisle_location.payload import build_positioning_label_payload
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelSignatureStatus,
    ClientPositionLabelStatus,
)
from src.domain.position_label_detection.entities import (
    DetectedCode,
    ImageCodeKind,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.infrastructure.repositories.memory_client_position_label_repository import (
    MemoryClientPositionLabelRepository,
)
from src.infrastructure.repositories.memory_image_position_label_detection_repository import (
    MemoryImagePositionLabelDetectionRepository,
)


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _signing(secret: str = "test-secret-16chars") -> PositioningLabelSigningService:
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret=secret, key_version=1, required=True)
    )


def _signed_payload(label_id: str = "pos_test_1") -> dict:
    base = build_positioning_label_payload(public_label_id=label_id, version=1)
    return _signing().sign_payload(base)


def test_classifier_routes_position_vs_item() -> None:
    clf = CodeClassifier(max_payload_bytes=4096)
    pos = DetectedCode(
        symbology="QR_CODE",
        raw_value='{"type":"DINAMIC_POSITION","version":1,"label_id":"x"}',
        normalized_value='{"type":"DINAMIC_POSITION","version":1,"label_id":"x"}',
    )
    item = DetectedCode(symbology="QR_CODE", raw_value="SKU123|10", normalized_value="SKU123|10")
    assert clf.classify(pos) is ImageCodeKind.POSITION
    assert clf.classify(item) is ImageCodeKind.ITEM


def test_parser_rejects_legacy_inventory_fields() -> None:
    parser = PositionLabelPayloadParser(max_payload_bytes=4096)
    raw = (
        '{"type":"DINAMIC_POSITION","version":1,"label_id":"pos_x",'
        '"inventory_id":"inv-1","signature":"abc"}'
    )
    parsed = parser.parse(raw)
    assert parsed.status is PositionLabelDetectionStatus.UNSUPPORTED_LEGACY_PAYLOAD


def test_parser_unsupported_version() -> None:
    parser = PositionLabelPayloadParser(max_payload_bytes=4096)
    raw = '{"type":"DINAMIC_POSITION","version":99,"label_id":"pos_x","signature":"abc"}'
    assert parser.parse(raw).status is PositionLabelDetectionStatus.UNSUPPORTED_VERSION


def test_validation_invalid_signature() -> None:
    signed = _signed_payload()
    signed["signature"] = "0" * 64
    parser = PositionLabelPayloadParser(max_payload_bytes=4096)
    import json

    parsed = parser.parse(json.dumps(signed, separators=(",", ":")))
    # Force VALID parse with bad sig content already present
    assert parsed.status is PositionLabelDetectionStatus.VALID
    validator = PositionLabelValidationService(
        signing=_signing(), signature_validation_enabled=True
    )
    result = validator.validate(parsed)
    assert result.detection_status is PositionLabelDetectionStatus.INVALID_SIGNATURE


def test_resolver_client_mismatch_and_invalidated() -> None:
    repo = MemoryClientPositionLabelRepository()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    label = ClientPositionLabel(
        id=str(uuid4()),
        client_id="client-a",
        public_identifier="pos_a",
        name="A-01",
        normalized_name="A-01",
        status=ClientPositionLabelStatus.ACTIVE,
        payload_version=1,
        canonical_payload={},
        created_at=now,
        updated_at=now,
    )
    repo.save(label)
    resolver = PositionLabelResolver(label_repo=repo)
    mismatch = resolver.resolve(public_label_id="pos_a", expected_client_id="client-b")
    assert mismatch.detection_status is PositionLabelDetectionStatus.CLIENT_MISMATCH
    assert mismatch.label is None

    label.status = ClientPositionLabelStatus.INVALIDATED
    repo.save(label)
    inv = resolver.resolve(public_label_id="pos_a", expected_client_id="client-a")
    assert inv.detection_status is PositionLabelDetectionStatus.LABEL_INVALIDATED


def test_use_case_valid_and_idempotent() -> None:
    import json

    repo_labels = MemoryClientPositionLabelRepository()
    repo_det = MemoryImagePositionLabelDetectionRepository()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    payload = _signed_payload("pos_ok")
    label = ClientPositionLabel(
        id=str(uuid4()),
        client_id="client-1",
        public_identifier="pos_ok",
        name="B-02",
        normalized_name="B-02",
        status=ClientPositionLabelStatus.ACTIVE,
        payload_version=1,
        canonical_payload=payload,
        created_at=now,
        updated_at=now,
    )
    repo_labels.save(label)
    signing = _signing()
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=signing, signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=repo_labels),
        repo=repo_det,
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    code = DetectedCode(
        symbology="QR_CODE",
        raw_value=json.dumps(payload, separators=(",", ":")),
        normalized_value=json.dumps(payload, separators=(",", ":")),
        confidence=None,
    )
    cmd = ImagePositionDetectionCommand(
        client_id="client-1",
        inventory_id="inv-1",
        job_id="job-1",
        source_asset_id="asset-1",
        codes=[code],
        sequence_number=4,
    )
    first = use_case.execute(cmd)
    second = use_case.execute(cmd)
    assert len(first.detections) == 1
    assert first.detections[0].detection_status is PositionLabelDetectionStatus.VALID
    assert first.detections[0].position_name_snapshot == "B-02"
    assert first.detections[0].id == second.detections[0].id
    assert len(repo_det.list_by_job("job-1")) == 1


def test_use_case_ambiguous_two_positions() -> None:
    import json

    repo_labels = MemoryClientPositionLabelRepository()
    repo_det = MemoryImagePositionLabelDetectionRepository()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    signing = _signing()
    for pub, name in (("pos_1", "A"), ("pos_2", "B")):
        payload = signing.sign_payload(build_positioning_label_payload(public_label_id=pub))
        repo_labels.save(
            ClientPositionLabel(
                id=str(uuid4()),
                client_id="client-1",
                public_identifier=pub,
                name=name,
                normalized_name=name,
                status=ClientPositionLabelStatus.ACTIVE,
                payload_version=1,
                canonical_payload=payload,
                created_at=now,
                updated_at=now,
            )
        )
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=signing, signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=repo_labels),
        repo=repo_det,
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    p1 = signing.sign_payload(build_positioning_label_payload(public_label_id="pos_1"))
    p2 = signing.sign_payload(build_positioning_label_payload(public_label_id="pos_2"))
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-1",
            codes=[
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value=json.dumps(p1, separators=(",", ":")),
                    normalized_value="",
                ),
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value=json.dumps(p2, separators=(",", ":")),
                    normalized_value="",
                ),
            ],
        )
    )
    assert result.ambiguous is True
    assert any(
        d.detection_status is PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION
        for d in result.detections
    )


def test_feature_flag_disabled_skips_detection() -> None:
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=MemoryClientPositionLabelRepository()),
        repo=MemoryImagePositionLabelDetectionRepository(),
        clock=_Clock(),
        detection_enabled=False,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="c",
            inventory_id="i",
            job_id="j",
            source_asset_id="a",
            codes=[DetectedCode(symbology="QR_CODE", raw_value="x", normalized_value="x")],
        )
    )
    assert result.disabled is True
    assert result.detections == ()


def test_parser_missing_signature_and_payload_too_large() -> None:
    missing = PositionLabelPayloadParser(max_payload_bytes=4096).parse(
        '{"type":"DINAMIC_POSITION","version":1,"label_id":"pos_x","key_version":1}'
    )
    assert missing.status is PositionLabelDetectionStatus.MISSING_SIGNATURE
    # Parser floors max_payload_bytes at 256 bytes.
    huge = PositionLabelPayloadParser(max_payload_bytes=256).parse("x" * 300)
    assert huge.status is PositionLabelDetectionStatus.PAYLOAD_TOO_LARGE


def test_unsigned_active_label_accepted_when_qr_missing_signature() -> None:
    """Labels created without HMAC (UNSIGNED) must still resolve by label_id."""
    repo_labels = MemoryClientPositionLabelRepository()
    repo_det = MemoryImagePositionLabelDetectionRepository()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    payload = build_positioning_label_payload(public_label_id="pos_unsigned", version=1)
    repo_labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-1",
            public_identifier="pos_unsigned",
            name="U-01",
            normalized_name="U-01",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
            signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
        )
    )
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=repo_labels),
        repo=repo_det,
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    raw = '{"type":"DINAMIC_POSITION","version":1,"label_id":"pos_unsigned"}'
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-u",
            codes=[
                DetectedCode(symbology="QR_CODE", raw_value=raw, normalized_value=raw, candidate_index=0)
            ],
        )
    )
    assert result.position_candidate_indexes == (0,)
    assert len(result.detections) == 1
    assert (
        result.detections[0].detection_status
        is PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW
    )
    assert result.detections[0].signature_status is PositionLabelSignatureStatus.MISSING
    assert result.detections[0].public_identifier == "pos_unsigned"


def test_unsigned_v2_active_label_accepted_when_qr_missing_signature() -> None:
    """Hierarchy v2 labels issued UNSIGNED (no HMAC) must still set position via review path."""
    import json

    repo_labels = MemoryClientPositionLabelRepository()
    repo_det = MemoryImagePositionLabelDetectionRepository()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    payload = build_positioning_label_payload(
        public_label_id="pos_v2_unsigned",
        pallet="02",
        side="LEFT",
        level=1,
        marker_index=1,
        marker_total=1,
    )
    assert payload["version"] == 2
    repo_labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-1",
            public_identifier="pos_v2_unsigned",
            name="Pallet 02 - LEFT - Level 1",
            normalized_name="PALLET 02 - LEFT - LEVEL 1",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=2,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
            signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
        )
    )
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=repo_labels),
        repo=repo_det,
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-v2-u",
            codes=[
                DetectedCode(symbology="QR_CODE", raw_value=raw, normalized_value=raw, candidate_index=0)
            ],
        )
    )
    assert len(result.detections) == 1
    assert (
        result.detections[0].detection_status
        is PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW
    )
    assert result.detections[0].public_identifier == "pos_v2_unsigned"
    assert result.detections[0].metadata_json.get("pallet") == "02"


def test_use_case_position_plus_item_keeps_both() -> None:
    import json

    repo_labels = MemoryClientPositionLabelRepository()
    repo_det = MemoryImagePositionLabelDetectionRepository()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    payload = _signed_payload("pos_mix")
    repo_labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-1",
            public_identifier="pos_mix",
            name="C-03",
            normalized_name="C-03",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=repo_labels),
        repo=repo_det,
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-mix",
            codes=[
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value=json.dumps(payload, separators=(",", ":")),
                    normalized_value="",
                ),
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value="SKU|5",
                    normalized_value="SKU|5",
                ),
            ],
            sequence_number=2,
        )
    )
    assert len(result.item_codes) == 1
    assert result.item_codes[0].raw_value == "SKU|5"
    assert result.position_candidate_indexes == (0,)
    assert len(result.detections) == 1
    assert result.detections[0].detection_status is PositionLabelDetectionStatus.VALID
    assert result.detections[0].sequence_number == 2


def test_use_case_duplicate_same_label_consolidates() -> None:
    import json

    repo_labels = MemoryClientPositionLabelRepository()
    repo_det = MemoryImagePositionLabelDetectionRepository()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    payload = _signed_payload("pos_dup")
    repo_labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-1",
            public_identifier="pos_dup",
            name="D-01",
            normalized_name="D-01",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=repo_labels),
        repo=repo_det,
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    raw = json.dumps(payload, separators=(",", ":"))
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-dup",
            codes=[
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value=raw,
                    normalized_value=raw,
                    bounding_box={"x": 1},
                ),
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value=raw,
                    normalized_value=raw,
                    bounding_box={"x": 2},
                ),
            ],
        )
    )
    assert len(result.detections) == 1
    assert result.detections[0].detection_status is PositionLabelDetectionStatus.VALID
    assert result.detections[0].metadata_json.get("duplicate_code_count") == 2


def test_use_case_label_not_found() -> None:
    import json

    payload = _signed_payload("pos_missing")
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=MemoryClientPositionLabelRepository()),
        repo=MemoryImagePositionLabelDetectionRepository(),
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-missing",
            codes=[
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value=json.dumps(payload, separators=(",", ":")),
                    normalized_value="",
                )
            ],
        )
    )
    assert result.detections[0].detection_status is PositionLabelDetectionStatus.LABEL_NOT_FOUND


def test_structured_error_codes() -> None:
    from src.application.errors import PositionLabelDetectionContextInvalidError

    assert (
        PositionLabelDetectionContextInvalidError().code
        == "POSITION_LABEL_DETECTION_CONTEXT_INVALID"
    )


def test_max_codes_does_not_drop_item_candidates() -> None:
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=MemoryClientPositionLabelRepository()),
        repo=MemoryImagePositionLabelDetectionRepository(),
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=False,
        max_codes_per_image=2,
        persist_no_label=False,
    )
    codes = [
        DetectedCode(symbology="QR_CODE", raw_value=f"ITEM{i}|1", normalized_value=f"ITEM{i}|1")
        for i in range(40)
    ]
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-many",
            codes=codes,
        )
    )
    assert len(result.item_codes) == 40
    assert result.position_candidate_indexes == ()
    assert result.detections == ()


def test_signature_disabled_is_not_operationally_valid() -> None:
    import json

    payload = _signed_payload("pos_skip")
    validator = PositionLabelValidationService(
        signing=_signing(), signature_validation_enabled=False
    )
    parsed = PositionLabelPayloadParser(max_payload_bytes=4096).parse(
        json.dumps(payload, separators=(",", ":"))
    )
    result = validator.validate(parsed)
    assert result.detection_status is PositionLabelDetectionStatus.SIGNATURE_VALIDATION_SKIPPED
    assert result.signature_status.value == "SKIPPED"


def test_missing_client_id_is_context_invalid() -> None:
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=MemoryClientPositionLabelRepository()),
        repo=MemoryImagePositionLabelDetectionRepository(),
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="  ",
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-1",
            codes=[DetectedCode(symbology="QR_CODE", raw_value="SKU|1", normalized_value="SKU|1")],
        )
    )
    assert result.context_invalid is True
    assert result.detections == ()
    assert len(result.item_codes) == 1


def test_job_scoped_idempotency_preserves_history() -> None:
    import json

    repo_labels = MemoryClientPositionLabelRepository()
    repo_det = MemoryImagePositionLabelDetectionRepository()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    payload = _signed_payload("pos_jobs")
    repo_labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-1",
            public_identifier="pos_jobs",
            name="J-01",
            normalized_name="J-01",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=_signing(), signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=repo_labels),
        repo=repo_det,
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    raw = json.dumps(payload, separators=(",", ":"))
    code = DetectedCode(symbology="QR_CODE", raw_value=raw, normalized_value=raw)
    first = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-a",
            source_asset_id="asset-shared",
            codes=[code],
        )
    )
    second = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-1",
            inventory_id="inv-1",
            job_id="job-b",
            source_asset_id="asset-shared",
            codes=[code],
        )
    )
    assert first.detections[0].job_id == "job-a"
    assert second.detections[0].job_id == "job-b"
    assert first.detections[0].id != second.detections[0].id
    assert len(repo_det.list_by_job("job-a")) == 1
    assert len(repo_det.list_by_job("job-b")) == 1


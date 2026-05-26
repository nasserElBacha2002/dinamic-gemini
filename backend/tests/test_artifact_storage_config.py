from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

import src.config as config_mod
from src.api import dependencies as deps
from src.config import Settings, load_settings
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter
from src.runtime.app_container import reset_app_container_for_tests


def _reset_config_cache() -> None:
    config_mod._settings = None
    reset_app_container_for_tests()


def test_settings_require_s3_bucket_when_provider_is_s3() -> None:
    with patch.dict(
        os.environ, {"ARTIFACT_STORAGE_PROVIDER": "s3", "ARTIFACT_S3_BUCKET": ""}, clear=False
    ):
        with pytest.raises(Exception):
            Settings()


def test_settings_require_gcs_bucket_when_provider_is_gcs() -> None:
    with patch.dict(
        os.environ, {"ARTIFACT_STORAGE_PROVIDER": "gcs", "GCS_BUCKET_NAME": ""}, clear=False
    ):
        with pytest.raises(Exception):
            Settings()


def test_settings_accepts_gcs_provider_with_bucket() -> None:
    with patch.dict(
        os.environ,
        {"ARTIFACT_STORAGE_PROVIDER": "gcs", "GCS_BUCKET_NAME": "my-gcs-bucket"},
        clear=False,
    ):
        settings = Settings()
        assert settings.artifact_storage_provider == "gcs"
        assert settings.artifact_gcs_bucket == "my-gcs-bucket"


def test_settings_rejects_unknown_artifact_storage_provider() -> None:
    with patch.dict(os.environ, {"ARTIFACT_STORAGE_PROVIDER": "azure"}, clear=False):
        with pytest.raises(Exception):
            Settings()


def test_get_artifact_storage_local_provider() -> None:
    _reset_config_cache()
    with patch.dict(
        os.environ,
        {
            "ARTIFACT_STORAGE_PROVIDER": "local",
            "OUTPUT_DIR": "output_test_artifacts",
        },
        clear=False,
    ):
        _ = load_settings()
        storage = deps.get_artifact_storage()
        assert isinstance(storage, V3ArtifactStorageAdapter)
        assert Path("output_test_artifacts").exists()


def test_get_artifact_storage_s3_provider_uses_s3_adapter() -> None:
    _reset_config_cache()

    class _FakeS3Adapter:
        def __init__(self, **kwargs):
            self.bucket = kwargs["bucket"]
            self.prefix = kwargs["prefix"]

    with patch.dict(
        os.environ,
        {
            "ARTIFACT_STORAGE_PROVIDER": "s3",
            "ARTIFACT_S3_BUCKET": "bucket-a",
            "ARTIFACT_S3_REGION": "us-east-1",
            "ARTIFACT_S3_PREFIX": "v3",
            "ARTIFACT_S3_SIGNED_URL_TTL_SEC": "600",
        },
        clear=False,
    ):
        _ = load_settings()
        with patch(
            "src.infrastructure.storage.s3_artifact_storage_adapter.S3ArtifactStorageAdapter",
            _FakeS3Adapter,
        ):
            storage = deps.get_artifact_storage()
        assert isinstance(storage, _FakeS3Adapter)
        assert storage.bucket == "bucket-a"
        assert storage.prefix == "v3"


def test_get_artifact_storage_gcs_provider_uses_gcs_adapter() -> None:
    _reset_config_cache()

    class _FakeGcsAdapter:
        def __init__(self, **kwargs):
            self.bucket = kwargs["bucket"]
            self.prefix = kwargs["prefix"]

    with patch.dict(
        os.environ,
        {
            "ARTIFACT_STORAGE_PROVIDER": "gcs",
            "GCS_BUCKET_NAME": "bucket-gcs",
            "GCS_PROJECT_ID": "proj-1",
            "GCS_OBJECT_PREFIX": "v3",
            "GCS_SIGNED_URL_TTL_SECONDS": "600",
        },
        clear=False,
    ):
        _ = load_settings()
        with patch(
            "src.infrastructure.storage.gcs_artifact_storage_adapter.GcsArtifactStorageAdapter",
            _FakeGcsAdapter,
        ):
            storage = deps.get_artifact_storage()
        assert isinstance(storage, _FakeGcsAdapter)
        assert storage.bucket == "bucket-gcs"
        assert storage.prefix == "v3"

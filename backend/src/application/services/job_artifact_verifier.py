"""Read-only artifact manifest verification — Phase 3.3."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import REQUIRED_ARTIFACT_KINDS, is_required_artifact_kind
from src.domain.jobs.finalization_evidence import ArtifactVerificationVerdict
from src.infrastructure.storage.artifact_store import ArtifactStore


@dataclass(frozen=True)
class ArtifactEntryVerification:
    artifact_kind: str
    verdict: ArtifactVerificationVerdict
    required: bool
    storage_key: str | None = None


class JobArtifactVerifier:
    def __init__(
        self,
        *,
        manifest_store: ArtifactManifestStore,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self._manifest = manifest_store
        self._artifact_store = artifact_store

    def verify_required(self, job_id: str) -> list[ArtifactEntryVerification]:
        return [self.verify_entry(job_id, kind) for kind in sorted(REQUIRED_ARTIFACT_KINDS)]

    def verify_entry(self, job_id: str, artifact_kind: str) -> ArtifactEntryVerification:
        required = is_required_artifact_kind(artifact_kind)
        entry = self._manifest.get_entry(job_id, artifact_kind)
        if entry is None:
            return ArtifactEntryVerification(
                artifact_kind=artifact_kind,
                verdict=ArtifactVerificationVerdict.MISSING,
                required=required,
            )
        if entry.status in (
            ArtifactManifestStatus.PENDING,
            ArtifactManifestStatus.UNKNOWN,
            ArtifactManifestStatus.FAILED,
        ):
            return ArtifactEntryVerification(
                artifact_kind=artifact_kind,
                verdict=ArtifactVerificationVerdict.MISSING,
                required=entry.required,
                storage_key=entry.storage_key,
            )
        if entry.status != ArtifactManifestStatus.PUBLISHED:
            return ArtifactEntryVerification(
                artifact_kind=artifact_kind,
                verdict=ArtifactVerificationVerdict.UNVERIFIABLE,
                required=entry.required,
                storage_key=entry.storage_key,
            )
        if not entry.storage_key:
            return ArtifactEntryVerification(
                artifact_kind=artifact_kind,
                verdict=ArtifactVerificationVerdict.MISSING,
                required=entry.required,
            )
        if self._artifact_store is None:
            return ArtifactEntryVerification(
                artifact_kind=artifact_kind,
                verdict=ArtifactVerificationVerdict.UNVERIFIABLE,
                required=entry.required,
                storage_key=entry.storage_key,
            )
        try:
            if not self._artifact_store.object_exists(entry.storage_key):
                return ArtifactEntryVerification(
                    artifact_kind=artifact_kind,
                    verdict=ArtifactVerificationVerdict.MISSING,
                    required=entry.required,
                    storage_key=entry.storage_key,
                )
            if entry.size_bytes is not None:
                size = self._artifact_store.object_size_bytes(entry.storage_key)
                if size != entry.size_bytes:
                    return ArtifactEntryVerification(
                        artifact_kind=artifact_kind,
                        verdict=ArtifactVerificationVerdict.MISMATCH,
                        required=entry.required,
                        storage_key=entry.storage_key,
                    )
        except Exception:
            return ArtifactEntryVerification(
                artifact_kind=artifact_kind,
                verdict=ArtifactVerificationVerdict.UNVERIFIABLE,
                required=entry.required,
                storage_key=entry.storage_key,
            )
        return ArtifactEntryVerification(
            artifact_kind=artifact_kind,
            verdict=ArtifactVerificationVerdict.CONFIRMED,
            required=entry.required,
            storage_key=entry.storage_key,
        )

    def verify_all(self, job_id: str) -> list[ArtifactEntryVerification]:
        known = {e.artifact_kind for e in self._manifest.list_entries(job_id)}
        kinds = sorted(known | set(REQUIRED_ARTIFACT_KINDS))
        return [self.verify_entry(job_id, kind) for kind in kinds]

# GCS latency investigation — observability hardening

**Date:** 2026-08-31  
**Scope:** Observability + Job/Aisle ID hardening only. **No** change to `CODE_SCAN_VARIANTS_BUDGET_SECONDS` (remains 15s, starts after `source_loaded`).

## Architecture (confirmed)

```text
CodeScanProcessingStrategy.process
  → ArtifactStoreSourceAssetContentReader.read_image_bytes
    → ArtifactStore.get_object
      → GcsArtifactStorageAdapter.get_object
        → google.cloud.storage.Client (process-scoped)
        → bucket.blob(object_key).download_as_bytes()
        → blob.reload()   # pre-existing metadata call, not added for obs
```

| Concern | Finding | Classification |
| --- | --- | --- |
| Client recreation per asset | `build_artifact_storage` builds one adapter; `GcsArtifactStorageAdapter` holds one `Client` in `__init__` | **CONFIRMED** reused per process |
| Credential refresh | Best-effort `credentials_expired_at_start` flag only; no token material logged | **UNVERIFIED** as root cause of 16–20s spikes |
| SDK retries | google-cloud-storage may retry under the hood; no public per-call retry counter | **UNVERIFIED** (`retry_status=unknown`) |
| DNS / connection reuse | Relies on SDK HTTP session; no custom pooling added | **LIKELY** reused after first call in-process |
| Network latency | Historical jobs show 3s vs 16–20s for similar assets | **LIKELY** variable storage/network |
| Large object size | ~2.3MB assets observed; not uniquely correlated with timeout | **REJECTED** as sole cause |
| Decoder CPU | Post-fix job: decode ~0.65–0.75s while storage 2.4–3.1s | **REJECTED** as timeout cause |
| Server saturation | Not measured live in this phase (DB unreachable from agent env) | **UNVERIFIED** |

## Timeout-scope fix (context only — already shipped)

```text
Before: CODE_SCAN variants budget started at process() entry (included GCS load)
After:  budget starts after source_loaded as decode_budget_started_at
```

Confirmed by `test_code_scan_timeout_scope.py` and current `code_scan_processing_strategy.py`.

## Historical comparative table

| Job | Asset context | Storage ms | Decoder ms | Outcome |
| --- | ---: | ---: | ---: | --- |
| `4230ded7-eb45-445e-bfb5-ecd2fc054a92` | asset1 (prior audit) | ~20150 | ~82 until timeout | FAILED_TECHNICAL (`CODE_SCAN_TIMEOUT`, asset-wide budget) |
| `697aed4c…` (same aisle lineage) | same assets family | ~16079 | ~44 until timeout | FAILED_TECHNICAL |
| `939ecf64-8598-4694-a552-d15535ab0a45` | post-fix worker | ~3055 / ~2400 | ~751 / ~650 | UNRECOGNIZED (no timeout) |

Confused UUID `83934f6e-28dc-4bfc-a262-228d710bb37d` is an **aisle_id**, not a job_id. Latest job on that aisle was `939ecf64…`.

## What this phase adds

1. **Storage fetch timings** on `ArtifactStoreSourceAssetContentReader` (`storage_fetch_ms`, backend, bucket, byte_length, attempt, success).
2. **GCS adapter phase timings** (`download_ms`, `metadata_lookup_ms`, `total_storage_ms`) without extra HEAD/download.
3. **Slow warning** `asset.storage_fetch_slow` when `duration_ms >= SLOW_STORAGE_FETCH_WARNING_MS` (default 10000) — observability only.
4. **Metrics** `storage_fetch_duration_seconds`, `storage_fetch_slow_total`, `storage_fetch_failed_total` with `storage_backend` + `outcome` labels only.
5. **Sanitizer allowlist** so `source_load_ms` / storage fields actually persist in `processing_events`.
6. **UI** unambiguous Job / Pasillo / Inventario / Execution labels + copy actions.
7. **`scripts/debug_job.py`** rejects aisle UUID passed as `--job-id` (exit 2) and supports `--aisle-id`.
8. **`scripts/benchmark_asset_storage.py`** for repeated same-object timing (documents cache caveats).

## Benchmark note

Live GCS multi-run benchmark was **not** executed in this agent environment (SQL Server login timeout). Run on a worker/ops host:

```bash
python scripts/benchmark_asset_storage.py --asset-id <uuid> --runs 10
```

Do **not** interpret results as pure GCS RTT: SDK reuse, TLS session reuse, and local caches can affect later runs.

## Separation of concerns

```text
Storage latency  ≠  Barcode decoder latency  ≠  CODE_SCAN variants budget
```

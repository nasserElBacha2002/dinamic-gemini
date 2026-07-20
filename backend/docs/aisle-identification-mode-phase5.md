# Aisle identification — Phase 5 (selective external fallback)

## Enable / rollback

```env
EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=false   # default OFF
EXTERNAL_FALLBACK_PROVIDER=gemini
EXTERNAL_FALLBACK_MODEL=
MAX_EXTERNAL_FALLBACK_CONCURRENCY=1
EXTERNAL_FALLBACK_TIMEOUT_SECONDS=60
EXTERNAL_FALLBACK_MAX_ATTEMPTS=1
EXTERNAL_FALLBACK_CIRCUIT_BREAKER_THRESHOLD=5
EXTERNAL_FALLBACK_CIRCUIT_BREAKER_COOLDOWN_SECONDS=60
MULTI_PROVIDER_FALLBACK_ENABLED=false       # must stay false (not implemented)
```

| Flag | Effect |
|------|--------|
| `false` (default) | Internal CODE_SCAN / INTERNAL_OCR results that fail stay unrecognized / manual review — **no** provider call |
| `true` | Eligible unresolved assets call **one** primary external provider **per image** |

Rollback: set `EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=false`. New jobs snapshot the flag; in-flight / retry jobs keep their immutable `engine_params_json.identification_execution.external_fallback`.

## Flow (per asset)

```text
Internal strategy (CODE_SCAN | INTERNAL_OCR)
  → RESOLVED_INTERNAL → persist → done (no provider)
  → eligible failure → claim durable request (idempotency key)
  → provider call (retries for TIMEOUT / RATE_LIMITED / recoverable 5xx)
  → durable normalized response on request
  → validate (client_rules from snapshot + shared validators)
  → persist / reconcile position
  → finalize attempt SUCCEEDED only when position/active_result exists
  → asset RESOLVED_EXTERNAL
```

Never marks `attempt SUCCEEDED` solely because the provider returned code+quantity.

### Recovery windows

| Case | Behavior |
|------|----------|
| A — provider responded, worker died before durable save | May repeat the provider call (no durable evidence). Minimize by persisting ASAP after the call. |
| B — normalized response durable, crash before position | Retry **reuses** stored normalized result (no new provider call). |
| C — position persisted, crash before finalize | Recovery reconciles and finalizes attempt/request without a new call. |

Idempotency key: `job_id|asset_id|provider|model|prompt_version|configuration_snapshot_version` (table `external_image_analysis_requests`, migration 0056).

## Eligibility (`FallbackEligibilityPolicy`)

Built from **snapshot** `enabled` + optional `recoverable_technical_codes` +
`ambiguous_internal_code_fallback_enabled` (not live defaults alone).

Eligible examples:
- `UNRECOGNIZED` / missing internal code
- `MISSING_QUANTITY` only when profile evidence sets `fallback_eligible=true`
  (`MissingQuantityResolutionPolicy.allow_external_fallback`)
- `AMBIGUOUS_INTERNAL_CODE` only when the snapshot flag is true

Never eligible:
- `RESOLVED_INTERNAL` / `RESOLVED_EXTERNAL`
- technical source/engine failures (`INTERNAL_OCR_TIMEOUT`, decode/read failures,
  `PROFILE_SNAPSHOT_INVALID`, …) — AI must not paper over defects
- persistence / concurrency / misconfiguration codes
- cancelled jobs / lost lease / circuit open
- broad `PENDING_MANUAL_REVIEW` (e.g. `CODE_LENGTH_NOT_EXACT`) without an
  allowlisted business reason

Default `recoverable_technical_codes` is **empty**.

## Snapshot

Stored at job create under `identification_execution.external_fallback`:

- `fallback_enabled`, `fallback_provider`, `fallback_model`, `prompt_key` / `prompt_version`
- timeout, max_attempts, retry_backoff_seconds, concurrency, circuit breaker, quantity_max, recoverable codes, client_rules

Live settings supply credentials/endpoints only. Provider/model identity comes from the snapshot via `ExternalProviderFactory`.

Retries **copy** the snapshot (see `retry_aisle_job`); they do not re-read live env for provider choice.

## Attempts

Internal and external attempts are separate rows (`strategy=CODE_SCAN|INTERNAL_OCR` then `EXTERNAL_PROVIDER`).

Statuses are separated: `provider_call_status`, `persistence_status`, `attempt_status`, `asset_status`.

Estimated cost (when usage is available) is stored on `attempt.extra.estimated_cost`. Evidence uses `request_image_sha256` vs `provider_response_sha256` (never call the image hash `response_hash`).

## Circuit breaker

Process-local (`provider:model:profile`). States: CLOSED → OPEN → HALF_OPEN (exactly one probe). Opens on timeouts / rate limits / technical failures — **not** on ambiguous / validation / no-result business outcomes.

Limitation: not shared across worker processes.

## Concurrency

`MAX_EXTERNAL_FALLBACK_CONCURRENCY` is independent of `MAX_IMAGE_PROCESSING_CONCURRENCY` and `MAX_INTERNAL_IMAGE_PROCESSING_CONCURRENCY`.

## API / UI

- Job summary: `fallback_progress` (prefer DB aggregate from requests) + `fallback_asset_summaries`
- Observability workspace shows counters + a short per-image fallback line
- Full per-image attempt UX is Phase 7 — see `aisle-identification-mode-phase7.md`

## Security

No API keys, full images, or raw provider payloads in logs. Image MIME/size/dimensions validated before provider call. Response evidence uses hashes / normalized fields only.

## Metrics (process-local)

In-process counters / log lines (`fallback_requested`, etc.) are **not** a
multi-replica guarantee. Prefer:

1. SQL durable rows (`external_image_analysis_requests`, `processing_attempts`)
2. Structured JSON events in the execution log / processing_events table

Do not treat `local_total` style counters as global. Prometheus/OTel adapters
are a follow-up; SQL remains the source of truth for legacy / fallback audit.

## How to test

1. Enable CODE_SCAN or INTERNAL_OCR + `EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=true` in a controlled env.
2. Process an aisle with some unscannable images.
3. Confirm resolved internals never hit the provider; unresolved ones create an `EXTERNAL_PROVIDER` attempt.
4. Confirm `result_json.fallback_progress` / `fallback_asset_summaries` and job summary API fields.
5. Toggle flag off and start a new job — no external calls.

## Recommended controlled defaults

```env
EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=false
MAX_EXTERNAL_FALLBACK_CONCURRENCY=1
EXTERNAL_FALLBACK_MAX_ATTEMPTS=1
MULTI_PROVIDER_FALLBACK_ENABLED=false
```

Controlled live provider tests must be opt-in (credentials + cost limits); unit/contract tests use fakes.

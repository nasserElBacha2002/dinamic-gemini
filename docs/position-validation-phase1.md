# Phase 1 — canonical position validation

## Reconstructed baseline

```text
CURRENT_POSITION_ENTRY_POINTS:
  CODE_SCAN/QR, external Vision, internal OCR, mobile CSV, scanner TXT,
  manual image result, review API, and internal persistence/materialization flows.

CURRENT_AUTHORITATIVE_VALIDATOR:
  No single authority existed. LabelValidationService was authoritative for
  profile-based ITEM/POSITION validation, while ImagePositionDetectionUseCase
  owned Dinamic signature, catalog resolution, and operational policy.

CURRENT_SIGNATURE_RULE:
  DINAMIC_POSITION uses HMAC-SHA256 over canonical JSON excluding `signature`.
  CODE_SCAN verifies it server-side. Mobile only reports structurally-valid
  unverified payloads. Vision previously passed through LabelValidationService,
  whose Dinamic parser checked signature presence but did not verify the HMAC.

CURRENT_EXISTENCE_RULE:
  Dinamic CODE_SCAN resolves `label_id` in client_position_labels, scoped by
  client and ACTIVE status. Supplier-profile position labels and local imports
  do not share that catalog preexistence requirement.

CURRENT_NORMALIZATION_RULE:
  Multiple channel-specific trim/case rules existed. Phase 1 defines NFC,
  outer-trim, uppercase canonical identity; internal separators/spaces remain.
  Control/format characters are rejected and raw input is preserved.

CURRENT_MAX_LENGTH:
  Import transport accepted values up to 255 characters, while
  positions.corrected_position_code persists at most 64. Phase 1 uses 64 as
  the safe shared position identity maximum; no schema migration is included.

CURRENT_POSITION_ITEM_DISCRIMINATION:
  Dinamic discriminators (`D1|` and DINAMIC_POSITION JSON type) are fail-closed.
  Supplier profiles evaluate both kinds and return AMBIGUOUS if both validate.
```

## Phase 1 integration by channel

`CanonicalPositionValidator` now produces a persistence-independent recognition
and an explicit status. Signature evidence distinguishes missing, unverified,
verified, invalid, and not-applicable. A valid unknown position is represented
as `VALID_UNMATERIALIZED`.

- `FULL_CANONICAL_VALIDATION`: generic CODE_SCAN classification and external
  Vision position candidates. Their already-computed deterministic
  `LabelValidationResult` is reused, so profile regex/checksum parsing runs once.
  Dinamic signatures are still verified by the canonical validator.
- `SHADOW_ONLY`: the dedicated `ImagePositionDetectionUseCase` CODE_SCAN path.
  Its legacy result remains operationally authoritative. Canonical resolution is
  explicitly `NOT_EVALUATED`; the comparison stores only statuses, source,
  profile, outcome and reason, never the complete code.
- `SHARED_NORMALIZATION_ONLY`: scanner TXT (`label_id`), local CSV
  (`position_code`), manual image result and review position-code update.
  These paths enforce the same 64-character/control-character identity rule but
  do not claim signature, profile or catalog validation.
- `LEGACY_ONLY`: internal OCR paths that do not expose a canonical position
  candidate. Completing OCR context wiring remains deferred.

Shadow calls do not increment `position_recognition_total`,
`position_validation_rejected_total`, `position_valid_unmaterialized_total` or
other operational canonical counters. They emit only
`position_validation_shadow_comparison_total` with `MATCH`, `DIVERGENCE` or
`NOT_EVALUATED`.

## Server policy and legacy compatibility

The historical signature flag remains independent of the flexible master flag:

```text
POSITION_LABEL_SIGNATURE_VALIDATION_ENABLED=true
POSITIONING_ALLOW_UNSIGNED_LEGACY=true
POSITION_PREEXISTENCE_REQUIRED=true
POSITION_FLEXIBLE_VALIDATION_ENABLED=false
```

Decision rules:

- Flexible off, preexistence on: valid configuration. Signature verification
  follows its historical value; disabling it remains fail-closed as
  `SIGNATURE_VALIDATION_SKIPPED`, rather than accepting an unverified signature.
- Missing-signature acceptance is controlled separately by the historical
  `POSITIONING_ALLOW_UNSIGNED_LEGACY` policy.
- Flexible off, preexistence off: startup fails because unknown-position
  acceptance would bypass the master capability flag.
- Flexible on: signature and preexistence independently follow their configured
  values for all four combinations.

These policies are built from server settings and are not accepted from client,
mobile or frontend payloads. A missing resolver while preexistence is required
is `POSITION_RESOLVER_UNAVAILABLE`, not “position not found”.

## Deferred to Phase 2+

- Mobile capture/synchronization contract and `active_position_json`.
- Automatic materialization/upsert and concurrency/idempotency behavior.
- Persistence migrations or key changes.
- Operational use of `VALID_UNMATERIALIZED` in CODE_SCAN.
- Full OCR context wiring where OCR does not yet expose a position candidate.
- Authoritative inventory writability, inventory/aisle ownership and tenant
  context ports. Those unimplemented booleans/IDs are intentionally absent from
  `CanonicalPositionValidationCommand`.

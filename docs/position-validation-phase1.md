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

## Phase 1 integration

`CanonicalPositionValidator` now produces a persistence-independent recognition
and an explicit status. Signature evidence distinguishes missing, unverified,
verified, invalid, and not-applicable. A valid unknown position is represented
as `VALID_UNMATERIALIZED`.

Supplier-profile CODE_SCAN positions pass the canonical service before being
classified; Dinamic CODE_SCAN invokes it in shadow mode while its established
parser/policy remains operationally authoritative. Vision position candidates
must pass the canonical service and therefore cannot treat signature presence
as verification. CSV/TXT/manual/review inputs share the canonical 64-character
limit and control-character checks.

Defaults remain legacy-compatible:

```text
POSITION_LABEL_SIGNATURE_VALIDATION_ENABLED=true
POSITION_PREEXISTENCE_REQUIRED=true
POSITION_FLEXIBLE_VALIDATION_ENABLED=false
```

## Deferred to Phase 2+

- Mobile capture/synchronization contract and `active_position_json`.
- Automatic materialization/upsert and concurrency/idempotency behavior.
- Persistence migrations or key changes.
- Operational use of `VALID_UNMATERIALIZED` in CODE_SCAN.
- Full OCR context wiring where OCR does not yet expose a position candidate.

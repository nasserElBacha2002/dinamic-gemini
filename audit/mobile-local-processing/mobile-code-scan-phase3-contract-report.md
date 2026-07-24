# Mobile CODE_SCAN Phase 3 — Contract Report

## Authority

Server:

- `parse_inventory_code_payload` (`code_scan_qr_payload.py`)
- `EncodedLabelPayloadParser` (`encoded_label_payload_parser.py`)

Mobile:

- `parseEncodedLabelPayload` / `parseInventoryCodePayloadGrammar` (`mobile/src/core/labelPayload.ts`)
- `consolidateCodeDetections` (`mobile/src/core/codeDetectionConsolidator.ts`)

## Fixtures

Path: `contracts/code-scan/v1/`

| File | Purpose |
| --- | --- |
| `constants.json` | Limits, symbologies, versions |
| `valid.json` | PIPE, DI1, PLAIN, LABELED |
| `invalid.json` | empty, whitespace, control chars, qty above max |
| `ambiguous.json` | multi-code / qty conflict / duplicates / zero |
| `schema.json` | Fixture shape documentation |

Fixtures are hand-authored; not generated from either parser during tests.

## Versions

| Component | Version |
| --- | --- |
| pipeline_version | `code-scan-v1` |
| parser_version | `1.0.0` |
| detector_version | `mlkit-barcode-1.0.0` |
| code_max_length | 48 |
| quantity_max_default | 99999999 |

## Compatibility notes

- Python `ParsedLabelPayload.version` is `None` for non-DI1; contract tests normalize to `"v1"` to match mobile `formatVersion`.
- Quantity-above-max keeps valid code with `quantity=null` and warning `QUANTITY_ABOVE_MAX` (both sides).
- Consolidation statuses from backend (`MULTIPLE_DISTINCT_CODES`, etc.) map to draft UI status `AMBIGUOUS` / `UNRESOLVED` / `RESOLVED` in the strategy layer.

## Tests executed

| Suite | Result |
| --- | --- |
| `mobile/tests/labelPayloadContracts.test.ts` | PASS (14) |
| `./venv/bin/pytest .../test_code_scan_shared_contracts.py` | PASS (9) |

## Divergences

None observed on shared fixtures at the time of this report.

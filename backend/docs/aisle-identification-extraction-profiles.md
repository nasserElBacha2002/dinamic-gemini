# Aisle identification — Phase 6 (supplier extraction profiles)

## Goal

Centralize **structured, versioned extraction rules** per `client_id + supplier_id`
(`client_suppliers.id`) so CODE_SCAN, INTERNAL_OCR, and EXTERNAL_PROVIDER interpret labels
consistently. Free-text prompts and reference annotations are **hints**, not the source of truth.

## Feature flags (default OFF)

```env
CLIENT_EXTRACTION_PROFILES_ENABLED=false
PROFILE_AWARE_VALIDATION_ENABLED=false
REFERENCE_TEMPLATE_ANNOTATIONS_ENABLED=false
```

| Flag | Effect |
|------|--------|
| `CLIENT_EXTRACTION_PROFILES_ENABLED` | Admin profiles + include profile block in job snapshot |
| `PROFILE_AWARE_VALIDATION_ENABLED` | Derive OCR/client_rules and validation from snapshotted profile |
| `REFERENCE_TEMPLATE_ANNOTATIONS_ENABLED` | Use spatial annotations as OCR hints (when strategies load them) |

## Profile sections (A/B/C)

Configuration JSON now separates:

| Section | Key | Purpose |
|---------|-----|---------|
| A — Label detection | `label_detection_rules` | Background/shape/orientation hints, primary/secondary anchors, area bounds, rotation/perspective/full-image fallback |
| B — Internal code | `internal_code_sources` + `validation_rules.code` | Source priority, aliases, `exact_length`, charset, `reject_measurement_patterns` |
| C — Quantity | `quantity_rules` | Aliases, `expected_presence`, `missing_quantity_action` (default `PENDING_MANUAL_REVIEW`), min/max |

Recommended inventory-label starting point:

- Label: LIGHT, APPROXIMATELY_RECTANGULAR, anchors `CÓDIGO INTERNO` / `INVENTARIO GENERAL`
- Code: INTERNAL_CODE only, numeric, `exact_length=7`, preserve leading zeros
- Quantity: aliases `CANT. TOTAL` / `CANTIDAD`, required, missing → manual review

Rollback: set flags to `false`. Profiles remain in DB; historical jobs keep their snapshots.

## Precedence

```text
job snapshot supplier_extraction_profile
→ active supplier profile (new jobs only, when flag on)
→ legacy INTERNAL_OCR_EAN_FIRST_CLIENT_IDS / PREFER_EAN (compatibility)
→ system default profile
```

Retry **never** re-resolves the active profile — it copies `engine_params_json`.

## Model

Table `supplier_extraction_profiles` (migration `0057`):

- Unique `(client_id, supplier_id, version)`
- Filtered unique one `ACTIVE` per `(client_id, supplier_id)` (`UQ_sep_one_active`)
- Statuses: `DRAFT` | `ACTIVE` | `INACTIVE` | `SUPERSEDED`
- `configuration_json` holds structured rules (priorities, quantity, aliases, validations, formats)
- `visual_notes` complementary free text (versioned with the profile)

Annotations: `supplier_reference_annotations` with **normalized** polygons (`0..1`).

## Versioning UX (mirrors prompts)

- **Guardar sin activar** → new `DRAFT`
- **Guardar y activar** → new version + transactional activate (supersede previous ACTIVE)
- **Clone** → new DRAFT from an historical version (never mutate ACTIVE in place)

## Default profile

Conservative: INTERNAL_CODE → EAN → ARTICLE; quantity required; **no** default quantity `1`.

## Shared validator

`ProfileAwareProcessingResultValidator` — deterministic errors such as
`MISSING_QUANTITY`, `AMBIGUOUS_INTERNAL_CODE`, `INVALID_EAN_CHECKSUM`.

## API

Under `/api/v3/clients/{clientId}/suppliers/{supplierId}/`:

- `GET/POST extraction-profiles`
- `GET extraction-profiles/active`
- `GET extraction-profiles/versions/{version}`
- `POST extraction-profiles/clone`
- `POST extraction-profiles/{profileId}/activate`
- `GET/PUT reference-images/{imageId}/annotations`

Admin auth (same as other client/supplier routes).

## Frontend

Supplier detail tab **Instrucciones OCR** (`?tab=instrucciones-ocr`): structured editor
(not a free textarea as primary UI). Reference images: **Configurar campos** for annotations
(desktop preferred for polygon editing).

## Geometry

`LabelGeometryNormalizer` applies EXIF orientation only; perspective is optional/not required.
Annotations are hints — miss → general extraction continues.

## Legacy

`INTERNAL_OCR_EAN_FIRST_CLIENT_IDS` and `INTERNAL_OCR_PREFER_EAN_AS_INTERNAL_CODE` remain until
profiles are rolled out; marked deprecated when profile-aware mode is enabled.

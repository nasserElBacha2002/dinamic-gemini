# Reference images (v3 — Phase C)

## Model

Reference images are **supplier-scoped**, not inventory-scoped.

```
Client
└── Client Supplier
    └── Supplier Reference Images (table: supplier_reference_images)
```

Operators manage them from **Client detail → Supplier → Reference images** (drawer / module). The HTTP API lives under `/api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images`.

The legacy **inventory-level** visual reference system (`inventory_visual_references` and `/inventories/.../visual-references`) was **retired and removed** (Phase C9).

## How processing selects references

1. Each **aisle** may have `client_supplier_id` (FK to the client-scoped supplier).
2. When processing an aisle job, the pipeline loads rows from **`supplier_reference_images`** for that supplier id (via `SupplierReferenceImageResolver` / `AisleAnalysisContextBuilder`).
3. Resolved paths populate **`AnalysisContext.visual_references`** (`VisualReferenceContext`) for the hybrid pipeline input builder.

## Edge cases

| Situation | Behavior |
| --------- | -------- |
| Aisle has **no** `client_supplier_id` | No supplier reference lookup; **zero** visual references attached (still valid run). |
| Supplier has **no** reference-image rows | **Zero** visual references; job proceeds on aisle assets only. |
| Mixed historical jobs | Old `job.result_json` and execution logs may still describe `reference_usage` / `visual_reference_context` — read-only compatibility. |

## Observability

- Execution logs may include **`visual_reference_attachments`** in analysis-request events.
- APIs and UI may surface **`reference_usage`** summaries for recent jobs (resolved counts, errors).

## Related audit

See `audit/phase-c10-final-closure.md` and Phase C0–C9 reports under `audit/`.

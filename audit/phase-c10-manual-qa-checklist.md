# C10 — Manual QA checklist (supplier reference images)

Use in staging/production-like environment after migrations through **0029** are applied.

**Preconditions:** authenticated operator user; SQL Server reachable; API + worker running; artifact storage configured.

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Create or open a **client** | Client detail loads |
| 2 | Create or open a **supplier** under that client | Supplier row visible |
| 3 | **Upload** one or more supplier reference images (UI drawer or POST multipart) | 201 / images listed |
| 4 | Open supplier reference image drawer | Thumbnails / list shows uploads |
| 5 | **Preview** or download `/reference-images/{id}/file` | Image renders or downloads |
| 6 | **Delete** one reference image | 200/204 semantics per API; row disappears |
| 7 | Create **inventory** (optional `client_id` link) | Inventory saves |
| 8 | Create **aisle** with **`client_supplier_id`** pointing at step 2 supplier | Aisle saves |
| 9 | Upload **aisle source assets** (photos/video per product rules) | Assets listed |
| 10 | **Process aisle** | Job reaches terminal success/failure predictably |
| 11 | Inspect execution log / Gemini payload when references exist | `visual_reference_attachments` / counts consistent with supplier images |
| 12 | Job **reference_usage** on aisle/inventory surfaces | Summary reflects resolved refs when applicable |
| 13 | Process aisle with **`client_supplier_id` null** | Completes with **zero** visual references (no supplier lookup) |
| 14 | Process aisle with supplier **without** reference rows | Completes with **zero** visual references |
| 15 | Open **InventoryDetail** | **No** legacy “inventory reference images” management entry point |
| 16 | Open **Create inventory** dialog | Single-step flow; **no** reference-image wizard step |
| 17 | Call legacy paths `GET/POST/PUT/DELETE .../inventories/{id}/visual-references*` | **404** (routes removed) |

**Sign-off:** Name / date / environment / migration version / notes:

```

```

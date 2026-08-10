# ADR: Position marker operational semantics

- **Status:** Accepted
- **Date:** 2026-08-10
- **Context:** Positioning labels can represent multi-marker faces on the same pallet/side/level (e.g. `01/03`, `02/03`, `03/03`). Operators need a clear rule for what counts as a distinct operational position versus a shared hierarchy group.

## Decision

1. **Each `marker_index` is a distinct operational position.**  
   The hierarchy `canonical_key` includes `marker_index` (and `marker_total`). Scans, reconciliation, and inventory assignment treat `P12 LEFT N3 01/03` as a different position than `P12 LEFT N3 02/03`.

2. **A marker set shares pallet / side / level / marker_total.**  
   Creating a marker-set of size N materializes N ACTIVE labels with indices `1..N`. They are siblings of one physical face, not duplicates of one position.

3. **ACTIVE uniqueness is per marker index.**  
   At most one ACTIVE label may exist for `(client_id, pallet, side, level, marker_index)`. Reprinting requires invalidating the previous ACTIVE marker before creating a replacement.

4. **Marker-set create is atomic and optionally idempotent.**  
   All N labels are persisted in one transaction (`save_many`). An `Idempotency-Key` may be stored on the first label; retries with the same key and request fingerprint return the existing set.

## Consequences

- Downstream code must never collapse markers that only share pallet/side/level into a single position key.
- Unique-violation on ACTIVE marker create maps to conflict `POSITION_LABEL_MARKER_ACTIVE_EXISTS`.
- Invalidated markers remain historically auditable but do not block a new ACTIVE marker at the same index.

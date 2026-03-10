# Bug Investigation

## Symptom

- **Observed:** GET `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` returns **500 Internal Server Error**.
- **Frontend:** Positions fetch (from `client.ts` line 142) receives 500; network log shows "positions" resource with 500, 0 B transferred.
- **Backend error:** `pyodbc.ProgrammingError: ('42000', '[42000] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]The multi-part identifier "p.aisle_id" could not be bound. (4104) (SQLExecDirectW)')`
- **Location:** `src/infrastructure/repositories/sql_position_repository.py` line 182, inside `list_by_aisle()`.

## Expected Behavior

- GET aisle positions returns **200** with a JSON list of positions (or empty list when no positions exist).
- No server exception; SQL runs successfully against the `positions` table.

## Area(s) Suspect (Platform / Pipeline)

- **Platform — persistence (SQL repository).** The failure is in the SQL position repository when building/executing the query for `list_by_aisle`. No pipeline or frontend bug; the API and use case are correct.

## Hypotheses (ranked)

### H1: WHERE clause uses alias `p` but the non-join query does not define it (root cause — confirmed)

- **Why likely:** The error says `"p.aisle_id" could not be bound`. In `list_by_aisle`, `conditions` are always built with the `p.` prefix (e.g. `p.aisle_id = ?`, `p.status = ?`). When `sku_filter` is not set, `join_product_records` is False and the code uses a query `FROM positions` with no alias, while `WHERE {where}` still references `p.aisle_id`. SQL Server requires every multi-part identifier to refer to a table/alias that appears in the FROM clause.
- **How to confirm:** Read `sql_position_repository.py`: the `else` branch (no join) uses `FROM positions` and `WHERE {where}` where `where` contains `p.aisle_id`. Confirmed.
- **Logs/metrics to add:** None required for this fix. Optional: log which branch is used (`join_product_records` True/False) if debugging similar issues later.
- **Minimal repro:** Call `list_by_aisle(aisle_id="some-id")` with no filters (no sku_filter, no status, etc.) so the else branch runs. Requires SQL Server backend.
- **Fix (minimal):** In the `else` branch, use the same alias `p` so the existing WHERE is valid: `FROM positions p` and qualify SELECT/ORDER BY with `p.` (e.g. `p.id`, `p.aisle_id`, `ORDER BY p.created_at ASC, p.id ASC`).

### H2: Wrong parameter order or count

- **Why less likely:** The error is specifically about the identifier "p.aisle_id" not being bound, not about parameter count or type.
- **How to confirm:** If params were wrong, we’d typically see a different error (e.g. binding or conversion). Not observed.
- **Fix:** N/A.

### H3: SQL Server version / OFFSET-FETCH or reserved words

- **Why less likely:** OFFSET-FETCH is used in both branches; only the non-join branch fails. The message points to identifier binding.
- **Fix:** N/A.

## Most Likely Root Cause

**Inconsistent use of table alias in `list_by_aisle()`:**  
Conditions are built with the `p.` prefix for both code paths. The branch that joins `product_records` correctly uses `FROM positions p`, so `p.aisle_id` is valid. The branch that does not join uses `FROM positions` (no alias) but still uses `WHERE {where}` with `p.aisle_id`, so `p` is undefined and SQL Server raises "The multi-part identifier \"p.aisle_id\" could not be bound."

## Proposed Fix Plan (ordered)

1. **Fix SQL in the non-join branch** (done): Use `FROM positions p` and qualify all selected and ordered columns with `p.` so the same `where` string is valid. No change to params or to the join branch.
2. **Run existing tests:** Run `tests/infrastructure/repositories/` (and any integration tests that hit list_by_aisle) to ensure no regressions.
3. **Manual smoke test:** With SQL Server enabled, open an inventory → aisle → positions in the UI and confirm 200 and correct/empty list.

## Regression Prevention (tests + invariants)

- **Unit test for `list_by_aisle` without filters:** Add (or extend) a test that calls `list_by_aisle(aisle_id="...", page=1, page_size=25)` with no optional filters (no sku_filter, no status, no needs_review, no min_confidence) so the non-join branch is executed. Use an in-memory repo for fast tests; for SQL, use the existing SQL repository test harness if available.
- **Invariant:** In this repository, whenever a WHERE clause is built from a list of conditions that reference a table alias, every SQL variant (join vs non-join) that uses that WHERE must define that alias in the FROM clause.
- **Code review:** For any new or modified SQL that uses aliases, check that every branch that uses the same WHERE/conditions defines the same alias.

## Debug Checklist (runbook)

1. Reproduce: GET `/api/v3/inventories/{id}/aisles/{id}/positions` with SQL Server enabled and no positions (or with positions).
2. Confirm 500 and traceback pointing to `sql_position_repository.list_by_aisle` and `cur.execute(sql, params)`.
3. Check error message for "could not be bound" → indicates missing or wrong table/alias in FROM.
4. In `sql_position_repository.py`, compare both branches that build `sql`: ensure any alias used in `where` (e.g. `p`) appears in the FROM of that branch and SELECT/ORDER BY are consistent.
5. Apply fix (use alias `p` in non-join branch); run tests; re-test the endpoint.

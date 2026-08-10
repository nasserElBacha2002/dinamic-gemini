# Phase 3 — Migration validation (0072)

Archivo: `backend/src/database/migrations/versions/0072_inventory_jobs_lease_fencing.sql`  
Mirror: `backend/src/database/schema.sql` (bloque Phase 3 lease fencing + `GO` batches).

## Schema before

Tras Phase 1 (`0071`), `inventory_jobs` tiene `claim_owner_id` pero **no**:

- `lease_fencing_token`
- `lease_expires_at`
- `lease_acquired_at`
- índice `IX_inventory_jobs_lease_expiry`

Ownership de claim existe; no hay fencing/expiry de lease.

## Schema after

| Objeto | Definición |
|---|---|
| `lease_fencing_token` | `BIGINT NOT NULL` + `DF_inventory_jobs_lease_fencing_token DEFAULT (0)` |
| `lease_expires_at` | `DATETIME2 NULL` |
| `lease_acquired_at` | `DATETIME2 NULL` |
| `IX_inventory_jobs_lease_expiry` | NONCLUSTERED `(status, lease_expires_at)` WHERE `lease_expires_at IS NOT NULL` |

**Owner:** se reutiliza `claim_owner_id` (comentario explícito en migración: no columna `lease_owner_id`).

## Idempotency

Cada ALTER está envuelto en:

```sql
IF COL_LENGTH('inventory_jobs', '<col>') IS NULL
BEGIN
    ALTER TABLE ...
END
GO
```

Índice:

```sql
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE ... name = 'IX_inventory_jobs_lease_expiry')
BEGIN
    CREATE NONCLUSTERED INDEX ...
END
GO
```

Re-ejecutar 0072 es seguro (no-op si ya aplicado). `schema.sql` usa el mismo patrón `COL_LENGTH` / index existence.

## Rollout

1. Aplicar 0072 en order de migraciones (después de 0071).
2. Deploy código que SELECT/UPDATE columnas lease.
3. Defaults: filas existentes → `lease_fencing_token=0`, expiries NULL hasta primer claim Phase 3.
4. Validar con SQL IT `_require_lease_columns` + suite `test_sql_job_lease_fencing.py`.
5. Observar logs `job_lease_acquired` en nuevos claims.

## Rollback warning

Comentario formal en la migración (dev/test only):

```sql
ALTER TABLE inventory_jobs DROP COLUMN lease_fencing_token;
ALTER TABLE inventory_jobs DROP COLUMN lease_expires_at;
ALTER TABLE inventory_jobs DROP COLUMN lease_acquired_at;
```

**No dropear columnas con datos de producción** sin plan ops explícito (pérdida de fencing state, incompatibilidad con código deployado). Preferir rollback de **código** solo si se mantiene schema aditivo, o forward-fix.

Drop del índice filtrado antes de columnas si el engine lo requiere en el entorno concreto.

## Corrections (2026-07-28 UTC)
- Rollback SQL documented for dev/test only (DROP INDEX / CONSTRAINT / columns).
- Keep 0072 additive; reapply-safe via COL_LENGTH guards.

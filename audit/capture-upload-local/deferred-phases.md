# Local processing / CSV / security / tests — placeholders

Los siguientes documentos del brief quedan como **diseño aprobado, no implementado** en este PR:

| Documento | Estado |
|-----------|--------|
| `local-processing-architecture.md` | Diseño en auditoría previa; código no |
| `csv-export-schema.md` | Schema del brief; sin generador mobile |
| `csv-import-contract.md` | Endpoints no creados |
| `local-remote-reconciliation.md` | Política definida; sin UI/API |
| `security-review.md` | CSV injection / IDOR aplican a Fase 4–5 |
| `test-report.md` | Ver tests Fase 0–1 abajo |
| `migration-report.md` | v21 aditiva aplicada |
| `rollback-plan.md` | Flags + columnas nullable |

## Tests Fase 0–1 (pasados)

- `captureService.test.ts` — skip seguro, última foto MediaStore, doble submit, rollback, freeze
- `databaseMigrations.test.ts` — v21
- `uploadQueuePhase1Corrections.test.ts` — heal/orphan (previos + flags nuevas)
- `featureFlags.test.ts`
- `mobile typecheck` OK

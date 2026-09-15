# Final tenant coverage matrix (residual families)

Legend: Y = present; N = absent/unknown; P = partial; — = n/a

| Family | Dependency control | Use-case control | Repository scope | Parent-child check | Automated test | Estado |
|--------|--------------------|------------------|------------------|--------------------|----------------|--------|
| Clients list/get/create | Y JWT+policy | Y | Y list_for_client | — | Stage2 JWT/SQL | VERIFIED_FIXED (SEC-002) |
| Inventories list/get/soft-delete | Y | Y | Y scoped soft-delete | — | Stage2 JWT/SQL | VERIFIED_FIXED (SEC-001) |
| Inventories export (priority) | Y | P | P | P | Stage2 JWT export cases | PARTIAL |
| Aisles under inventory | Y inventory scope | P | P | Y inventory parent | Stage2 parent/child samples | PARTIAL |
| Jobs (v3 inventory_jobs) | P | P | P | P aisle/inventory | Worker suites (not tenant A/B) | PENDING |
| Artifacts / downloads | P | P | P | P | Observability capacity tests | PENDING_P0 |
| Aisle revisions | P | P | P | P | Unit/IT without A/B JWT | PENDING |
| Results / positions | P | P | P | P aisle | Merge IT; no A/B matrix | PENDING |
| Position override | P | P | P | P | Limited | PENDING |
| Retry / reprocess | P | P | P | P | Pipeline IT | PENDING |
| Server reprocess | P | P | P | P | — | PENDING |
| Analytics / admin | P platform | P | P | — | — | PENDING |
| Full HTTP DAST A/B | — | — | — | — | Not run | BLOCKED_BY_ENVIRONMENT |

P0/P1 tests added this correction wave focus on soft-delete atomicity and merge concurrency — not indiscriminate 140-route patches.

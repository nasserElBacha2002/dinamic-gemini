# Rollout y rollback — móvil

## Rollout progresivo

1. **Equipo técnico** — builds debug/internal; duración ≥ 3 días.
2. **Piloto interno** — 1–2 dispositivos campo; métricas upload/job.
3. **Un cliente** — volumen controlado; soporte dedicado.
4. **Grupo reducido** — 10–20% operadores.
5. **General** — tras checklist productivo firmado.

Criterios de éxito por etapa: 0 duplicados críticos, tasa upload ≥ umbral acordado, 0 ANR, jobs reconciliables.

## Rollback

| Capa | Acción |
|------|--------|
| App | Reinstalar versión anterior (versionCode menor); SQLite forward-compatible (no downgrade destructivo) |
| Feature flags | Desactivar HEIC convert / mobile data upload / WM schedule vía build |
| Backend | Sin cambio requerido para rollback app; flags servidor si existen |
| Polling/WM | Al abrir app antigua, jobs se leen; workers únicos se cancelan al update |

## Migraciones SQLite

Solo aditivas. No depender de downgrade de esquema.

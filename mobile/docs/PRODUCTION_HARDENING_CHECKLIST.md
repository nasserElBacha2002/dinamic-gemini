# Checklist productivo — Dinamic Captura

Marcar solo con evidencia.

## Bloqueantes producción

- [ ] Matriz física Android 12–14 aprobada
- [ ] DEVICE_EVIDENCE.md completo (20/100 fotos, offline, reboot, Doze)
- [ ] CI mobile verde en develop/main
- [ ] APK/AAB release firmados + checksums
- [ ] HTTPS-only en builds production
- [ ] Crash reporting activo en staging
- [ ] Runbook leído por soporte
- [ ] Rollback documentado y ensayado
- [ ] API key móvil sin privilegios críticos (o vacía)

## Código / automatización (Fase 3)

- [x] Auditoría inicial
- [x] Feature flags tipadas
- [x] Versionado metadata
- [x] Catálogo errores
- [x] Diagnóstico exportable
- [x] Health checks
- [x] FlatList fotos
- [x] Storage cleanup
- [x] CI mobile-validate
- [ ] WorkManager upload nativo completo
- [ ] ProGuard release validado
- [ ] E2E automatizado

## Firma

Checklist firmado por: ________ Fecha: ________  
Veredicto: producción | rollout limitado | bloqueada

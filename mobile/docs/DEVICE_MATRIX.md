# Matriz de dispositivos — Fase 3

Plantilla para evidencia física. Completar antes de marcar producción general.

## SDK / ABI

| Parámetro | Valor |
|-----------|--------|
| minSdkVersion | 24 |
| targetSdkVersion | 34 |
| compileSdkVersion | 34 |
| ABI | arm64-v8a, armeabi-v7a |
| Memoria mínima recomendada | 3 GB RAM |
| Almacenamiento libre mínimo | 1 GB (sesión típica) |

## Dispositivos piloto

| Fabricante | Modelo | Android | RAM | Evidencia | Firma |
|------------|--------|---------|-----|-----------|-------|
| Samsung | _TBD_ | 12/13/14 | | | |
| Motorola | _TBD_ | 12/13/14 | | | |
| Google Pixel | _TBD_ | 13/14/15 | | | |
| Xiaomi | _TBD_ | 12/13/14 | | Doc OEM batería | |

## Escenarios obligatorios (por dispositivo)

- [ ] 20 fotos
- [ ] 100 fotos
- [ ] Pantalla bloqueada + FGS
- [ ] Doze / Battery Saver
- [ ] Cambio de red / offline
- [ ] Reinicio app
- [ ] Reinicio dispositivo (cola al reabrir)
- [ ] Force stop (recuperación al abrir; no prometido en background)
- [ ] Poco espacio
- [ ] Token vencido
- [ ] Job fallido
- [ ] Dos pasillos (uno uploading, uno capture)

Ver también `DEVICE_EVIDENCE.md`.

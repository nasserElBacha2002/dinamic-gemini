# Evidencia de dispositivo — Fase 1

Completar después de la prueba física. Sin este archivo firmado, la Fase 1 queda
**parcialmente validada**.

## Dispositivo

| Campo | Valor |
|-------|-------|
| Fabricante | Samsung |
| Modelo | SM-G985F |
| Versión Android | 13 |
| Fecha de prueba | 2026-07-16 |
| Operador | Instalación automatizada desde Cursor |

## Evidencia ya registrada

- [x] `npm ci`
- [x] `npm run verify`
- [x] `npx expo prebuild -p android --clean`
- [x] `./gradlew assembleDebug`
- [x] `./gradlew installDebug` en dispositivo conectado
- [ ] `npm run doctor` OK para Android (el warning crudo de Xcode en `npx expo-doctor` es esperado en macOS con Xcode 26 + SDK 51; no bloquea Android)

## Escenario ejecutado

- [ ] Permiso solo fotografías (sin prompt de video)
- [ ] Login contra backend actual
- [ ] Listado de inventarios
- [ ] Listado de pasillos
- [ ] Marcar inicio
- [ ] Foreground Service / notificación visible
- [ ] 20 fotografías capturadas/copiadas
- [ ] Pantalla bloqueada durante parte del proceso
- [ ] Video `.mp4` agregado a la galería
- [ ] Video **no** aparece en la UI
- [ ] Contadores de fotos no afectados por el video
- [ ] 0 duplicados
- [ ] Estabilidad aplicada (ninguna confirmada sin estabilizar)
- [ ] Finalizar captura
- [ ] Revisión y exclusión/reincorporación
- [ ] Cerrar/reabrir app y recuperar sesión
- [ ] Notificación FGS desaparece

## Métricas

| Métrica | Valor |
|---------|-------|
| Duración total | |
| Eventos de galería | |
| Scans ejecutados | |
| Fotos detectadas | |
| Fotos estables | |
| Inestables / undecodable | |
| Rechazos core (defensa) | |
| Duplicados | |
| Assets leídos (último scan) | |
| Assets hidratados (último scan) | |
| Comportamiento con pantalla bloqueada | |

## Notas / fallos

_

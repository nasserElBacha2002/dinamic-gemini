# Alternativas — Procesamiento / aceleración del flujo móvil

**Referencia:** evidencia en `mobile-local-processing-audit.md`

---

## Matriz comparativa (1–5; mayor = mejor, excepto Complejidad/Riesgo donde 5 = peor)

| Criterio | A Upload opt. | B CODE_SCAN local | C OCR local | D Pipeline local | E Híbrido | F Core compartido | G Runtime embebido |
|----------|---------------|-------------------|-------------|------------------|-----------|-------------------|--------------------|
| Mejora velocidad | 4 | 3 | 2 | 2 | 4 | 2 | 1 |
| Complejidad (↓mejor) | 2 | 3 | 5 | 5 | 4 | 4 | 5 |
| Riesgo (↓mejor) | 2 | 3 | 5 | 5 | 3 | 3 | 5 |
| Reutilización | 3 | 4 | 1 | 1 | 4 | 5 | 2 |
| Mantenimiento | 4 | 3 | 1 | 1 | 3 | 3 | 1 |
| Seguridad | 4 | 3 | 2 | 1 | 3 | 4 | 1 |
| Offline | 2 | 4 | 4 | 5 | 4 | 3 | 3 |
| Batería/memoria | 4 | 3 | 1 | 1 | 3 | 4 | 1 |
| Compatibilidad | 5 | 4 | 2 | 1 | 4 | 4 | 1 |
| Impacto backend | 3 | 3 | 2 | 1 | 3 | 2 | 1 |
| Divergencia (↓mejor) | 5 | 3 | 1 | 1 | 3 | 4 | 2 |
| Observabilidad | 3 | 3 | 2 | 2 | 4 | 3 | 1 |
| Rollback | 5 | 4 | 3 | 2 | 4 | 3 | 1 |
| Tiempo impl. | 5 | 3 | 1 | 1 | 3 | 2 | 1 |
| **Score relativo** | **Alto** | **Medio-alto** | **Bajo** | **Muy bajo** | **Alto (con A+B)** | **Medio (habilitador)** | **Descartado** |

---

## Alternativa A — Optimizar únicamente la carga existente

### Qué implica
- Tope de dimensión proactivo (usar `DEFAULT_MAX_DIMENSION_PX`).
- JPEG/WebP adaptativo según red/batería.
- Subida concurrente adaptativa (2–4 en Wi-Fi).
- WorkManager / FGS real para drenar cola upload.
- Opcional: **signed PUT** a object storage (endpoint aditivo).
- Chunked/resumable (tus/S3 multipart) para archivos grandes.
- Dedup por hash (persistir SHA-256 actualmente descartado).
- Thumbnails primero + original diferido (si auditoría lo permite).

### Ventajas
- Ataca el cuello de botella evidenciado.
- No toca pipeline CODE_SCAN/OCR/LLM.
- Rollback trivial (feature flags).
- Bajo riesgo de divergencia de resultados.

### Desventajas
- No da resultados sin red.
- No evita OCR/LLM cuando el upload ya terminó.

### Esfuerzo / riesgo
- Medio-bajo / bajo-medio (signed URL es el cambio backend más grande).

### Seguridad
- Signed URLs con TTL corto, scope por aisle/asset, auth previa.
- No secretos de storage en el APK.

### Veredicto
**Obligatoria como Fase 0–1.** Base de cualquier estrategia posterior.

---

## Alternativa B — CODE_SCAN local

### Qué implica
- SDK barcode/QR on-device (p.ej. ML Kit / ZXing).
- Reutilizar grammar: `parse_inventory_code_payload` / `EncodedLabelPayloadParser` vía **contract tests** o port TypeScript del parser puro.
- Resultado preliminar: code ± quantity.
- Política de upload: siempre subir evidencia (auditoría) o diferir originales si resuelto.

### Ventajas
- Alta tasa de resolución en etiquetas encodeadas.
- CPU liviana vs OCR.
- Contratos de payload ya existen y son deterministas (Python puro).
- Encaja con modos que la UI ya envía (`CODE_SCAN`).

### Desventajas
- No resuelve etiquetas solo-texto (caso INTERNAL_OCR / fallback LLM).
- Requiere sync de resultados + validación servidor.
- SDK nativo + permisos + tests de dispositivo.

### Esfuerzo / riesgo
- Medio / medio (sync + autoridad servidor).

### Veredicto
**Recomendada como Fase 2** tras métricas de upload.

---

## Alternativa C — OCR local

### Qué implica
- Motor on-device distinto al Tesseract/INTERNAL_OCR del servidor.
- Preprocesamiento, orientación, crops, perfiles por cliente.

### Ventajas
- Offline parcial para texto.
- Menos dependencia de INTERNAL_OCR remoto.

### Desventajas
- **Divergencia casi segura** vs OCR servidor (precisión, anchors, perfiles).
- Memoria/batería/térmica en S10+ con lotes grandes.
- Mantenimiento de dos pipelines.
- El caso real reciente (códigos LLM sin cantidad) muestra que incluso vision models fallan en qty — OCR local no garantiza mejora.

### Esfuerzo / riesgo
- Alto / alto.

### Veredicto
**No recomendada en horizonte cercano.** Solo experimento controlado si métricas demuestran % alto de UNRECOGNIZED por OCR remoto en etiquetas no encodeadas.

---

## Alternativa D — Pipeline local completo

### Qué implica
Replicar preprocess + CODE_SCAN + OCR + reglas + estados + sync.

### Ventajas
- Máximo offline teórico.

### Desventajas
- Duplica `AisleProcessingOrchestrator`, validadores, fallback LLM (imposible offline seguro).
- Costo de mantenimiento prohibitive.
- Viola restricción de no convertir móvil en dependencia del flujo.

### Veredicto
**Descartada.**

---

## Alternativa E — Procesamiento híbrido

### Qué implica
1. Intentar local (CODE_SCAN).
2. Sync resultados livianos primero.
3. Upload evidencia en background.
4. Assets no resueltos → `POST .../process` servidor (pipeline intacto).
5. Review solo en web.

### Ventajas
- Combina ROI de A + B.
- Servidor permanece autoridad y fallback completo.
- Compatible con restricción crítica.

### Desventajas
- Dos caminos de ingestión de resultados (requiere endpoints aditivos + idempotencia).
- Complejidad de estados (local vs accepted vs server-reprocessed).

### Esfuerzo / riesgo
- Medio-alto / medio (si se fasea bien).

### Veredicto
**Estrategia objetivo** = A primero + B dentro de E, sin C/D/G.

---

## Alternativa F — Núcleo compartido

### Qué implica
Extraer parsers/enums/policies a paquete neutro o **JSON Schema + contract tests** (móvil TS / backend Python).

### Opciones técnicas evaluadas

| Opción | Fit | Notas |
|--------|-----|-------|
| OpenAPI / JSON Schema + contract tests | **Alto** | Ya hay contratos v3; bajo costo |
| Paquete TS compartido (monorepo) | Medio | Móvil ya TS; backend no lo consume |
| Port manual del QR parser a TS + golden tests | **Alto** | Grammar pequeña y estable |
| Kotlin Multiplatform | Bajo | Solo Android hoy; overkill |
| Rust / C++ / WASM | Bajo | Complejidad nativa innecesaria para QR grammar |
| Copiar Python a RN | Nulo | No viable |

### Veredicto
**Habilitador**, no producto. Empezar con contract tests + port TS del parser QR; no KMP/WASM.

---

## Alternativa G — Runtime Python / servicio embebido

### Qué implica
Chaquopy / termux-like / microservicio local corriendo parte del backend.

### Desventajas
- Tamaño APK, seguridad, updates, debugging, OEM kills.
- Acoplamiento extremo.

### Veredicto
**Descartada** (alto riesgo, sin evidencia a favor en este repo).

---

## Descartadas vs retenidas

| Alternativa | Decisión |
|-------------|---------|
| A | **Retener — Fase 0–1** |
| B | **Retener — Fase 2** |
| C | Descartar (corto plazo) |
| D | Descartar |
| E | **Retener como arquitectura objetivo (A+B)** |
| F | Retener como disciplina de contratos |
| G | Descartar |

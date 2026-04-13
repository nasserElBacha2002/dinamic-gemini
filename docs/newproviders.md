# Plan de implementación

## Objetivo general

Dejar el sistema preparado para operar con **4 providers reales**:

* OpenAI
* Gemini
* Claude
* DeepSeek

sin `fake`, con una capa de prompts modular, trazable y escalable, y con una estrategia de tests que ya no dependa de un provider ficticio.

---

# Fase 0 — Definiciones y criterios de salida

Antes de tocar código, definí estas reglas de arquitectura:

### Decisiones a cerrar

* `fake` **sale completamente** del producto, API pública, settings, catálogos y frontend.
* Los tests dejarán de usar `fake` como provider registrado y pasarán a usar **test doubles al nivel executor**.
* La arquitectura de prompts migrará desde un único módulo centralizado a un esquema con:

  * núcleo semántico,
  * overlays por provider,
  * bloques de enriquecimiento,
  * composer central.
* Claude y DeepSeek serán **first-class providers**, no hacks.
* Toda ejecución relevante deberá poder responder:

  * qué provider corrió,
  * qué modelo,
  * qué profile de prompt,
  * qué composición/versionado de prompt se usó.

### Exit criteria

* Documento corto de decisiones aprobado.
* Orden de migración fijado:

  1. test harness,
  2. remoción de fake,
  3. composer de prompts,
  4. nuevos providers.

---

# Fase 1 — Reemplazo del `fake` por una estrategia de testing correcta

## Objetivo

Eliminar la dependencia conceptual de `fake` sin romper cobertura.

## Problema actual

Hoy `fake` no es solo scaffolding: está metido en registry, settings, API, catálogos y tests. Además, te da respuestas JSON “perfectas”, lo cual oculta problemas reales de parseo y normalización .

## Implementación

Crear un **TestLLMExecutor** o equivalente, pero solo en tests.

### Qué hacer

* Crear un test double que implemente `LlmGlobalAnalysisExecutor`.
* Permitir que devuelva:

  * `structured_output` válido,
  * `raw_text` controlado,
  * errores simulados,
  * outputs con variaciones útiles para tests.
* Mover los tests que hoy usan `provider_name="fake"` a una estrategia basada en:

  * patch de `resolve_llm_executor`,
  * fixture executor,
  * o monkeypatch del punto de resolución.

### Qué no hacer

* No registrar este executor como provider real.
* No exponerlo en API.
* No dejarlo en `src/` como parte de arquitectura productiva.

## Entregables

* `tests/conftest.py` o módulo de fixtures con executor de prueba.
* Guía corta de cómo usarlo en unit/integration tests.

## Exit criteria

* Existe una vía estable para correr tests sin red y sin `fake`.
* Los tests más importantes ya no dependen del provider ficticio.

---

# Fase 2 — Migración de tests fuera de `fake`

## Objetivo

Dejar la suite desacoplada del provider ficticio antes de borrarlo.

## Implementación

Migrar por capas.

### Subfase 2.1 — Tests backend del pipeline

Prioridad alta para tests que hoy dependen de `fake`:

* smoke tests del hybrid pipeline,
* tests de processing resolution,
* tests de aisle processing,
* tests de lifecycle/status,
* tests de prompt profiles que usan `"fake"`.

### Subfase 2.2 — Tests de normalización

Agregar casos que hoy `fake` no cubre:

* JSON envuelto en markdown,
* JSON parcial,
* aliases de keys,
* tipos inconsistentes,
* campos faltantes,
* errores de parseo.

### Subfase 2.3 — Frontend tests

Actualizar mocks de `processing-provider-options` y cualquier selector/provider list para que dejen de incluir `fake` .

## Exit criteria

* La suite corre completa sin depender de `fake`.
* Los tests nuevos cubren “ugliness” real de providers.

---

# Fase 3 — Remoción completa del `fake provider`

## Objetivo

Eliminar la deuda técnica estructural.

## Implementación

### Backend

Remover `fake` de:

* registry / `_KNOWN_KEYS`,
* resolution,
* processing catalogs,
* `processing-provider-options`,
* validators de settings (`llm_provider`),
* `get_llm_provider`,
* `fake_llm_fixture_path`,
* cualquier bridge transicional asociado.

### Cleanup estructural

Eliminar:

* `FakeProvider`,
* `TransitionalLlmProviderBridgeExecutor`,
* `TRANSITIONAL_LLM_PROVIDER_BRIDGE_KEYS` si queda vacío,
* docs de uso local con `LLM_PROVIDER=fake`.

### Frontend

* Quitar `fake` de mocks,
* evitar cualquier label o selector legado,
* confirmar que solo se muestran providers reales.

### Datos / fixtures

* revisar seeds, fixtures o jobs de staging con `provider_name="fake"`.

## Riesgos

* romper flujos dev/CI si la migración de tests no quedó bien.
* dejar paths muertos ligados al bridge transicional.

## Exit criteria

* `fake` ya no existe como provider real en ninguna superficie pública.
* Todo sigue corriendo con OpenAI/Gemini.
* CI verde.

---

# Fase 4 — Diseño e introducción del Prompt Composer con paridad exacta

## Objetivo

Modularizar prompts sin cambiar todavía el comportamiento observable.

## Problema actual

El archivo actual mezcla:

* prompt semántico,
* variantes por provider,
* enriquecimientos,
* resolución,
* perfiles híbridos,
  y solo modela en serio `default` y `openai` .

## Diseño objetivo

### Capas recomendadas

1. **Semantic core**
   Qué debe hacer el modelo.

2. **Profile behavior**
   Ejemplo: `global_v21` vs `global_v21_b`.

3. **Provider policy**
   Ajustes por provider: OpenAI, Gemini, Claude, DeepSeek.

4. **Output enforcement**
   Reglas de JSON/schema.

5. **Enrichments**
   image_ids, product-label association, otros bloques.

6. **Composer**
   Une todo y devuelve:

   * texto final,
   * fragmentos usados,
   * hash/id de composición.

## Implementación

Introducir un `compose_hybrid_prompt(...)` que replique exactamente la salida actual para:

* `global_v21` + gemini/default
* `global_v21` + openai
* `global_v21_b` + gemini/default
* `global_v21_b` + openai

## Muy importante

Primero paridad exacta, después mejora estructural.

## Entregables

* composer inicial,
* golden tests de strings,
* resolución central única.

## Exit criteria

* El composer genera exactamente lo mismo que hoy para OpenAI y Gemini.
* Nadie más arma prompts “por afuera”.

---

# Fase 5 — Unificación real del armado de prompts

## Objetivo

Evitar que convivan múltiples fuentes de verdad.

## Implementación

* Hacer que `HybridGlobalAnalysisStrategy` use solo el composer.
* Eliminar o deprecar accesos directos al viejo `PROMPTS` dict para paths híbridos.
* Revisar los fallbacks de adapters para que nunca rehagan prompts de forma inconsistente.
* Conectar formalmente `enrich_prompt_with_product_label_association` dentro del flujo correcto, si efectivamente debe ser parte del prompt base; hoy aparece definido pero con wiring ambiguo según el análisis .

## Exit criteria

* Hay una sola fuente de verdad para el prompt final.
* No existe divergencia entre strategy, adapters y tests.

---

# Fase 6 — Persistencia y trazabilidad de composición de prompts

## Objetivo

Poder auditar realmente resultados multi-provider.

## Implementación

Persistir por ejecución o job:

* `provider_name`
* `model_name`
* `prompt_key` / profile
* `prompt_version` o `prompt_composition_hash`
* fragmentos aplicados
* metadata útil en artifacts/logs

### Impacto esperado

Actualizar:

* `run_metadata.json`
* `execution_log.jsonl`
* `hybrid_report.json`

Y eventualmente DTOs/API si querés exponerlo.

## Exit criteria

* Toda ejecución puede reconstruir qué prompt exacto se usó.
* Benchmarking provider × prompt deja de ser opaco.

---

# Fase 7 — Normalización endurecida para providers reales

## Objetivo

Preparar la capa de salida para Claude y DeepSeek.

## Implementación

Definir responsabilidades claras:

* **adapter**: garantizar extracción de JSON parseable,
* **normalizer**: aliasing y limpieza estructural,
* **schema validation**: validación canónica final.

### Qué agregar

* helpers compartidos para extracción de JSON,
* preprocessors provider-specific si hace falta,
* más tests con outputs imperfectos.

## Exit criteria

* La capa de normalización ya no asume solo OpenAI/Gemini.
* Está lista para casos nuevos sin ensuciar el core.

---

# Fase 8 — Incorporación de Claude

## Objetivo

Agregar el tercer provider real sobre una base ya limpia.

## Implementación

Agregar:

* adapter/executor Claude,
* settings/config,
* catálogo de modelos,
* labels en provider options,
* provider policy en prompt composer,
* tests de integración y parsing,
* metadata y logs consistentes.

## Recomendación

Claude probablemente necesite atención especial a:

* separación system/user,
* disciplina de output,
* parseo de respuestas verbosas.

## Exit criteria

* Claude corre como provider first-class.
* Se puede lanzar, comparar y auditar igual que OpenAI/Gemini.

---

# Fase 9 — Incorporación de DeepSeek

## Objetivo

Agregar el cuarto provider real.

## Implementación

Evaluar primero si DeepSeek entra como:

* adapter nativo,
* o variante OpenAI-compatible con configuración distinta.

Luego repetir:

* registry,
* settings,
* catálogo,
* policy de prompt,
* tests,
* trazabilidad.

## Exit criteria

* DeepSeek queda integrado sin hacks.
* El sistema ya opera con 4 providers reales.

---

# Fase 10 — Ajustes de frontend, observabilidad y UX multi-provider

## Objetivo

Cerrar la historia completa de producto.

## Implementación

### Frontend

* selectors solo con providers reales,
* compare runs con labels claros de provider/model/prompt,
* visibilidad de `prompt_key` y eventualmente `prompt_version`,
* limpieza de copy Gemini-shaped.

### Execution log

Alinear evento de backend y frontend:

* usar contrato genérico tipo `analysis_request`,
* soportar legado solo si hace falta durante transición.

### Analytics

Preparar vistas para comparar:

* provider,
* modelo,
* prompt profile,
* más adelante prompt version.

## Exit criteria

* El producto refleja correctamente el sistema de 4 providers.
* No quedan sesgos ni nombres heredados de Gemini/fake.

---

# Fase 11 — Cleanup final y endurecimiento

## Objetivo

Cerrar la migración.

## Implementación

* borrar código legacy remanente,
* revisar módulos huérfanos,
* actualizar documentación,
* limpiar métricas antiguas,
* revisar naming vendor-specific en artifacts.

## Exit criteria

* no quedan conceptos transicionales,
* arquitectura consistente,
* documentación al día.

---

# Orden recomendado de implementación

Este es el orden que te recomiendo seguir sí o sí:

## Camino recomendado

1. **Fase 1** — test harness sin fake
2. **Fase 2** — migración de tests
3. **Fase 3** — remover fake
4. **Fase 4** — prompt composer con paridad
5. **Fase 5** — unificación real del armado de prompts
6. **Fase 6** — trazabilidad/versionado de prompts
7. **Fase 7** — endurecer normalización
8. **Fase 8** — Claude
9. **Fase 9** — DeepSeek
10. **Fase 10** — frontend/observabilidad
11. **Fase 11** — cleanup final

---

# Riesgos principales

## 1. Sacar fake demasiado pronto

Podés romper CI y quedarte sin harness confiable.

## 2. Modularizar prompts sin golden tests

Podés cambiar comportamiento sin darte cuenta.

## 3. Agregar providers antes de cerrar prompt traceability

No vas a poder auditar diferencias reales.

## 4. Dejar metadata vendor-shaped

Después cuesta mucho generalizar.

## 5. No reforzar tests de parsing real

Vas a reemplazar un problema visible por uno invisible.

---

# Resultado esperado al final

Vas a pasar de esto:

* OpenAI
* Gemini
* Fake
* prompts semi-centralizados
* tests apoyados en provider ficticio

a esto:

* OpenAI
* Gemini
* Claude
* DeepSeek
* sin fake
* prompts modulares y versionables
* tests desacoplados del registry productivo
* mejor trazabilidad y benchmarking real

---

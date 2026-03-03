# Sprint 6B — Re-ID Integration & Robustness — Backlog

Objetivo: integrar Re-ID (pHash/CLIP + DSU merge) detrás de `REID_ENABLED=False` por defecto, con historias entregables una a una.

Flujo Re-ID (según plan): **después de tracking y ROI+blur**, **antes de view selection**.
`build_track_signatures` → `generate_candidates` (gating) → `filter_with_phash` → `verify_with_clip` → `merge_tracks_dsu`.

---

## US-6B.1 — Flag y paquete Re-ID (infraestructura mínima) ✅ PRIMERA ENTREGA

**Como** desarrollador, **quiero** tener el flag `REID_ENABLED` (default False) y el paquete `src/reid/` con módulos stub **para** integrar Re-ID por historias sin romper el MVP.

**Criterios de aceptación**
- CA.1: Existe `REID_ENABLED` en config (default False) y opción CLI `--reid-enabled` (solo con `--track-pipeline`).
- CA.2: Existe `src/reid/` con `__init__.py`, `signature.py`, `gating.py`, `phash.py`, `clip_embedder.py`, `merge.py` con funciones stub que devuelven valores seguros (sin lógica real).
- CA.3: Con `REID_ENABLED=False` el pipeline no ejecuta ninguna lógica Re-ID.
- CA.4: Con `REID_ENABLED=True` el orquestador llama a la etapa Re-ID; por ahora devuelve los mismos tracks (passthrough) y rellena métricas: `tracks_before_reid`, `tracks_after_reid`, `tracks_merged_count`, `reid_candidates_generated`, `clip_verifications_run`.
- CA.5: Tests: (1) con Re-ID desactivado no se llama a módulos Re-ID; (2) con Re-ID activado passthrough devuelve mismos tracks y métricas coherentes.

**Archivos impactados**
- `src/config.py` (nuevo `reid_enabled`)
- `src/app.py` (arg `--reid-enabled`, pasar a `run_pipeline`)
- `src/pipeline/orchestrator.py` (rama Re-ID después de ROI+blur, antes de view selection)
- `src/reid/__init__.py`, `signature.py`, `gating.py`, `phash.py`, `clip_embedder.py`, `merge.py` (nuevos, stubs)
- `pyproject.toml` (incluir paquete `src.reid`)
- `tests/test_reid.py` (nuevo)

**Riesgos**
- Bajo: solo wiring y stubs.

**Tests sugeridos**
- `test_reid_disabled_no_calls`: mock de reid; con reid_enabled=False no se invoca run_reid.
- `test_reid_passthrough_returns_same_tracks`: con reid_enabled=True, run_reid devuelve mismos tracks y summary con tracks_before_reid == tracks_after_reid, tracks_merged_count == 0.

**DoD**
- Código compila; tests pasan; se puede activar con `--reid-enabled` o env; métricas Re-ID visibles en summary cuando está activo.

**PR checklist (US-6B.1)**
- [ ] `ruff check src/reid src/config.py src/app.py src/pipeline/orchestrator.py tests/test_reid.py tests/test_pipeline.py`
- [ ] `pytest tests/test_reid.py tests/test_pipeline.py -v --no-cov`
- [ ] Sin `--reid-enabled`, pipeline no llama a Re-ID.
- [ ] Con `--track-pipeline --reid-enabled`, log "Re-ID habilitado" y métricas en summary.

**Comandos para correr tests (US-6B.1)**
```bash
# desde repo
./venv/bin/python -m pytest tests/test_reid.py tests/test_pipeline.py -v --no-cov
```

---

## US-6B.2 — Firma por track (signature_k ROIs + pHash) ✅ IMPLEMENTADA

**Como** desarrollador, **quiero** construir una firma por track con `signature_k` mejores ROIs (blur + área + diversidad temporal) y pHash por ROI **para** poder comparar tracks en Re-ID.

**Criterios de aceptación**
- CA.1: `build_track_signatures(tracks, signature_k)` devuelve un dict `track_id -> TrackSignature` con phashes y metadata por track.
- CA.2: TrackSignature incluye: track_id, roi_phashes (hex), roi_paths, signature_k, start_frame/end_frame opcionales.
- CA.3: Dependencia `imagehash` + PIL en pyproject; selección determinista (blur desc, area desc, frame_idx asc).

**Archivos impactados**
- `src/reid/signature.py` (TrackSignature, compute_phash, build_track_signatures)
- `src/reid/__init__.py` (llamada a build_track_signatures, reid_signatures en metrics)
- `src/config.py` (reid_signature_k)
- `pyproject.toml` (imagehash)
- `tests/test_reid.py` (test_signatures_empty_when_no_rois, test_signatures_k_selection_deterministic, test_phash_stable_for_same_image, test_phash_diff_for_diff_images)

**DoD**
- Tests unitarios con tracks con roi_path; firmas generadas; pHash estable/distinto; reid_signatures en pipeline_debug cuando Re-ID activo.

**Comandos para correr tests (US-6B.2)**
```bash
./venv/bin/python -m pytest tests/test_reid.py -v
# Con pipeline y Re-ID (passthrough con firmas en debug):
# python -m src.app <video> --track-pipeline --heuristic --reid-enabled
```

---

## US-6B.3 — Gating temporal y espacial ✅ IMPLEMENTADA

**Como** desarrollador, **quiero** generar candidatos a merge solo entre tracks que cumplan gate temporal (gap ≤ max_gap_frames) y espacial (dx ≤ dx_max, dy ≤ dy_max) **para** reducir pares inviables antes de pHash/CLIP.

**Criterios de aceptación**
- CA.1: `generate_candidates(signatures, max_gap_frames, dx_max, dy_max)` devuelve lista de pares (track_id_a, track_id_b) con orden canónico (min_id, max_id).
- CA.2: Config REID_MAX_GAP_FRAMES (default 240), REID_DX_MAX (0.20), REID_DY_MAX (0.25).
- CA.3: TrackSignature extendido con start_centroid y end_centroid (normalizados 0..1); build_track_signatures recibe frame_width/frame_height opcionales; run_reid_passthrough recibe video_width/video_height y expone reid_candidates y reid_candidates_generated en pipeline_debug.

**Archivos impactados**
- `src/reid/signature.py` (start_centroid, end_centroid; build_track_signatures con frame_width/height)
- `src/reid/gating.py` (generate_candidates real: gap en frames, espacial con centroides)
- `src/reid/__init__.py` (llamada a generate_candidates; reid_candidates en metrics)
- `src/config.py` (reid_max_gap_frames, reid_dx_max, reid_dy_max)
- `src/pipeline/orchestrator.py` (pasa video_width/video_height a run_reid_passthrough; log candidates)
- `tests/test_reid.py` (test_gating_* y test_no_duplicate_pairs)

**DoD**
- Tests: gating_empty_when_insufficient_meta, temporal_within/outside_gap, spatial_within/outside_threshold, no_duplicate_pairs. pipeline_debug.reid_candidates y reid_candidates_generated visibles con --reid-enabled.

**Comandos para correr tests (US-6B.3)**
```bash
./venv/bin/python -m pytest tests/test_reid.py -v
# Con pipeline: python -m src.app <video> --track-pipeline --heuristic --reid-enabled
# Ver pipeline_debug.reid_candidates y reid_candidates_generated en summary/resultado.
```

---

## Post-6B.3 improvements (PR pequeño) ✅

Mejoras de correctitud y estabilidad sobre US-6B.2 y US-6B.3, sin implementar US-6B.4/5/6.

**Cambios realizados:**

1. **Fix summary requests_sent:** `_make_summary` recibe `requests_sent` como parámetro explícito (keyword-only); el orchestrator pasa `requests_sent=tracks_requests_sent`. Se eliminó el hardcode `requests_sent: tracks_analyzed`. Test: `test_make_summary_requests_sent_equals_tracks_requests_sent` y aserción en test de Re-ID de que `summary["requests_sent"] == pipeline_debug["tracks_requests_sent"]`.

2. **build_track_signatures: start/end solo con ROIs válidas:** `frames_used` se construye solo con los `frame_idx` de observaciones cuyo `compute_phash` devolvió valor (ROI existente). Si no hay ROIs válidas, fallback a `track.start_frame` / `track.end_frame`. Tests: `test_signatures_start_end_fallback_when_no_valid_roi`, `test_signatures_start_end_only_from_valid_rois`.

3. **Gating gap==0 más estricto:** Con solapamiento (gap=0) se exige simetría: ambas direcciones espaciales (endA->startB y endB->startA) deben pasar el umbral (AND). Tests: `test_gating_gap_zero_requires_both_directions`, `test_gating_gap_zero_both_directions_ok`.

4. **Prefiltro n>500:** El bucketing considera `start_frame` y `end_frame`: se construyen `by_start` y `by_end` por bucket; los pares a revisar son los que relacionan start de uno con end del otro en buckets adyacentes (y viceversa), reduciendo falsos negativos.

5. **compute_phash robustez:** Se usa `img.convert("RGB").copy()` para calcular el hash sobre una copia y no depender del archivo abierto.

**Checklist Post-6B.3:**
- [x] `pytest tests/test_reid.py -v`
- [x] `pytest tests/test_pipeline.py -v --no-cov`
- [x] `summary["requests_sent"]` refleja `tracks_requests_sent`
- [x] start/end de firma solo con ROIs con phash válido
- [x] gap=0 exige ambas direcciones espaciales
- [x] Bucketing n>500 usa start y end

**Comandos:**
```bash
./venv/bin/python -m pytest tests/test_reid.py -v
./venv/bin/python -m pytest tests/test_pipeline.py -v --no-cov
```

---

## US-6B.4 — Filtro pHash (Hamming ≤ max_dist)

**Como** desarrollador, **quiero** filtrar candidatos con distancia Hamming de pHash ≤ max_dist **para** reducir llamadas a CLIP.

**Criterios de aceptación**
- CA.1: `filter_with_phash(candidates, signatures, max_dist)` devuelve sublista de pares que pasan (min Hamming entre ROIs del par ≤ max_dist).
- CA.2: Config `PHASH_MAX_DIST` (default 10).

**Archivos impactados**
- `src/reid/phash.py` (implementación)
- `src/config.py` (PHASH_MAX_DIST)
- `tests/test_reid.py`

**Riesgos**
- Bajo.

**DoD**
- Tests con hashes sintéticos; pares filtrados correctamente.

---

## US-6B.5 — Verificación CLIP (interfaz + stub/capa adaptable) ✅ IMPLEMENTADA

**Como** desarrollador, **quiero** una capa `verify_with_clip` con interfaz definida y stub/mock por defecto **para** no bloquear el sprint si CLIP no está disponible (GPU/costo).

**Criterios de aceptación**
- CA.1: `verify_with_clip(candidates, signatures, min_sim)` devuelve lista de pares confirmados; contrato claro (entrada: candidatos + firmas; salida: pares (id_a, id_b)).
- CA.2: Implementación stub que devuelve lista vacía cuando `embedder=None` (nunca confirma merge); tests con mocks.
- CA.3: Parámetro opcional `embedder: Optional[Callable[[str], List[float]]]`; si se pasa, se usa primer roi_path por track, cosine_similarity >= min_sim confirma. Config `clip_min_sim` (default 0.92).

**Archivos impactados**
- `src/reid/clip_embedder.py` (verify_with_clip + cosine_similarity + _roi_paths_from_sig; embedder opcional)
- `src/config.py` (clip_min_sim, env CLIP_MIN_SIM)
- `tests/test_reid.py` (test_verify_with_clip_stub_returns_empty, confirms_when_similarity_high, confirms_with_dict_signatures, rejects_when_similarity_low, skips_when_missing_roi_paths, maintains_order)

**DoD**
- Interfaz estable; stub (embedder=None) devuelve []; tests pasan sin GPU.

**Comandos para correr tests (US-6B.5)**
```bash
./venv/bin/python -m pytest tests/test_reid.py -v --no-cov
```

---

## US-6B.6 — Merge DSU (Union-Find determinista) ✅ IMPLEMENTADA

**Como** desarrollador, **quiero** fusionar tracks con Union-Find a partir de pares confirmados, con orden temporal consistente **para** obtener MergedTrack sin doble conteo.

**Criterios de aceptación**
- CA.1: `merge_tracks_dsu(tracks, confirmed_pairs)` devuelve lista de tracks fusionados (cada uno con observaciones concatenadas, ordenadas por frame_idx/bbox y deduplicadas por (frame_idx, bbox); start_frame/end_frame recalculados).
- CA.2: Track fusionado = PalletTrack con track_id = min(componente); compatible con view selection y Gemini.
- CA.3: Orden determinista: pares normalizados (min_id, max_id); salida ordenada por (start_frame, end_frame, track_id). Pares con track_id inexistente se ignoran.

**Archivos impactados**
- `src/reid/merge.py` (DSU con path compression, _merge_observations con dedup por (frame_idx, bbox))
- `tests/test_reid.py` (test_merge_tracks_dsu_no_pairs_returns_same, merges_two_tracks, transitive_merge, ignores_unknown_track_ids, deduplicates_exact_same_obs, output_sorted_deterministic)

**Riesgos**
- Bajo; cuidado con identidad de track_id del merged (menor id del componente).

**DoD**
- Tests: 3 tracks, 2 pares (A-B, B-C) → 1 merged; dedup de obs idénticas; salida ordenada.

**Comandos para correr tests (US-6B.6)**
```bash
./venv/bin/python -m pytest tests/test_reid.py -v --no-cov
```

---

## US-6B.7 — Integración Re-ID en pipeline (flujo completo) ✅ IMPLEMENTADA

**Como** desarrollador, **quiero** que con `REID_ENABLED=True` el pipeline ejecute firma → gating → phash → clip → merge y use los tracks fusionados para view selection y Gemini **para** reducir doble conteo en producción.

**Criterios de aceptación**
- CA.1: Con Re-ID activo, después de ROI+blur se ejecutan en orden: build_track_signatures, generate_candidates, filter_with_phash, verify_with_clip, merge_tracks_dsu; el resultado reemplaza `tracks` antes de view selection.
- CA.2: Métricas en summary y pipeline_debug: tracks_before_reid, tracks_after_reid, tracks_merged_count, reid_candidates_generated, reid_pairs_after_phash, reid_pairs_confirmed, clip_verifications_run, reid_merge_map.
- CA.3: Log por etapa (candidatos, pairs_after_phash, pairs_confirmed). En caso de excepción: log warning y devolver tracks originales con reid_error en métricas.

**Archivos impactados**
- `src/reid/__init__.py` (run_reid_pipeline completo; run_reid_passthrough como alias)
- `src/reid/merge.py` (get_merge_map para pipeline_debug)
- `src/pipeline/orchestrator.py` (run_reid_pipeline; summary con reid_pairs_after_phash, reid_pairs_confirmed)
- `tests/test_pipeline.py` (test_run_pipeline_reid_full_flow_no_merges; tests con run_reid_pipeline mock)
- `tests/test_reid.py` (test_run_reid_pipeline_with_merge)

**DoD**
- Pipeline con --reid-enabled y stub CLIP termina; métricas presentes; tests de integración.

**Comandos**
```bash
./venv/bin/python -m pytest tests/test_reid.py tests/test_pipeline.py -v --no-cov
# Manual: revisar métricas Re-ID
# python -m src.app <video> --track-pipeline --heuristic --reid-enabled
# Revisar en summary/resultado: reid_candidates_generated, reid_pairs_after_phash, reid_pairs_confirmed, tracks_merged_count, reid_merge_map
```

**Keys en summary y pipeline_debug cuando reid_enabled=True**

| Key | Descripción |
|-----|-------------|
| `tracks_before_reid` | Número de tracks antes del merge. |
| `tracks_after_reid` | Número de tracks después del merge. |
| `tracks_merged_count` | tracks_before_reid - tracks_after_reid. |
| `reid_candidates_generated` | Pares generados por gating. |
| `reid_pairs_after_phash` | Pares que pasaron el filtro pHash. |
| `reid_pairs_confirmed` | Pares confirmados por CLIP (stub → 0). |
| `clip_verifications_run` | Cantidad de pares enviados a verificación CLIP. |
| `reid_merge_map` | Dict merged_track_id → [original_track_ids] (solo componentes con size > 1). |
| `reid_error` | Presente solo si hubo excepción; mensaje de error (tracks originales devueltos). |

Además en `pipeline_debug`: `reid_signatures`, `reid_candidates`, `tracks_with_signatures`.

---

## US-6B.8 — Cache de embeddings CLIP (opcional)

**Como** operador, **quiero** cachear embeddings CLIP por ROI **para** controlar costo y latencia en Re-ID.

**Criterios de aceptación**
- CA.1: Config `CACHE_CLIP_EMBEDDINGS`; si True, embeddings se cachean por path de ROI (o hash de imagen).
- CA.2: verify_with_clip usa cache en lugar de recomputar cuando ya existe.

**Archivos impactados**
- `src/reid/clip_embedder.py` (cache en memoria o disco)
- `src/config.py` (CACHE_CLIP_EMBEDDINGS)
- `tests/test_reid.py` (cache hit/miss)

**Riesgos**
- Bajo.

**DoD**
- Tests de cache; métricas o logs que permitan ver hits.

---

## US-6B.9 — Observabilidad y validación manual

**Como** operador, **quiero** poder validar Re-ID con un video de muestra y un comando CLI claro **para** verificar manifests y métricas sin desplegar.

**Criterios de aceptación**
- CA.1: Comando documentado: `python -m src.app <video> --track-pipeline --heuristic --reid-enabled` (y opcional --save-annotated).
- CA.2: En summary o manifest se ve tracks_before_reid, tracks_after_reid, tracks_merged_count; si hay merge, algún manifest o log indica qué tracks se fusionaron.
- CA.3: README o doc con checklist de validación para Sprint 6B.

**Archivos impactados**
- `README.md` o `docs/SPRINT_6B.md`, `src/app.py` (help text)
- Opcional: manifest por run con reid_metrics

**Riesgos**
- Bajo.

**DoD**
- Documentación y comando listados; checklist ejecutable.

---

## Resumen de dependencias entre historias

- **6B.1** (esta entrega): base; sin dependencias de otras historias 6B.
- **6B.2** usa 6B.1 (paquete y hook ya existen).
- **6B.3** usa 6B.2 (firmas con centroides/tiempos).
- **6B.4** usa 6B.2 (firmas con pHash).
- **6B.5** usa 6B.2 (firmas con embeddings si se implementa real).
- **6B.6** independiente de 2–5 (solo pares confirmados); puede desarrollarse en paralelo tras 6B.1.
- **6B.7** integra 2–6 en el pipeline.
- **6B.8** mejora 6B.5/6B.7.
- **6B.9** documentación y validación final.

---

## Definición de “hecho” por historia

- Código compila.
- Tests pasan.
- Se puede activar con `--reid-enabled` o config/env.
- Métricas/logs visibles para lo implementado en esa historia.

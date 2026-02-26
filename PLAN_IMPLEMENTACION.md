# Plan de Implementación — Sistema de Conteo de Pallets por Video con Gemini

## Executive Summary

- **Objetivo:** Sistema de visión artificial que procesa videos de depósito/pasillos, detecta pallets únicos mediante tracking estable (`pallet_track_id`), y cuenta cajas por producto usando Gemini API con validación estricta post-LLM.

- **Unidad de procesamiento:** Cambio fundamental de `frame` → `pallet_track`. El costo escala con `#pallets únicos`, no con `#frames`.

- **Invariantes no negociables:**
  - **Segregación 100%:** Un pallet lógico nunca puede contener múltiples SKUs distintos. Si se detecta mezcla → `ERROR: MIXED_SKUS`.
  - **Conteo determinista:** Si la evidencia visual no es suficiente para un conteo exacto → `ERROR: INSUFFICIENT_EVIDENCE`. No se permite estimar.

- **Arquitectura de costo:**
  - **Sprint A/B:** `requests_sent ≈ pallet_tracks_detected` (1 request por track con 3-5 ROIs).
  - **Sprint C:** Re-ID agrega costo de CLIP solo para candidatos filtrados (pHash + gating temporal/espacial).

- **Pipeline principal:**
  1. Video → Extracción de frames
  2. Detección de pallets por frame (YOLO/clustering)
  3. Tracking multi-objeto (ByteTrack/SORT) → `pallet_track_id` estable
  4. ROI cropping por observación (bbox + padding 10-15%, resize max_side 1024/1280, JPEG quality 80-85)
  5. Selección de vistas por track (3-5): filtro por blur score + diversidad temporal + área ROI
  6. Gemini: 1 request por `pallet_track_id` con prompt multi-view anti-suma
  7. Validación post-LLM (Python): segregación + determinismo
  8. Export: `final_result.json` (OK) + `errors.json` (ERROR)

- **Sprint C (Re-ID):**
  - Firma por track (2-3 ROIs mejores: pHash + CLIP embedding)
  - Gating: temporal (`MAX_GAP=8s`) + espacial (`dx≤0.20`, `dy≤0.25`)
  - Filtro pHash (Hamming ≤10) → candidatos para CLIP
  - Verificación CLIP (cosine similarity ≥0.92) → merge confirmado
  - Union-Find (DSU) para fusionar tracks transitivos

- **Modo estricto:** El sistema falla correctamente. Si no puede garantizar segregación o determinismo → `ERROR` explícito. No inventa números.

- **Observabilidad:** Métricas principales: `tracks_detected`, `tracks_analyzed`, `tracks_ok`, `tracks_error_mixed_skus`, `tracks_error_insufficient_evidence`, `error_rate`, `avg_views_per_track`, `requests_sent`.

---

## Repo Structure (Target)

```
dinamic-gemini/
├── src/
│   ├── __init__.py
│   ├── config.py                    # Settings (extend existing)
│   ├── app.py                       # CLI entrypoint (modify existing)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py               # Extend: add PalletObservation, PalletTrack, etc.
│   │   └── contracts.py             # NEW: MinifiedTrackResult, TrackResultStrict
│   │
│   ├── video/
│   │   ├── __init__.py
│   │   ├── ingest.py                # Existing (keep)
│   │   └── frames.py                # Existing (keep)
│   │
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── pallet_detector.py       # NEW: detect_pallets_per_frame()
│   │   └── clustering.py            # NEW: cluster_boxes_to_pallets() (Opción A MVP)
│   │
│   ├── tracking/
│   │   ├── __init__.py
│   │   ├── tracker.py                # NEW: MultiObjectTracker (ByteTrack/SORT wrapper)
│   │   └── track_builder.py          # NEW: build_pallet_tracks(detections) -> List[PalletTrack]
│   │
│   ├── roi/
│   │   ├── __init__.py
│   │   ├── cropper.py                # NEW: crop_roi(bbox, padding_pct, max_side, quality)
│   │   └── quality.py                # NEW: calculate_blur_score(roi) -> float
│   │
│   ├── view_selection/
│   │   ├── __init__.py
│   │   ├── selector.py                # NEW: select_views_per_track(track, min_views, target_views, max_views)
│   │   └── diversity.py               # NEW: temporal_diversity_score() (Sprint C)
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── prompts.py                # Modify: add Prompt Maestro B (multi-view per track)
│   │   └── gemini_client.py          # Modify: analyze_track(track_id, roi_paths) -> MinifiedTrackResult
│   │
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── segregation.py            # NEW: enforce_one_product_per_pallet(result) -> bool
│   │   ├── determinism.py            # NEW: StrictCountingPolicy.validate(result, track) -> bool
│   │   └── normalizer.py             # NEW: normalize_product_key(brand, name) -> str (robust)
│   │
│   ├── reid/
│   │   ├── __init__.py
│   │   ├── signature.py              # NEW: build_track_signatures(tracks) -> Dict[track_id, TrackSignature]
│   │   ├── gating.py                 # NEW: generate_candidates(signatures, max_gap, dx_max, dy_max)
│   │   ├── phash.py                  # NEW: filter_with_phash(candidates, max_dist)
│   │   ├── clip_embedder.py          # NEW: verify_with_clip(candidates) -> List[PairConfirmed]
│   │   └── merge.py                  # NEW: merge_tracks_dsu(tracks, confirmed_pairs) -> List[MergedTrack]
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py           # NEW: run_pipeline(video_path, config) -> ProcessingResult
│   │   └── stages.py                 # NEW: Stage definitions (detection, tracking, roi, etc.)
│   │
│   └── io/
│       ├── __init__.py
│       ├── outputs.py                # Modify: export_final_result(ok_tracks), export_errors(error_tracks)
│       └── logging.py                 # Existing (keep)
│
├── tests/
│   ├── test_detection.py
│   ├── test_tracking.py
│   ├── test_roi.py
│   ├── test_view_selection.py
│   ├── test_validation.py
│   ├── test_reid.py
│   ├── test_pipeline_integration.py
│   └── test_regression.py            # 20 labeled videos
│
├── data/
│   ├── videos/                       # Test videos
│   └── labels/                        # Ground truth for regression tests
│
├── pyproject.toml                    # Extend dependencies
├── .env.example                      # Extend config vars
└── README.md                          # Update usage
```

### Module Responsibilities & Data Contracts

| Module | Input | Output | Key Functions |
|--------|-------|--------|---------------|
| `detection/pallet_detector.py` | `np.ndarray` (frame) | `List[BBox]` (x1,y1,x2,y2,conf) | `detect_pallets_per_frame(frame)` |
| `tracking/tracker.py` | `List[BBox]` per frame | `Dict[frame_idx, List[TrackedBBox]]` | `update(detections)` → `get_tracks()` |
| `tracking/track_builder.py` | Tracked detections | `List[PalletTrack]` | `build_pallet_tracks(tracked_data)` |
| `roi/cropper.py` | `BBox`, `np.ndarray` (frame) | `np.ndarray` (ROI), `str` (path) | `crop_roi(bbox, frame, padding_pct, max_side, quality)` |
| `roi/quality.py` | `np.ndarray` (ROI) | `float` (blur_score) | `calculate_blur_score(roi)` |
| `view_selection/selector.py` | `PalletTrack` | `List[PalletObservation]` (3-5) | `select_views_per_track(track, min_views, target_views, max_views)` |
| `llm/gemini_client.py` | `pallet_track_id`, `List[str]` (roi_paths) | `MinifiedTrackResult` | `analyze_track(track_id, roi_paths, prompt_profile)` |
| `validation/segregation.py` | `MinifiedTrackResult` | `bool` (is_valid) | `enforce_one_product_per_pallet(result)` |
| `validation/determinism.py` | `MinifiedTrackResult`, `PalletTrack` | `bool` (is_deterministic) | `StrictCountingPolicy.validate(result, track)` |
| `reid/signature.py` | `List[PalletTrack]` | `Dict[track_id, TrackSignature]` | `build_track_signatures(tracks, signature_k=2)` |
| `reid/gating.py` | `TrackSignature` dict | `List[Tuple[track_id, track_id]]` | `generate_candidates(signatures, max_gap, dx_max, dy_max)` |
| `reid/phash.py` | Candidates | Filtered candidates | `filter_with_phash(candidates, max_dist=10)` |
| `reid/clip_embedder.py` | Filtered candidates | `List[PairConfirmed]` | `verify_with_clip(candidates, min_sim=0.92)` |
| `reid/merge.py` | `List[PalletTrack]`, confirmed pairs | `List[MergedTrack]` | `merge_tracks_dsu(tracks, confirmed_pairs)` |
| `pipeline/orchestrator.py` | `video_path`, `Config` | `ProcessingResult` | `run_pipeline(video_path, config)` |

---

## Data Contracts

### Internal Models (Pydantic)

```python
# src/models/schemas.py (extend)

class PalletObservation(BaseModel):
    """Single observation of a pallet in a frame."""
    frame_idx: int
    timestamp_seconds: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    det_conf: float
    blur_score: Optional[float] = None
    roi_path: Optional[str] = None
    track_id: str

class PalletTrack(BaseModel):
    """Stable track of a pallet across frames."""
    track_id: str
    observations: List[PalletObservation]
    start_frame: int
    end_frame: int
    
    def best_views(self, k: int) -> List[PalletObservation]:
        """Select k best views based on blur_score + temporal diversity."""
        ...
    
    def roi_paths_for_views(self, k: int) -> List[str]:
        """Get ROI paths for k best views."""
        ...

class MergedTrack(PalletTrack):
    """Track after Re-ID merge (Sprint C)."""
    merged_from: List[str]  # Original track_ids
    signature: Optional[TrackSignature] = None

class PalletTrackBatch(BaseModel):
    """Input to Gemini: one track with selected ROIs."""
    track_id: str
    roi_paths: List[str]  # 3-5 paths
    video_id: str

# src/models/contracts.py (NEW)

class MinifiedTrackResult(BaseModel):
    """Minified JSON schema for Gemini output (production)."""
    id: str = Field(alias="pallet_id", description="Track ID")
    s: Literal["OK", "ERROR"] = Field(alias="status")
    e: Optional[Literal["MIXED_SKUS", "INSUFFICIENT_EVIDENCE"]] = Field(None, alias="error_code")
    b: Optional[str] = Field(None, alias="brand")
    n: Optional[str] = Field(None, alias="name")
    q: Optional[int] = Field(None, alias="count", ge=0)
    c: float = Field(alias="confidence", ge=0.0, le=1.0)
    v: int = Field(alias="views_used", ge=0, le=5)
    
    @model_validator(mode='after')
    def validate_error_state(self):
        if self.s == "ERROR":
            assert self.q is None, "count must be null when status=ERROR"
            assert self.c == 0.0, "confidence must be 0.0 when status=ERROR"
        return self

class TrackResultStrict(BaseModel):
    """Internal representation after validation."""
    pallet_id: str
    status: Literal["OK", "ERROR"]
    error_code: Optional[Literal["MIXED_SKUS", "INSUFFICIENT_EVIDENCE", "PARSE_FAILURE"]]
    product: Optional[ProductEstimate]  # Only if OK
    count: Optional[int]  # Only if OK
    confidence: float
    views_used: int
    validation_notes: Optional[str] = None

class ProcessingResult(BaseModel):
    """Final output of pipeline."""
    video_id: str
    run_id: str
    tracks_ok: List[TrackResultStrict]
    tracks_error: List[TrackResultStrict]
    processing_summary: ProcessingSummary

class ProcessingSummary(BaseModel):
    """Observability metrics."""
    frames_extracted: int
    detections_total: int
    pallet_tracks_detected: int
    tracks_analyzed: int
    tracks_ok: int
    tracks_error_mixed_skus: int
    tracks_error_insufficient_evidence: int
    error_rate: float
    avg_views_per_track: float
    views_selected_total: int
    roi_bytes_total: Optional[int]
    requests_sent: int
    parse_repair_rate: Optional[float]
    latency_total_seconds: float
    latency_per_request_avg: float
    # Sprint C
    tracks_before_reid: Optional[int] = None
    tracks_after_reid: Optional[int] = None
    tracks_merged_count: Optional[int] = None
    reid_candidates_generated: Optional[int] = None
    clip_verifications_run: Optional[int] = None
```

### External JSON Schema (Gemini)

```json
{
  "type": "object",
  "properties": {
    "id": {"type": "string"},
    "s": {"type": "string", "enum": ["OK", "ERROR"]},
    "e": {"type": ["string", "null"], "enum": ["MIXED_SKUS", "INSUFFICIENT_EVIDENCE", null]},
    "b": {"type": ["string", "null"]},
    "n": {"type": ["string", "null"]},
    "q": {"type": ["integer", "null"], "minimum": 0},
    "c": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    "v": {"type": "integer", "minimum": 0, "maximum": 5}
  },
  "required": ["id", "s", "c", "v"],
  "additionalProperties": false
}
```

### Output Files

**final_result.json** (OK tracks only):
```json
{
  "video_id": "VID_001",
  "run_id": "20260225_143353_960a8874",
  "pallets": [
    {
      "pallet_id": "TRACK_001",
      "products": [
        {
          "brand": "Cremigal",
          "product": "Leche UAT Entera 12x1L",
          "estimated_boxes": 84,
          "confidence": 0.93
        }
      ]
    }
  ],
  "processing_summary": { ... }
}
```

**errors.json** (ERROR tracks only):
```json
{
  "video_id": "VID_001",
  "run_id": "20260225_143353_960a8874",
  "errors": [
    {
      "pallet_id": "TRACK_002",
      "status": "ERROR",
      "error_code": "MIXED_SKUS",
      "validation_notes": "Detected 2 distinct product_keys: 'cremigal||leche uat' and 'cremigal||leche desnatada'"
    },
    {
      "pallet_id": "TRACK_003",
      "status": "ERROR",
      "error_code": "INSUFFICIENT_EVIDENCE",
      "validation_notes": "Only 2 views available, required min_views=3 for deterministic count"
    }
  ]
}
```

**processing_summary.json**:
```json
{
  "frames_extracted": 1800,
  "detections_total": 450,
  "pallet_tracks_detected": 12,
  "tracks_analyzed": 12,
  "tracks_ok": 10,
  "tracks_error_mixed_skus": 1,
  "tracks_error_insufficient_evidence": 1,
  "error_rate": 0.167,
  "avg_views_per_track": 4.2,
  "views_selected_total": 50,
  "requests_sent": 12,
  "latency_total_seconds": 45.3,
  "latency_per_request_avg": 3.775
}
```

---

## Implementation Plan by Sprint

### Sprint A — Identidad de Pallets + ROI + Micro-Batch (Bloqueante)

**Objective:** Establecer identidad estable de pallets (`pallet_track_id`) y mecanismo de micro-batching controlado por costo basado en selección de ROIs.

**Scope:** Detección, Tracking, Generación de ROI, Selección de Vistas, Request Gemini Micro-Batch.

#### Step-by-Step Tasks

1. **A1: Implementar detección de pallets por frame**
   - **File:** `src/detection/pallet_detector.py` (NEW)
   - **Function:** `detect_pallets_per_frame(frame: np.ndarray) -> List[BBox]`
   - **Opción A (MVP):** Si ya tienes YOLO de cajas → `cluster_boxes_to_pallets(detections) -> List[BBox]`
   - **Opción B:** Detector de pallets directo (requiere modelo entrenado)
   - **Output:** Lista de bboxes (x1, y1, x2, y2, conf) por frame
   - **Config:** `DETECTION_CONF_THRESHOLD = 0.5`

2. **A2: Implementar tracking multi-objeto**
   - **File:** `src/tracking/tracker.py` (NEW)
   - **Dependency:** `byte-track` o `sort-tracker` (agregar a `pyproject.toml`)
   - **Function:** `MultiObjectTracker.update(detections: List[BBox]) -> Dict[frame_idx, List[TrackedBBox]]`
   - **Output:** `track_id` estable por bbox
   - **Config:** `TRACKER_TYPE = "bytetrack"` (o "sort")

3. **A3: Construir objetos PalletTrack**
   - **File:** `src/tracking/track_builder.py` (NEW)
   - **Function:** `build_pallet_tracks(tracked_data: Dict) -> List[PalletTrack]`
   - **Output:** `List[PalletTrack]` con `observations: List[PalletObservation]`
   - **Calcula:** `start_frame`, `end_frame` por track

4. **A4: Implementar ROI Cropper**
   - **File:** `src/roi/cropper.py` (NEW)
   - **Function:** `crop_roi(bbox: Tuple, frame: np.ndarray, padding_pct: float, max_side: int, quality: int) -> Tuple[np.ndarray, str]`
   - **Lógica:**
     - `pad_px = padding_pct * max(bbox_width, bbox_height)`
     - Clamp a límites de imagen
     - Resize `max_side` (mantener aspect ratio)
     - JPEG quality
   - **Config:** `ROI_PADDING_PCT = 0.12`, `ROI_MAX_SIDE = 1280`, `ROI_JPEG_QUALITY = 85`

5. **A5: Calcular blur score por ROI**
   - **File:** `src/roi/quality.py` (NEW)
   - **Function:** `calculate_blur_score(roi: np.ndarray) -> float`
   - **Método:** `Var(Laplacian(gray(roi)))`
   - **Guarda:** `blur_score` en `PalletObservation`

6. **A6: Implementar selector de vistas por track**
   - **File:** `src/view_selection/selector.py` (NEW)
   - **Function:** `select_views_per_track(track: PalletTrack, min_views: int, target_views: int, max_views: int) -> List[PalletObservation]`
   - **Algoritmo:**
     1. Filtrar observaciones con blur < percentil 25 del track
     2. Ordenar por `frame_idx`
     3. Dividir track en `K=target_views` segmentos temporales
     4. En cada segmento: elegir observación con mayor `blur_score` + mayor área ROI (tie-breaker)
   - **Config:** `MIN_VIEWS = 3`, `TARGET_VIEWS = 4`, `MAX_VIEWS = 5`

7. **A7: Modificar Gemini client para 1 request por track**
   - **File:** `src/llm/gemini_client.py` (MODIFY)
   - **Function:** `analyze_track(track_id: str, roi_paths: List[str], prompt_profile: str) -> MinifiedTrackResult`
   - **Request shape:** Prompt primero, luego 3-5 imágenes (ROIs)
   - **Prompt:** "son vistas del MISMO pallet", "no sumes por imagen"
   - **Output:** `MinifiedTrackResult` (sin `status/error_code` todavía, eso es Sprint B)

8. **A8: Actualizar prompts para multi-view anti-suma**
   - **File:** `src/llm/prompts.py` (MODIFY)
   - **Add:** `PROMPT_MULTI_VIEW_ANTI_SUM` (Sprint A version, sin reglas estrictas todavía)

9. **A9: Integrar pipeline en orchestrator**
   - **File:** `src/pipeline/orchestrator.py` (NEW)
   - **Function:** `run_pipeline(video_path: str, config: Config) -> ProcessingResult`
   - **Stages:**
     1. Extract frames
     2. Detect pallets per frame
     3. Track → build PalletTracks
     4. Crop ROIs per observation
     5. Calculate blur scores
     6. Select views per track
     7. Send 1 request per track to Gemini
     8. Collect results
   - **Métricas:** `tracks_detected`, `tracks_analyzed`, `views_selected_total`, `requests_sent`

10. **A10: Actualizar CLI para nuevo pipeline**
    - **File:** `src/app.py` (MODIFY)
    - **Change:** Llamar `run_pipeline()` en lugar de pipeline frame-based
    - **Args:** Mantener existentes, agregar `--strict-mode` (placeholder para Sprint B)

#### File-Level TODO List

**New Files:**
- `src/detection/__init__.py`
- `src/detection/pallet_detector.py`
- `src/detection/clustering.py` (si Opción A)
- `src/tracking/__init__.py`
- `src/tracking/tracker.py`
- `src/tracking/track_builder.py`
- `src/roi/__init__.py`
- `src/roi/cropper.py`
- `src/roi/quality.py`
- `src/view_selection/__init__.py`
- `src/view_selection/selector.py`
- `src/pipeline/__init__.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/stages.py`

**Modified Files:**
- `src/models/schemas.py` (add `PalletObservation`, `PalletTrack`)
- `src/llm/gemini_client.py` (add `analyze_track()`)
- `src/llm/prompts.py` (add multi-view prompt)
- `src/app.py` (call `run_pipeline()`)
- `src/config.py` (add tracking/ROI/view selection config)
- `pyproject.toml` (add `byte-track` or `sort-tracker`)

#### Config Parameters (Defaults)

```python
# src/config.py (extend Settings)

# Detection
DETECTION_CONF_THRESHOLD: float = 0.5
DETECTION_USE_CLUSTERING: bool = True  # Opción A

# Tracking
TRACKER_TYPE: Literal["bytetrack", "sort"] = "bytetrack"
TRACKER_MIN_HITS: int = 3
TRACKER_MAX_AGE: int = 30

# ROI
ROI_PADDING_PCT: float = 0.12
ROI_MAX_SIDE: int = 1280
ROI_JPEG_QUALITY: int = 85

# View Selection
MIN_VIEWS: int = 3
TARGET_VIEWS: int = 4
MAX_VIEWS: int = 5
VIEW_SELECTION_BLUR_PERCENTILE: float = 0.25
```

#### Definition of Done

1. ✅ Pipeline produce `PalletTrack` estables para video largo con múltiples pallets.
2. ✅ Para cada track se generan ROIs y se seleccionan 3-5 vistas determinísticas.
3. ✅ Se envía **1 request por track** a Gemini (no por frame).
4. ✅ No se mezclan pallets en la request (ROIs lo garantizan).
5. ✅ `processing_summary` refleja: `tracks_detected`, `tracks_analyzed`, `views_selected_total`, `requests_sent`.
6. ✅ `requests_sent ≈ pallet_tracks_detected` (métrica clave).
7. ✅ Tests unitarios: detección, tracking, ROI, view selection.

#### Risks + Mitigations

| Risk | Mitigation |
|------|------------|
| Detector no detecta pallets bien | Opción A: agrupar cajas por cluster (MVP). Opción B: entrenar detector específico. |
| Tracker rompe IDs | Aceptable en Sprint A; Re-ID es Sprint C. Log `track_id` flips para análisis. |
| ROI mal recortado | Padding + clamp + QA check: ROI mantiene pallet completo. |
| Vistas redundantes | Selección por segmentos temporales + filtro blur. |
| Costo CLIP alto (si se usa) | No usar CLIP en Sprint A. Solo pHash/CLIP en Sprint C Re-ID. |

#### KPIs to Track

- `requests_sent ≈ pallet_tracks_detected` (target: ratio 1.0-1.2)
- `avg_views_per_track ∈ [3, 5]` (target: 4.0)
- `% tracks with views_selected >= 3` > 95%
- `roi_bytes_total` (monitorear para optimización)
- `latency_per_request_avg` < 5s

---

### Sprint B — Reglas Duras + Determinismo (Exacto o ERROR)

**Objective:** Aplicar invariantes de negocio: segregación 100% y conteo determinista. Cambiar sistema de "estimación" → "conteo exacto o error explícito".

**Scope:** Nuevo schema con `status/error_code`, prompt engineering para determinismo, validación post-LLM (hard constraints Python), export de errores.

#### Step-by-Step Tasks

1. **B1: Definir schema minificado con status/error_code**
   - **File:** `src/models/contracts.py` (NEW)
   - **Class:** `MinifiedTrackResult` (ver Data Contracts)
   - **Fields:** `id`, `s` (status), `e` (error_code), `b`, `n`, `q`, `c`, `v`
   - **Validator:** Si `s="ERROR"` → `q=null`, `c=0.0`

2. **B2: Actualizar response_schema de Gemini**
   - **File:** `src/llm/gemini_client.py` (MODIFY)
   - **Change:** `response_schema=MinifiedTrackResult` en `analyze_track()`
   - **Schema cleaning:** Usar `_get_safe_schema()` existente

3. **B3: Implementar Prompt Maestro B** ✅ (documentado)
   - **File:** `src/llm/prompts.py` (MODIFY)
   - **Add:** `PROMPT_MAESTRO_B_MULTI_VIEW` (ref. documento técnico Sprint 6, líneas 717-757; ver Appendix más abajo).
   - **Perfil CLI:** `maestro_b_multi_view`. User prompt es plantilla: el caller debe `.format(pallet_track_id=...)`.
   - **Key rules (ajuste de negocio):**
     - **MULTIPLE SKUs ALLOWED:** Un pallet puede tener varios SKU y estar desordenado; reportar cada producto identificable con su cantidad. No fallar solo por múltiples SKU.
     - **DETERMINISTIC COUNTING:** Si no hay evidencia suficiente para un producto → no adivinar: para ese producto `q=0`, `c=0.0` y explicar en `r`. No estimar profundidad oculta salvo que se vea en ≥2 vistas.
     - **Return ONLY valid JSON** según schema (un pallet, lista `p` de productos con `b`, `n`, `r`, `q`, `c`).

4. **B4: Implementar normalización robusta de product_key**
   - **File:** `src/validation/normalizer.py` (NEW)
   - **Function:** `normalize_product_key(brand: Optional[str], name: str) -> str`
   - **Lógica:** lower, strip, remove accents, remove punctuation, collapse whitespace
   - **Output:** `normalize(brand) + "||" + normalize(name)`

5. **B5: Implementar validador de segregación**
   - **File:** `src/validation/segregation.py` (NEW)
   - **Function:** `enforce_one_product_per_pallet(result: MinifiedTrackResult) -> Tuple[bool, Optional[str]]`
   - **Lógica:**
     - Si `result.s == "ERROR"` y `result.e == "MIXED_SKUS"` → ya validado por LLM, return `(True, None)`
     - Si `result.s == "OK"` → verificar que solo hay 1 `product_key` único
     - Si hay múltiples → return `(False, "MIXED_SKUS")`
   - **Output:** `(is_valid, error_code_if_invalid)`

6. **B6: Implementar StrictCountingPolicy**
   - **File:** `src/validation/determinism.py` (NEW)
   - **Class:** `StrictCountingPolicy`
   - **Method:** `validate(result: MinifiedTrackResult, track: PalletTrack) -> Tuple[bool, Optional[str]]`
   - **Rules:**
     - `views_used < min_views` → `INSUFFICIENT_EVIDENCE`
     - Si `result.s == "OK"` pero evidencia insuficiente (verificar consistencia en ≥2 vistas) → `INSUFFICIENT_EVIDENCE`
     - Si `result.s == "ERROR"` y `result.e == "INSUFFICIENT_EVIDENCE"` → ya validado, return `(True, None)`
   - **Config:** `MIN_VIEWS_FOR_DETERMINISM = 3`, `MIN_CONFIRM_VIEWS_FOR_DEPTH = 2`, `ALLOW_INFER_DEPTH = False`

7. **B7: Integrar validadores en pipeline**
   - **File:** `src/pipeline/orchestrator.py` (MODIFY)
   - **After Gemini response:**
     1. Parse `MinifiedTrackResult`
     2. Run `enforce_one_product_per_pallet()` → si falla, set `status=ERROR`, `error_code=MIXED_SKUS`
     3. Run `StrictCountingPolicy.validate()` → si falla, set `status=ERROR`, `error_code=INSUFFICIENT_EVIDENCE`
     4. Convert to `TrackResultStrict`
   - **Collect:** `tracks_ok`, `tracks_error` separados

8. **B8: Implementar export separado OK/ERROR**
   - **File:** `src/io/outputs.py` (MODIFY)
   - **Functions:**
     - `export_final_result(ok_tracks: List[TrackResultStrict], video_id: str, run_id: str) -> Path`
     - `export_errors(error_tracks: List[TrackResultStrict], video_id: str, run_id: str) -> Path`
   - **Output:** `final_result.json` (solo OK), `errors.json` (solo ERROR)

9. **B9: Actualizar processing_summary con métricas de negocio**
   - **File:** `src/pipeline/orchestrator.py` (MODIFY)
   - **Add metrics:**
     - `tracks_ok`, `tracks_error_mixed_skus`, `tracks_error_insufficient_evidence`
     - `error_rate = len(tracks_error) / len(tracks_analyzed)`
   - **File:** `src/models/schemas.py` (MODIFY)
   - **Extend:** `ProcessingSummary` con campos de error

10. **B10: Actualizar CLI para modo estricto**
    - **File:** `src/app.py` (MODIFY)
    - **Arg:** `--strict-mode` (default: `True` en Sprint B)
    - **Behavior:** Si `--strict-mode`, aplicar validadores. Si `False`, modo "legacy" (estimación).

#### File-Level TODO List

**New Files:**
- `src/models/contracts.py`
- `src/validation/__init__.py`
- `src/validation/normalizer.py`
- `src/validation/segregation.py`
- `src/validation/determinism.py`

**Modified Files:**
- `src/models/schemas.py` (add `TrackResultStrict`, extend `ProcessingSummary`)
- `src/llm/gemini_client.py` (use `MinifiedTrackResult` schema)
- `src/llm/prompts.py` (add Prompt Maestro B)
- `src/pipeline/orchestrator.py` (add validation stage)
- `src/io/outputs.py` (add export separado)
- `src/app.py` (add `--strict-mode`)

#### Config Parameters

```python
# src/config.py

# Validation
STRICT_MODE: bool = True
MIN_VIEWS_FOR_DETERMINISM: int = 3
MIN_CONFIRM_VIEWS_FOR_DEPTH: int = 2
ALLOW_INFER_DEPTH: bool = False
```

#### Definition of Done

1. ✅ Nuevo contrato JSON (prod) con `status/error_code` en uso.
2. ✅ Prompt Maestro B desplegado (perfil `maestro_b_multi_view`; permite multi-SKU y pallets desordenados; conteo determinista por producto).
3. ✅ Validadores Python: según política de negocio (ONE SKU opcional; ver Appendix Prompt Maestro B).
4. ✅ Sistema falla explícitamente con `ERROR` en lugar de estimar cuando evidencia insuficiente.
5. ✅ Reporte final incluye OK/ERROR separados con razones.
6. ✅ `error_rate` es métrica principal de negocio.
7. ✅ Tests unitarios: normalización, segregación, determinismo.

#### Risks + Mitigations

| Risk | Mitigation |
|------|------------|
| LLM ignora reglas duras | Validación post-LLM (hard constraints Python) prevalece sobre output LLM. |
| Token explosion | Schema minificado, sin reasoning obligatorio. |
| False positives (ERROR cuando debería OK) | Política conservadora: preferir ERROR antes que falso OK. Ajustar `MIN_VIEWS_FOR_DETERMINISM` si necesario. |

#### KPIs to Track

- `error_rate` (target: < 20% inicialmente, optimizar a < 10%)
- `tracks_error_mixed_skus` (target: 0 si segregación funciona)
- `tracks_error_insufficient_evidence` (monitorear para ajustar `MIN_VIEWS`)
- `avg_views_used_ok` vs `avg_views_used_error` (debe haber diferencia)

---

### Sprint C — Robustez y Escalabilidad Real en Pasillos

**Objective:** Mejorar robustez y capacidad anti-doble-conteo mediante Re-ID para manejar fallos de tracking en videos largos/pasillos.

**Scope:** Generación de firma por track, gating de candidatos (temporal/espacial), filtro pHash, verificación CLIP, estrategia de merge (Union-Find).

#### Step-by-Step Tasks

1. **C1: Implementar generación de firma por track**
   - **File:** `src/reid/signature.py` (NEW)
   - **Function:** `build_track_signatures(tracks: List[PalletTrack], signature_k: int = 2) -> Dict[str, TrackSignature]`
   - **Lógica:**
     - Por track: seleccionar `signature_k` mejores ROIs (blur_score alto, área alta, diversidad temporal)
     - Calcular `pHash` (64-bit) por ROI
     - Calcular `bbox_centroid` normalizado (0..1)
     - Calcular `clip_embedding` (vector normalizado L2) por ROI
   - **Dependency:** `imagehash` (pHash), `clip` o API CLIP
   - **Config:** `SIGNATURE_K = 2` (o 3)

2. **C2: Implementar gating temporal/espacial**
   - **File:** `src/reid/gating.py` (NEW)
   - **Function:** `generate_candidates(signatures: Dict[str, TrackSignature], max_gap: float, dx_max: float, dy_max: float) -> List[Tuple[str, str]]`
   - **Lógica:**
     - **Temporal gate:** `0 <= gap_seconds <= MAX_GAP`
     - **Spatial gate:** `|cxA - cxB| <= dx_max` y `|cyA - cyB| <= dy_max`
   - **Config:** `REID_MAX_GAP = 8.0`, `REID_DX_MAX = 0.20`, `REID_DY_MAX = 0.25`

3. **C3: Implementar filtro pHash**
   - **File:** `src/reid/phash.py` (NEW)
   - **Function:** `filter_with_phash(candidates: List[Tuple[str, str]], signatures: Dict, max_dist: int = 10) -> List[Tuple[str, str]]`
   - **Lógica:**
     - Por cada par candidato: calcular `min(hamming(phashA_i, phashB_j))` entre todos los ROIs
     - Si `min_dist <= PHASH_MAX_DIST` → pasa a CLIP
   - **Config:** `PHASH_MAX_DIST = 10`

4. **C4: Implementar verificación CLIP**
   - **File:** `src/reid/clip_embedder.py` (NEW)
   - **Function:** `verify_with_clip(candidates: List[Tuple[str, str]], signatures: Dict, min_sim: float = 0.92) -> List[Tuple[str, str]]`
   - **Lógica:**
     - Por cada par candidato: calcular `max(cosine_sim(embA_i, embB_j))` entre todos los embeddings
     - Si `max_sim >= CLIP_MIN_SIM` → merge confirmado
   - **Config:** `CLIP_MIN_SIM = 0.92`
   - **Dependency:** `clip` o API CLIP (costo alto, solo para candidatos)

5. **C5: Implementar merge strategy (Union-Find)**
   - **File:** `src/reid/merge.py` (NEW)
   - **Function:** `merge_tracks_dsu(tracks: List[PalletTrack], confirmed_pairs: List[Tuple[str, str]]) -> List[MergedTrack]`
   - **Lógica:**
     - Union-Find (DSU) para agrupar tracks transitivos (A~B, B~C → A~B~C)
     - Por cada cluster: crear `MergedTrack` con `merged_from` lista
     - Concatenar observaciones ordenadas por tiempo
     - Recomputar `start/end`, `best_views()`
   - **Output:** `List[MergedTrack]` (antes de view selection)

6. **C6: Integrar Re-ID en pipeline (antes de view selection)**
   - **File:** `src/pipeline/orchestrator.py` (MODIFY)
   - **After tracking, before ROI/view selection:**
     1. `signatures = build_track_signatures(tracks)`
     2. `candidates = generate_candidates(signatures, max_gap, dx_max, dy_max)`
     3. `filtered = filter_with_phash(candidates, signatures, max_dist)`
     4. `confirmed = verify_with_clip(filtered, signatures, min_sim)`
     5. `merged_tracks = merge_tracks_dsu(tracks, confirmed)`
   - **Use:** `merged_tracks` para view selection y Gemini (no `tracks` originales)

7. **C7: Actualizar métricas de Re-ID**
   - **File:** `src/pipeline/orchestrator.py` (MODIFY)
   - **Add to ProcessingSummary:**
     - `tracks_before_reid`, `tracks_after_reid`, `tracks_merged_count`
     - `reid_candidates_generated`, `clip_verifications_run`
     - `merge_clusters_sizes` (lista de tamaños de clusters)

8. **C8: Mejoras opcionales de view selection (diversidad angular)**
   - **File:** `src/view_selection/diversity.py` (NEW)
   - **Function:** `calculate_angular_diversity_score(observations: List[PalletObservation]) -> float`
   - **Integrate:** En `select_views_per_track()` como factor adicional

9. **C9: Optimización de costo (caching embeddings)**
   - **File:** `src/reid/clip_embedder.py` (MODIFY)
   - **Add:** Cache de embeddings por ROI (hash por bytes de imagen)
   - **Config:** `CACHE_CLIP_EMBEDDINGS = True`

10. **C10: Observabilidad avanzada (dashboard simple)**
    - **File:** `src/io/dashboard.py` (NEW, opcional)
    - **Function:** `generate_dashboard_html(result: ProcessingResult) -> str`
    - **Output:** HTML simple mostrando tracks OK vs ERROR por video

#### File-Level TODO List

**New Files:**
- `src/reid/__init__.py`
- `src/reid/signature.py`
- `src/reid/gating.py`
- `src/reid/phash.py`
- `src/reid/clip_embedder.py`
- `src/reid/merge.py`
- `src/view_selection/diversity.py` (opcional)
- `src/io/dashboard.py` (opcional)

**Modified Files:**
- `src/models/schemas.py` (add `MergedTrack`, extend `ProcessingSummary`)
- `src/pipeline/orchestrator.py` (add Re-ID stage)
- `src/config.py` (add Re-ID config)

#### Config Parameters

```python
# src/config.py

# Re-ID
REID_ENABLED: bool = True
SIGNATURE_K: int = 2
REID_MAX_GAP: float = 8.0
REID_DX_MAX: float = 0.20
REID_DY_MAX: float = 0.25
PHASH_MAX_DIST: int = 10
CLIP_MIN_SIM: float = 0.92
CACHE_CLIP_EMBEDDINGS: bool = True
```

#### Definition of Done

1. ✅ Módulo Re-ID implementado e integrado en pipeline pre-view selection.
2. ✅ `tracks_before_reid > tracks_after_reid` para videos con breaks de tracking.
3. ✅ Conteo final usa `MergedTrack` objects.
4. ✅ Observabilidad avanzada desplegada (dashboard o métricas).
5. ✅ Tests unitarios: gating, pHash, CLIP, DSU merge.

#### Risks + Mitigations

| Risk | Mitigation |
|------|------------|
| False merge (fusionar pallets distintos) | Endurecer `dx/dy` gate, bajar `PHASH_MAX_DIST`, subir `CLIP_MIN_SIM` a 0.93. |
| False negative (no fusionar mismo pallet) | Subir `MAX_GAP` a 12s, subir `PHASH_MAX_DIST` a 12, bajar `CLIP_MIN_SIM` a 0.90. |
| Costos CLIP altos | CLIP solo para candidatos (gating), cache embeddings por ROI. |

#### KPIs to Track

- `tracks_merged_count > 0` para videos con tracking breaks
- `clip_verifications_run << tracks_before_reid^2` (eficiencia de gating)
- `tracks_after_reid / tracks_before_reid` (ratio de reducción)
- `error_rate` (debe bajar con mejor cobertura de vistas)

---

## How to Run (Local Dev)

### Setup

```bash
# 1. Create venv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Install tracking library (Sprint A)
pip install byte-track  # or: pip install sort-tracker

# 4. Install Re-ID dependencies (Sprint C)
pip install imagehash pillow
# For CLIP: pip install clip-by-openai  # or use API

# 5. Configure environment
cp .env.example .env
# Edit .env: set GEMINI_API_KEY, etc.
```

### Run Pipeline on Sample Video

```bash
# Basic run (Sprint A)
python -m src.app data/videos/sample.mp4

# With custom config
python -m src.app data/videos/sample.mp4 \
  --video-id VID_001 \
  --extract-fps 0.5 \
  --output-dir output

# Strict mode (Sprint B, default)
python -m src.app data/videos/sample.mp4 --strict-mode

# Legacy mode (estimation, no strict validation)
python -m src.app data/videos/sample.mp4 --no-strict-mode

# Debug mode (save frames/ROIs)
python -m src.app data/videos/sample.mp4 --debug

# With Re-ID enabled (Sprint C)
python -m src.app data/videos/sample.mp4 --reid-enabled
```

### Output Locations

```
output/
  <video_id>/
    <run_id>/
      frames/              # Raw frames (if --debug)
      rois/                # ROI images per track (if --debug)
      final_result.json    # OK tracks only
      errors.json          # ERROR tracks only
      processing_summary.json
      processing.log       # Structured logs
      dashboard.html       # (Sprint C, optional)
```

### Enable Strict Mode

Strict mode is **default in Sprint B+**. To disable:

```bash
python -m src.app video.mp4 --no-strict-mode
```

Or set in `.env`:
```
STRICT_MODE=false
```

### Enable Debug Packs

```bash
# Save frames and ROIs
python -m src.app video.mp4 --debug

# Save only ROIs (not raw frames)
python -m src.app video.mp4 --save-rois

# Verbose logging
python -m src.app video.mp4 --log-level DEBUG
```

---

## Test Plan

### Unit Tests

**File:** `tests/test_detection.py`
- `test_detect_pallets_per_frame()`: detecta pallets en frame sintético
- `test_cluster_boxes_to_pallets()`: agrupa cajas en pallets

**File:** `tests/test_tracking.py`
- `test_tracker_updates()`: tracking mantiene IDs estables
- `test_track_builder()`: construye `PalletTrack` correctamente

**File:** `tests/test_roi.py`
- `test_crop_roi_padding()`: padding correcto
- `test_crop_roi_clamp()`: clamp a límites de imagen
- `test_calculate_blur_score()`: blur score calculado correctamente

**File:** `tests/test_view_selection.py`
- `test_select_views_temporal_diversity()`: vistas equiespaciadas
- `test_select_views_blur_filter()`: filtra frames borrosos
- `test_select_views_min_max()`: respeta min_views/max_views

**File:** `tests/test_validation.py`
- `test_normalize_product_key()`: normalización robusta (acentos, puntuación, espacios)
- `test_enforce_one_product_per_pallet_ok()`: 1 SKU → OK
- `test_enforce_one_product_per_pallet_mixed()`: 2 SKUs → ERROR
- `test_strict_counting_policy_sufficient_views()`: 3+ vistas → OK
- `test_strict_counting_policy_insufficient_views()`: <3 vistas → ERROR

**File:** `tests/test_reid.py`
- `test_gating_temporal()`: filtra por gap temporal
- `test_gating_spatial()`: filtra por posición
- `test_phash_filter()`: filtra por distancia Hamming
- `test_clip_verification()`: verifica con cosine similarity
- `test_merge_tracks_dsu()`: fusiona tracks transitivos

### Integration Tests

**File:** `tests/test_pipeline_integration.py`
- `test_pipeline_end_to_end_short_video()`: video de 10s, 2 pallets, verifica output JSON
- `test_pipeline_tracks_detected()`: verifica `tracks_detected == expected`
- `test_pipeline_requests_sent()`: verifica `requests_sent ≈ tracks_detected`
- `test_pipeline_strict_mode_errors()`: verifica que errores se exportan correctamente

### Regression Tests

**File:** `tests/test_regression.py`

**Dataset:** 20 videos etiquetados en `data/videos/` con ground truth en `data/labels/`.

**Expected Metrics per Video:**
- `tracks_detected` (debe coincidir con ground truth `#pallets`)
- `tracks_ok` (debe ser ≥ ground truth `#pallets_contables`)
- `tracks_error_mixed_skus` (debe ser 0 si no hay mezcla real)
- `tracks_error_insufficient_evidence` (monitorear, ajustar `MIN_VIEWS` si alto)
- `error_rate` (target: < 15% después de optimización)

**Run:**
```bash
pytest tests/test_regression.py -v --regression-dataset data/labels/
```

**Output:** Reporte comparando métricas esperadas vs actuales.

---

## Checklists

### Pre-Merge Checklist

- [ ] **Lint:** `ruff check src/ tests/`
- [ ] **Type check:** `mypy src/` (si configurado)
- [ ] **Tests:** `pytest tests/ -v --cov=src --cov-report=term-missing`
- [ ] **Coverage:** `coverage >= 80%` para módulos nuevos
- [ ] **Sample run:** `python -m src.app data/videos/test_sample.mp4` → verifica output JSON válido
- [ ] **Schema validation:** Output JSON valida contra `FinalResult` / `ErrorsResult` Pydantic models
- [ ] **Logs:** Verifica que `processing.log` contiene métricas esperadas
- [ ] **Config:** Verifica que nuevos parámetros tienen defaults sensatos en `config.py`

### Release Checklist

- [ ] **Versioning:** Actualizar `pyproject.toml` version (semver)
- [ ] **Schema version:** Si cambias `MinifiedTrackResult`, incrementar `schema_version` en output
- [ ] **Config freeze:** Documentar todos los parámetros en `README.md` o `CONFIG.md`
- [ ] **Changelog:** Actualizar `CHANGELOG.md` con cambios breaking
- [ ] **Dependencies:** Verificar que `pyproject.toml` tiene versiones fijas para producción
- [ ] **Migration guide:** Si hay cambios breaking, documentar migración
- [ ] **Tag:** `git tag v0.2.0` (ejemplo)

### Observability Checklist

- [ ] **ProcessingSummary completo:**
  - [ ] `tracks_detected`, `tracks_analyzed`, `tracks_ok`, `tracks_error_*`
  - [ ] `error_rate`, `avg_views_per_track`, `requests_sent`
  - [ ] `latency_total_seconds`, `latency_per_request_avg`
  - [ ] (Sprint C) `tracks_before_reid`, `tracks_after_reid`, `tracks_merged_count`
- [ ] **Logs estructurados:** Cada etapa loggea métricas con `log_metrics()`
- [ ] **Error tracking:** `errors.json` incluye `validation_notes` para debugging
- [ ] **Dashboard (Sprint C):** HTML generado muestra tracks OK vs ERROR

---

## Assumptions

1. **Detección de pallets:** Asumimos Opción A (clustering de cajas) para MVP. Si no hay YOLO de cajas, se requiere entrenar detector específico (fuera de scope Sprint A).

2. **Tracking library:** ByteTrack recomendado, pero SORT es alternativa válida. Asumimos que la librería elegida tiene API estable.

3. **CLIP embedding:** Asumimos uso de `clip-by-openai` o API CLIP. Si costo es prohibitivo, se puede deshabilitar Re-ID o usar solo pHash (menos robusto).

4. **Video format:** Asumimos formatos soportados por OpenCV (MP4, MOV, AVI). Formatos exóticos pueden requerir conversión previa.

5. **Ground truth para regresión:** Asumimos que los 20 videos etiquetados están disponibles. Si no, regresión tests se posponen.

6. **Strict mode default:** En Sprint B+, `STRICT_MODE=True` por defecto. Usuarios pueden deshabilitar para "legacy" behavior.

7. **Error handling:** Asumimos que fallos de API (Gemini, CLIP) se manejan con retry + logging. Tracks afectados → `ERROR: PARSE_FAILURE` o `UNPROCESSED`.

---

## Appendix: Prompt Maestro B (Reference)

### Versión referencia estricta (un SKU por pallet)

Versión original del documento técnico (Sprint 6, líneas 717-757); útil si en el futuro se exige un solo SKU por pallet y `status`/`error_code` en el schema.

```
SYSTEM:
You are a strict warehouse pallet counting engine.
...
HARD BUSINESS RULES:
1) ONE SKU PER PALLET: If you detect more than one distinct product/SKU → return ERROR with error_code="MIXED_SKUS".
2) DETERMINISTIC COUNTING: If you cannot determine the exact count → return ERROR with error_code="INSUFFICIENT_EVIDENCE".
OUTPUT: Return ONLY valid JSON matching the schema.
```

### Ajuste de negocio (implementado)

En la práctica **un pallet puede tener otros SKU y estar desordenado**. La implementación actual no impone "ONE SKU PER PALLET" ni error por múltiples SKU.

- **Reglas implementadas (PROMPT_MAESTRO_B_MULTI_VIEW):**
  1. **MULTIPLE SKUs ALLOWED:** Pallets pueden tener uno o varios productos y estar desordenados. Reportar cada producto claramente identificable con su cantidad. Solo usar confianza 0 cuando la mezcla no permita asignar cantidades por producto.
  2. **DETERMINISTIC COUNTING:** Si no se puede determinar la cantidad con evidencia en varias vistas, no adivinar: para ese producto `q=0`, `c=0.0` y explicar en el campo `r`. No estimar profundidad oculta salvo que se vea en ≥2 vistas.
  3. **OUTPUT:** Return ONLY valid JSON (schema actual: un pallet con lista `p` de productos; cada producto con `b`, `n`, `r`, `q`, `c`).

- **Perfil:** `maestro_b_multi_view`. User prompt es plantilla con `{pallet_track_id}`; el caller debe formatear con el id del track.
- **Schema de salida:** Coherente con `MinifiedFrameResult` / `MinifiedPallet` / `MinifiedProduct` (lista de productos por pallet).

---

**End of Plan**

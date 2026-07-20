# Processing mode UX (Phase 8)

## Process aisle modal

**Options for new runs**

| Option | Mode sent | Immediate external AI |
|--------|-----------|------------------------|
| Usar configuración predeterminada | inherit (`null` override) | Only if effective mode is legacy / external |
| Escanear QR o código de barras | `CODE_SCAN` | No |
| Leer etiqueta con OCR | `INTERNAL_OCR` | No (fallback may run later if enabled) |

**Not offered**

- `LEGACY_LLM` / “Procesamiento tradicional”
- “Usar configuración heredada” wording (replaced by **configuración predeterminada** + effective mode + source)

**Provider / model / prompt controls**

Shown only when the effective selection is still a legacy LLM mode (inherited soak path).  
For OCR / CODE_SCAN the dialog shows: *Proveedor externo inmediato: No*.

## Observability

Presentation is centralized in:

`frontend/src/features/processing/mappers/processingExecutionPresentation.ts`

Rules:

- Show **Proveedor / Modelo / Prompt tab** only when external LLM execution is evidenced (`LEGACY_*`, `EXTERNAL_PROVIDER`, or fallback progress).
- Correct misleading `current_stage: CodeScan` when strategy is `INTERNAL_OCR` → display `InternalOcr`.
- Prefer **Proveedor externo utilizado: Sí/No** over implying configured Gemini always ran.

## Duplicate “Escanear códigos”

Removed from **Más acciones** on aisle results.  
Barcode processing for inventory results is started via **Procesar → CODE_SCAN**.

The auxiliary `/code-scans` drawer API remains for evidence/review (COMPATIBILIDAD); do not present it as an alternate process path in the header menu.

## Historical jobs

Jobs with `LEGACY_LLM` remain visible; labels use “Procesamiento histórico con IA”.  
Creating a new run with the same obsolete override is blocked by the backend guard.

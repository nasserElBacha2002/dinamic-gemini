# Mobile Upload Phase 1 — Baseline Comparison

**Status:** tables intentionally empty of invented metrics.

| Escenario | Baseline bytes | Fase 1 bytes | Variación | Baseline upload | Fase 1 upload | Resultado servidor |
| --------- | -------------: | -----------: | --------: | --------------: | ------------: | ------------------ |
| 20 imgs Wi-Fi | — | — | — | — | — | no medido |
| 50 imgs Wi-Fi | — | — | — | — | — | no medido |
| 100 imgs Wi-Fi | — | — | — | — | — | no medido |
| 20 imgs cellular | — | — | — | — | — | no medido |
| 50 imgs cellular | — | — | — | — | — | no medido |
| JPEG ~12MP | — | — | — | — | — | no medido |
| HEIC | — | — | — | — | — | no medido |
| loss + retry | — | — | — | — | — | no medido |
| cancel | — | — | — | — | — | no medido |
| CODE_SCAN process | — | — | — | — | — | no medido |
| INTERNAL_OCR process | — | — | — | — | — | no medido |

How to fill: export Phase 0 baseline JSON before flags change vs after Phase 1 flags on (Diagnóstico → baseline). Compare `prepared_bytes`, `compression_ratio`, `prepare_ms`, `upload_ms`, `session_created_to_all_uploads_completed_ms`.

Do **not** claim percentage improvements without device rows above.

# OpenAI model_entity_id schema tolerance fix report

## 1. Executive summary

- **Status:** READY_FOR_REVIEW
- **Root cause:** OpenAI `json_object` responses can return `model_entity_id: null` or omit the field; `validate_global_analysis_structure_v21` requires a non-empty string.
- **Files changed:** `backend/src/llm/normalization/model_entity_id.py` (new), `backend/src/llm/openai_sdk_adapter.py`, `backend/tests/llm/test_model_entity_id_normalization.py` (new)
- **Tests added:** 7 unit/regression tests (null, missing, empty, preserved, duplicate, adapter, parse helper)

## 2. Error reproduced

```
[SCHEMA_INVALID] entities[0].model_entity_id must be a string, got 'NoneType'
```

OpenAI returned valid-looking entity JSON with `model_entity_id: null`. Strict validation ran on the raw parse result and rejected the response before entity resolution. Gemini uses structured output with a required string field, so it did not hit this path.

## 3. Fix implemented

- New helper: `normalize_model_entity_ids(data)` in `llm/normalization/model_entity_id.py`.
- Called from `_openai_parse_validate_global_analysis_json` **after** count normalization and **before** `validate_global_analysis_structure_v21`.
- Missing/null/whitespace → `E{index+1}` (with collision-safe allocation).
- Duplicate non-empty IDs → next free `E{n}`.
- Valid custom IDs (e.g. `CUSTOM_7`) are preserved.
- Warnings logged (`provider`, `job_id`, repaired indexes) and attached to `LLMResponse.usage["model_entity_id_repair_warnings"]`.

Gemini/Claude paths unchanged.

## 4. Validation behavior

`validate_global_analysis_structure_v21` still runs on the repaired payload. Business fields (`source_image_id`, `internal_code`, quantities, bboxes) are not invented.

## 5. Tests

```bash
cd backend && python3 -m pytest tests/llm/test_model_entity_id_normalization.py tests/llm/test_openai_sdk_adapter.py -q
```

**Result:** 17 passed.

## 6. Remaining risks

- GPT may still fail on other required schema fields (`entity_type`, `has_boxes`, bboxes, etc.).
- A future strict OpenAI JSON Schema path may reduce the need for post-hoc repair.
- This fix does not change image traceability or quantity logic.

## 7. Final status

**READY_FOR_REVIEW**

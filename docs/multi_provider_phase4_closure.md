# Phase 4 provider executor — closure notes

This supplements `multi_provider_planning_revision.md` and the implementation plan.

## Native vs transitional executors

- **`LlmGlobalAnalysisExecutor`** (`src/pipeline/ports/llm_execution.py`) is the pipeline-facing contract. I/O types are **`LLMRequest` / `LLMResponse`** (`src/llm/types.py`) — provider-neutral names are historical; semantics are documented there.

- **`gemini`** → **`GeminiSdkAdapter`** implements `execute()` directly; Gemini SDK types exist only under `src/llm/gemini_sdk_adapter.py`.

- **`openai`** → **`OpenAiSdkAdapter`** implements `execute()` directly (`src/llm/openai_sdk_adapter.py`).

- **`fake`** → **`TransitionalLlmProviderBridgeExecutor`** wraps legacy **`LLMProvider.analyze_global`**. See **`TRANSITIONAL_LLM_PROVIDER_BRIDGE_KEYS`** in `src/pipeline/providers/registry.py` (currently `{"fake"}` only).

## Default wiring

- **`default_analysis_provider()`** returns `HybridGlobalAnalysisStrategy` when `HybridInventoryPipeline` is constructed without injection. That is **runtime default wiring** for the shared hybrid analysis path; the executor is still resolved per job/settings via the registry.

## Generic layers

- **`HybridInventoryPipeline`** and **`AnalysisStage`** must not import `GeminiClient` / `GeminiGlobalAnalyzer`. Vendor code stays in adapters under `src/llm/` and the strategy module.

# Phase 4 provider executor — closure notes

This supplements `multi_provider_planning_revision.md` and the implementation plan.

## Native vs transitional executors

- **`LlmGlobalAnalysisExecutor`** (`src/pipeline/ports/llm_execution.py`) is the pipeline-facing contract. I/O types are **`LLMRequest` / `LLMResponse`** (`src/llm/types.py`) — provider-neutral names are historical; semantics are documented there.

- **`gemini`** → **`GeminiSdkAdapter`** implements `execute()` directly; Gemini SDK types exist only under `src/llm/gemini_sdk_adapter.py`.

- **`fake`** and **`openai`** → **`TransitionalLlmProviderBridgeExecutor`** wraps legacy **`LLMProvider.analyze_global`**. This is intentional until Phase 5+ adds dedicated executors. See **`TRANSITIONAL_LLM_PROVIDER_BRIDGE_KEYS`** in `src/pipeline/providers/registry.py`.

## Default wiring

- **`default_analysis_provider()`** returns the historical hybrid strategy class (`GeminiAnalysisProvider`) when `HybridInventoryPipeline` is constructed without injection. That is **runtime default wiring**, not a domain statement that all analysis is Gemini.

## Generic layers

- **`HybridInventoryPipeline`** and **`AnalysisStage`** must not import `GeminiClient` / `GeminiGlobalAnalyzer`. Vendor code stays in adapters under `src/llm/` and the strategy module.

"""Admin-only AI / provider inspection API (read-only, no secrets)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE


class AdminAiConfigServerDefaults(BaseModel):
    llm_provider: str
    hybrid_prompt_key: str = Field(
        ...,
        description=(
            "HYBRID_PROMPT env value — test-mode / catalog default when prompt_key is omitted; "
            "does not publish or switch the protected production aisle hybrid body."
        ),
    )
    prompt_version: str | None = Field(
        None,
        description=(
            "PROMPT_VERSION env — optional traceability label only; does not select prompt content."
        ),
    )
    effective_aisle_hybrid_profile: str = Field(
        DEFAULT_HYBRID_PROMPT_PROFILE,
        description="Protected hybrid profile always composed for new aisle analysis jobs.",
    )
    hybrid_prompt_env_selects_aisle_body: bool = Field(
        False,
        description="Always false: HYBRID_PROMPT does not change production aisle prompt bodies.",
    )
    prompt_version_env_selects_content: bool = Field(
        False,
        description="Always false: PROMPT_VERSION does not change composed prompt text.",
    )


class AdminAiConfigModelItem(BaseModel):
    id: str
    label: str
    is_default: bool


class AdminAiConfigProviderCapabilities(BaseModel):
    """Operational flags for the provider (credentials, defaults, multimodal)."""

    is_default_pipeline_provider: bool
    credential_configured: bool
    multimodal_aisle_analysis_supported: bool
    execution_mode: str = "native"


class AdminAiConfigProviderInstructions(BaseModel):
    provider_specific_note: str = ""


class AdminAiConfigResponseContract(BaseModel):
    expects_json: bool = True
    wire_transport: str
    validation_function: str
    normalization_function: str
    normalization_family: str
    alias_promotion_policy: str
    claude_product_label_to_internal_code_when_valid: bool = False
    required_root_keys: list[str] = Field(default_factory=list)
    extra_root_keys_policy_short: str = ""
    required_entity_keys: list[str] = Field(default_factory=list)
    canonical_entity_keys: list[str] = Field(default_factory=list)
    nullable_optional_entity_keys: list[str] = Field(default_factory=list)
    canonical_example_json: str = ""
    transport_notes: list[str] = Field(default_factory=list)


class AdminAiConfigComposition(BaseModel):
    """Hybrid prompt assembly rules for this pipeline provider (not operator instructions)."""

    hybrid_base_mode: str
    parity_mode_affects_prompt_assembly: bool
    multimodal_context_policy: str


class AdminAiConfigPromptCatalogItem(BaseModel):
    key: str
    label: str
    description: str | None = None


class AdminAiConfigPromptVariantSummary(BaseModel):
    prompt_key: str
    pipeline_provider_key: str
    prompt_parity_mode: bool
    variant_label: str


class AdminAiComposedPromptResponse(BaseModel):
    prompt_key: str
    pipeline_provider_key: str
    prompt_parity_mode: bool
    variant_label: str
    composed_prompt_text: str


class AdminAiConfigProviderDetail(BaseModel):
    key: str
    label: str
    description: str | None = None
    execution_mode: str = "native"
    models: list[AdminAiConfigModelItem] = Field(default_factory=list)
    default_model: str | None = None
    capabilities: AdminAiConfigProviderCapabilities
    instructions: AdminAiConfigProviderInstructions
    response_contract: AdminAiConfigResponseContract
    composition: AdminAiConfigComposition
    prompt_variant_summaries: list[AdminAiConfigPromptVariantSummary] = Field(default_factory=list)


class AdminAiConfigResponse(BaseModel):
    generated_at: str
    server_defaults: AdminAiConfigServerDefaults
    providers: list[AdminAiConfigProviderDetail]
    prompt_catalog: list[AdminAiConfigPromptCatalogItem]
    global_instructions_note: str

    model_config = ConfigDict(extra="ignore")

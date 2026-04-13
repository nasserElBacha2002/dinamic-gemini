"""Admin-only AI / provider inspection API (read-only, no secrets)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AdminAiConfigServerDefaults(BaseModel):
    llm_provider: str
    hybrid_prompt_key: str
    prompt_version: Optional[str] = None


class AdminAiConfigModelItem(BaseModel):
    id: str
    label: str
    is_default: bool


class AdminAiConfigProviderOverview(BaseModel):
    is_default_pipeline_provider: bool
    credential_configured: bool
    operationally_available: bool
    multimodal_aisle_analysis_supported: bool
    execution_mode: str = "native"


class AdminAiConfigProviderInstructions(BaseModel):
    provider_specific_note: str = ""


class AdminAiConfigResponseContract(BaseModel):
    expects_json: bool = True
    validation_function: str
    normalization_function: str
    normalization_family: str
    required_root_keys: List[str] = Field(default_factory=list)
    extra_root_keys_policy: str = ""
    required_entity_keys: List[str] = Field(default_factory=list)
    canonical_entity_keys: List[str] = Field(default_factory=list)
    nullable_optional_entity_keys: List[str] = Field(default_factory=list)
    canonical_example_json: str = ""
    raw_provider_expectation: str = ""
    canonical_contract_summary: str = ""
    provider_wire_notes: List[str] = Field(default_factory=list)
    normalization_notes: List[str] = Field(default_factory=list)


class AdminAiConfigCompositionNotes(BaseModel):
    hybrid_base_resolution: str = ""
    parity_mode: str = ""
    multimodal_context_rules: str = ""
    provider_composition_summary: str = ""
    bullets: List[str] = Field(default_factory=list)


class AdminAiConfigPromptCatalogItem(BaseModel):
    key: str
    label: str
    description: Optional[str] = None


class AdminAiConfigPromptVariant(BaseModel):
    prompt_key: str
    pipeline_provider_key: str
    prompt_parity_mode: bool
    variant_label: str
    composed_prompt_text: str


class AdminAiConfigProviderDetail(BaseModel):
    key: str
    label: str
    description: Optional[str] = None
    execution_mode: str = "native"
    models: List[AdminAiConfigModelItem] = Field(default_factory=list)
    default_model: Optional[str] = None
    overview: AdminAiConfigProviderOverview
    instructions: AdminAiConfigProviderInstructions
    response_contract: AdminAiConfigResponseContract
    composition_notes: AdminAiConfigCompositionNotes
    prompt_variants: List[AdminAiConfigPromptVariant] = Field(default_factory=list)


class AdminAiConfigResponse(BaseModel):
    generated_at: str
    server_defaults: AdminAiConfigServerDefaults
    providers: List[AdminAiConfigProviderDetail]
    prompt_catalog: List[AdminAiConfigPromptCatalogItem]
    global_instructions_note: str

    model_config = ConfigDict(extra="ignore")

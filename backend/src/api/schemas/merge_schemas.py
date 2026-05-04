from typing import Any, Optional

from pydantic import BaseModel, Field


class RunMergeResponse(BaseModel):
    operation_mode: str = Field(
        description=(
            "Merge execution mode for the manual aisle merge flow. The active restored mode is "
            "manual_authoritative, meaning the operator-triggered merge updates authoritative "
            "ProductRecord quantities and the visible aisle results."
        )
    )
    authoritative_quantity_updated: bool = Field(
        description=(
            "True when the manual merge updated authoritative ProductRecord quantities for the "
            "visible aisle results surface."
        )
    )
    raw_count: int
    normalized_count: int
    final_count: int
    product_records_updated: int = Field(
        description=(
            "Number of ProductRecord rows updated by the manual authoritative merge. Preserved as "
            "a compatibility field for existing consumers."
        )
    )


class MergeResultItemResponse(BaseModel):
    id: str
    position_id: Optional[str]
    sku: Optional[str]
    product_name: Optional[str]
    merged_quantity: int
    normalized_label_ids: list[str]
    review_required: bool
    explanation_summary: Optional[str]
    metadata: dict[str, Any]
    created_at: str


class MergeResultsResponse(BaseModel):
    results: list[MergeResultItemResponse]
    result_job_id: Optional[str] = Field(
        None, description="Effective job slice; null means legacy null-job final_count rows."
    )
    result_context_source: str = Field(
        ...,
        description="explicit | operational | legacy — how result_job_id was resolved.",
    )

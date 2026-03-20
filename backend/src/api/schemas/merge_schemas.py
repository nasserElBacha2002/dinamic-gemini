from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RunMergeResponse(BaseModel):
    operation_mode: str
    authoritative_quantity_updated: bool
    raw_count: int
    normalized_count: int
    final_count: int
    product_records_updated: int = Field(
        description=(
            "Compatibility field. In artifact_only mode this is expected to remain 0 because "
            "authoritative ProductRecord quantities are not updated."
        )
    )


class MergeResultItemResponse(BaseModel):
    id: str
    position_id: Optional[str]
    sku: Optional[str]
    product_name: Optional[str]
    merged_quantity: int
    normalized_label_ids: List[str]
    review_required: bool
    explanation_summary: Optional[str]
    metadata: Dict[str, Any]
    created_at: str


class MergeResultsResponse(BaseModel):
    results: List[MergeResultItemResponse]


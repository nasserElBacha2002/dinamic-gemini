from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RunMergeResponse(BaseModel):
    operation_mode: str = Field(
        description=(
            "Merge execution mode. Current mode is artifact_only, meaning merge computes artifacts "
            "without overwriting authoritative ProductRecord quantities."
        )
    )
    authoritative_quantity_updated: bool = Field(
        description=(
            "False in artifact_only mode. True would indicate authoritative ProductRecord "
            "quantities were updated (not used in current flow)."
        )
    )
    raw_count: int
    normalized_count: int
    final_count: int
    product_records_updated: int = Field(
        description=(
            "Compatibility field for legacy consumers. In artifact_only mode this is expected "
            "to remain 0 because authoritative ProductRecord quantities are not updated."
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


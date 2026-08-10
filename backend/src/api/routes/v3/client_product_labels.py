"""Client-scoped physical product label mint API (D1 format).

Idempotency: each POST intentionally mints new unique label_id values (physical stickers).
Unlike position-label create, retries/double-clicks produce additional stickers — there is no
shared Idempotency-Key for mint batches because each unit must remain a distinct physical ID.
Clients should disable double-submit in UI; timeouts may intentionally create extras that are unused.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_access_principal, get_client_repo, get_clock
from src.api.errors import reraise_if_mapped
from src.api.schemas.product_label_schemas import (
    IssuedProductLabelResponse,
    IssueProductLabelsRequest,
    IssueProductLabelsResponse,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.ports.repositories import ClientRepository
from src.application.use_cases.product_labels import (
    IssueProductLabelsCommand,
    IssueProductLabelsUseCase,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.runtime.app_container import get_app_container

router = APIRouter(tags=["client-product-labels"])


def _get_issued_repo():
    return get_app_container().get_issued_product_label_repo()


def get_issue_product_labels_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> IssueProductLabelsUseCase:
    return IssueProductLabelsUseCase(
        client_repo=client_repo,
        issued_repo=_get_issued_repo(),
        clock=clock,
    )


@router.post(
    "/{client_id}/product-labels",
    response_model=IssueProductLabelsResponse,
    status_code=201,
)
def issue_product_labels(
    client_id: str,
    body: IssueProductLabelsRequest,
    use_case: IssueProductLabelsUseCase = Depends(get_issue_product_labels_use_case),
    user: AuthUser = Depends(get_current_admin),
    principal: AccessPrincipal = Depends(get_access_principal),
) -> IssueProductLabelsResponse:
    try:
        result = use_case.execute(
            IssueProductLabelsCommand(
                client_id=client_id,
                internal_code=body.internal_code,
                quantity=body.quantity,
                count=body.count,
                created_by=user.id,
                principal=principal,
            )
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise

    return IssueProductLabelsResponse(
        items=[
            IssuedProductLabelResponse(
                label_id=item.label_id,
                internal_code=item.internal_code,
                quantity=item.quantity,
                format_version=item.format_version,
                checksum=item.checksum,
                payload=item.payload,
                created_at=item.created_at,
            )
            for item in result.items
        ]
    )

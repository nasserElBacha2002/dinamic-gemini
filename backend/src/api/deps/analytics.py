"""Analytics and benchmark API dependency providers.

Implementation is mechanically extracted from src.api.dependencies. The
historical module remains the public compatibility facade.
"""

from __future__ import annotations

from fastapi import Depends

from src.api.deps.infrastructure import get_result_context_resolver
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.analytics_query_service import AnalyticsQueryService
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.aisles.promote_aisle_operational_job import (
    PromoteAisleOperationalJobUseCase,
)
from src.application.use_cases.analytics.compare_aisle_runs import CompareAisleRunsUseCase
from src.application.use_cases.analytics.compare_many_aisle_runs import CompareManyAisleRunsUseCase
from src.application.use_cases.analytics.export_aisle_benchmark import (
    ExportAisleBenchmarkCompareCsvUseCase,
    ExportAisleBenchmarkRunCsvUseCase,
)
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_analytics_repo,
    get_inventory_repo,
    get_job_repo,
    get_position_repo,
    get_product_record_repo,
)


def get_compare_aisle_runs_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
) -> CompareAisleRunsUseCase:
    from src.config import load_settings

    return CompareAisleRunsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        positions_aisle_raw_cap=load_settings().v3_positions_aisle_raw_cap,
    )


def get_compare_many_aisle_runs_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
) -> CompareManyAisleRunsUseCase:
    from src.config import load_settings

    return CompareManyAisleRunsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        positions_aisle_raw_cap=load_settings().v3_positions_aisle_raw_cap,
    )


def get_promote_aisle_operational_job_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> PromoteAisleOperationalJobUseCase:
    from src.runtime.v3_deps import get_app_container

    return PromoteAisleOperationalJobUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        operational_promotion_service=get_app_container().build_operational_result_promotion_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
        ),
    )


def get_export_aisle_benchmark_run_csv_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
) -> ExportAisleBenchmarkRunCsvUseCase:
    from src.config import load_settings

    return ExportAisleBenchmarkRunCsvUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        positions_aisle_raw_cap=load_settings().v3_positions_aisle_raw_cap,
    )


def get_export_aisle_benchmark_compare_csv_use_case(
    compare_uc: CompareAisleRunsUseCase = Depends(get_compare_aisle_runs_use_case),
) -> ExportAisleBenchmarkCompareCsvUseCase:
    return ExportAisleBenchmarkCompareCsvUseCase(compare_uc=compare_uc)


def get_analytics_query_service(
    repo=Depends(get_analytics_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
) -> AnalyticsQueryService:
    return AnalyticsQueryService(repo, aisle_repo)


def get_analytics_cost_summary_service(
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
):
    from src.application.services.analytics_cost_counted_quantity import (
        AnalyticsCostCountedQuantityService,
    )
    from src.application.services.analytics_cost_summary_service import AnalyticsCostSummaryService

    return AnalyticsCostSummaryService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        counted_quantity_service=AnalyticsCostCountedQuantityService(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            job_repo=job_repo,
            result_context_resolver=result_context_resolver,
        ),
    )

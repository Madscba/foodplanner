"""API routes for ingestion pipeline management."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from foodplanner.database import get_db
from foodplanner.logging_config import get_logger
from foodplanner.models import Discount, IngestionRun, Product, Store

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


# Response schemas
class IngestionTriggerRequest(BaseModel):
    """Request to trigger ingestion."""

    store_ids: list[str] | None = Field(
        default=None,
        description="Specific store IDs to ingest. If None, ingest all user-selected stores.",
    )
    force: bool = Field(default=False, description="Force re-ingestion even if already run today")


class IngestionTriggerResponse(BaseModel):
    """Response from ingestion trigger."""

    task_id: str
    status: str
    message: str


class StoreIngestionStatusResponse(BaseModel):
    """Per-store ingestion status."""

    id: int
    store_id: str
    status: str
    products_fetched: int
    discounts_fetched: int
    products_inserted: int
    discounts_inserted: int
    error_message: str | None
    retry_count: int
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True


class IngestionRunResponse(BaseModel):
    """Summary of an ingestion run."""

    id: int
    run_date: date
    status: str
    task_id: str | None
    trigger_type: str
    stores_total: int
    stores_completed: int
    stores_failed: int
    products_updated: int
    discounts_updated: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None = None

    class Config:
        from_attributes = True


class IngestionRunDetailResponse(IngestionRunResponse):
    """Detailed view of an ingestion run including per-store status."""

    store_statuses: list[StoreIngestionStatusResponse] = Field(default_factory=list)


class IngestionRunsListResponse(BaseModel):
    """Paginated list of ingestion runs."""

    runs: list[IngestionRunResponse]
    total: int
    page: int
    page_size: int


class IngestionHealthResponse(BaseModel):
    """Health status of the ingestion system."""

    healthy: bool
    database: bool
    database_error: str | None = None
    redis: bool
    redis_error: str | None = None
    last_successful_run: datetime | None = None
    pending_stores: int = 0


class IngestionStatsResponse(BaseModel):
    """Statistics about ingestion data."""

    total_stores: int
    active_stores: int
    total_products: int
    total_discounts: int
    active_discounts: int
    last_run_date: date | None
    last_run_status: str | None
    runs_last_7_days: int
    successful_runs_last_7_days: int


@router.post("/trigger", response_model=IngestionTriggerResponse)
async def trigger_ingestion(
    request: IngestionTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestionTriggerResponse:
    """
    Manually trigger a data ingestion run.

    This will queue a Celery task to run the ingestion pipeline.
    Use the returned task_id to check progress via /runs endpoint.
    """
    from foodplanner.tasks.ingestion import run_daily_ingestion_task

    logger.info(f"Manual ingestion trigger: stores={request.store_ids}, force={request.force}")

    try:
        # Queue the Celery task
        task = run_daily_ingestion_task.delay(
            store_ids=request.store_ids,
            force=request.force,
        )

        return IngestionTriggerResponse(
            task_id=task.id,
            status="queued",
            message="Ingestion task queued successfully. Check /runs for progress.",
        )

    except Exception as e:
        logger.error(f"Failed to queue ingestion task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue ingestion task: {e}",
        )


@router.get("/runs", response_model=IngestionRunsListResponse)
async def list_ingestion_runs(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    status_filter: Annotated[str | None, Query(description="Filter by status")] = None,
    db: AsyncSession = Depends(get_db),
) -> IngestionRunsListResponse:
    """
    List recent ingestion runs with pagination.

    Returns a paginated list of ingestion runs, most recent first.
    """
    # Build query
    query = select(IngestionRun)

    if status_filter:
        query = query.where(IngestionRun.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(IngestionRun.run_date.desc(), IngestionRun.id.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    runs = result.scalars().all()

    return IngestionRunsListResponse(
        runs=[_run_to_response(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/{run_id}", response_model=IngestionRunDetailResponse)
async def get_ingestion_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> IngestionRunDetailResponse:
    """
    Get detailed information about a specific ingestion run.

    Includes per-store status information.
    """
    result = await db.execute(
        select(IngestionRun)
        .options(selectinload(IngestionRun.store_statuses))
        .where(IngestionRun.id == run_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion run {run_id} not found",
        )

    response = _run_to_response(run)
    return IngestionRunDetailResponse(
        **response.model_dump(),
        store_statuses=[StoreIngestionStatusResponse.model_validate(s) for s in run.store_statuses],
    )


@router.get("/runs/by-task/{task_id}", response_model=IngestionRunDetailResponse)
async def get_ingestion_run_by_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> IngestionRunDetailResponse:
    """
    Get ingestion run by Celery task ID.

    Useful for checking progress after triggering a manual run.
    """
    result = await db.execute(
        select(IngestionRun)
        .options(selectinload(IngestionRun.store_statuses))
        .where(IngestionRun.task_id == task_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ingestion run found for task {task_id}",
        )

    response = _run_to_response(run)
    return IngestionRunDetailResponse(
        **response.model_dump(),
        store_statuses=[StoreIngestionStatusResponse.model_validate(s) for s in run.store_statuses],
    )


@router.get("/health", response_model=IngestionHealthResponse)
async def get_ingestion_health(
    db: AsyncSession = Depends(get_db),
) -> IngestionHealthResponse:
    """
    Check the health of the ingestion system.

    Verifies database and Redis connectivity.
    """
    from foodplanner.tasks.ingestion import health_check_task

    logger.info("Running ingestion health check via API")

    # Run health check task synchronously for immediate response
    try:
        health_result = health_check_task()
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_result = {
            "database": False,
            "redis": False,
            "healthy": False,
            "error": str(e),
        }

    # Get last successful run
    last_success = await db.execute(
        select(IngestionRun)
        .where(IngestionRun.status == "completed")
        .order_by(IngestionRun.completed_at.desc())
        .limit(1)
    )
    last_run = last_success.scalar_one_or_none()

    # Count stores without recent ingestion
    from datetime import timedelta

    stale_cutoff = datetime.utcnow() - timedelta(days=2)
    pending_stores = await db.execute(
        select(func.count(Store.id)).where(
            Store.is_active == True,  # noqa: E712
            (Store.last_ingested_at == None) | (Store.last_ingested_at < stale_cutoff),  # noqa: E711
        )
    )
    pending_count = pending_stores.scalar() or 0

    return IngestionHealthResponse(
        healthy=health_result.get("healthy", False),
        database=health_result.get("database", False),
        database_error=health_result.get("database_error"),
        redis=health_result.get("redis", False),
        redis_error=health_result.get("redis_error"),
        last_successful_run=last_run.completed_at if last_run else None,
        pending_stores=pending_count,
    )


@router.get("/stats", response_model=IngestionStatsResponse)
async def get_ingestion_stats(
    db: AsyncSession = Depends(get_db),
) -> IngestionStatsResponse:
    """
    Get statistics about ingested data.

    Returns counts of stores, products, discounts, and recent run information.
    """
    from datetime import timedelta

    today = date.today()
    week_ago = today - timedelta(days=7)

    # Counts
    total_stores = (await db.execute(select(func.count(Store.id)))).scalar() or 0
    active_stores = (
        await db.execute(
            select(func.count(Store.id)).where(Store.is_active == True)  # noqa: E712
        )
    ).scalar() or 0
    total_products = (await db.execute(select(func.count(Product.id)))).scalar() or 0
    total_discounts = (await db.execute(select(func.count(Discount.id)))).scalar() or 0
    active_discounts = (
        await db.execute(select(func.count(Discount.id)).where(Discount.valid_to >= today))
    ).scalar() or 0

    # Recent runs
    runs_last_week = (
        await db.execute(
            select(func.count(IngestionRun.id)).where(IngestionRun.run_date >= week_ago)
        )
    ).scalar() or 0
    successful_runs = (
        await db.execute(
            select(func.count(IngestionRun.id)).where(
                IngestionRun.run_date >= week_ago, IngestionRun.status == "completed"
            )
        )
    ).scalar() or 0

    # Last run
    last_run = (
        await db.execute(select(IngestionRun).order_by(IngestionRun.run_date.desc()).limit(1))
    ).scalar_one_or_none()

    return IngestionStatsResponse(
        total_stores=total_stores,
        active_stores=active_stores,
        total_products=total_products,
        total_discounts=total_discounts,
        active_discounts=active_discounts,
        last_run_date=last_run.run_date if last_run else None,
        last_run_status=last_run.status if last_run else None,
        runs_last_7_days=runs_last_week,
        successful_runs_last_7_days=successful_runs,
    )


@router.post("/cleanup", status_code=status.HTTP_202_ACCEPTED)
async def trigger_cleanup(
    days_to_keep: Annotated[int, Query(ge=7, le=365, description="Days of data to retain")] = 30,
) -> dict:
    """
    Trigger cleanup of old ingestion data.

    This will queue a task to delete old raw data and expired discounts.
    """
    from foodplanner.tasks.ingestion import cleanup_old_data_task

    logger.info(f"Cleanup triggered: keeping {days_to_keep} days")

    try:
        task = cleanup_old_data_task.delay(days_to_keep=days_to_keep)
        return {
            "task_id": task.id,
            "status": "queued",
            "message": f"Cleanup task queued. Will retain {days_to_keep} days of data.",
        }
    except Exception as e:
        logger.error(f"Failed to queue cleanup task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue cleanup task: {e}",
        )


def _run_to_response(run: IngestionRun) -> IngestionRunResponse:
    """Convert IngestionRun model to response schema."""
    duration = None
    if run.completed_at and run.started_at:
        duration = (run.completed_at - run.started_at).total_seconds()

    return IngestionRunResponse(
        id=run.id,
        run_date=run.run_date,
        status=run.status,
        task_id=run.task_id,
        trigger_type=run.trigger_type,
        stores_total=run.stores_total,
        stores_completed=run.stores_completed,
        stores_failed=run.stores_failed,
        products_updated=run.products_updated,
        discounts_updated=run.discounts_updated,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=duration,
    )

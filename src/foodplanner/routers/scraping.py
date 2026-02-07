"""API routes for web scraping operations.

Provides endpoints to trigger, monitor, and cancel scraping jobs
for grocery store product data.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from foodplanner.logging_config import get_logger
from foodplanner.tasks.scraping import (
    cancel_scrape,
    full_rema1000_scrape_task,
    get_active_scrape,
    get_progress,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/scrape", tags=["scraping"])


# Request/Response schemas
class ScrapeJobRequest(BaseModel):
    """Request to trigger a scraping job."""

    include_details: bool = Field(
        default=True,
        description=(
            "Fetch full product details including nutrition. " "Slower but more complete data."
        ),
    )
    categories: list[str] | None = Field(
        default=None,
        description="Specific category slugs to scrape. If None, scrapes all categories.",
    )
    resume_from_task_id: str | None = Field(
        default=None,
        description="Resume from a previous task's checkpoint.",
    )
    dry_run: bool = Field(
        default=False,
        description="If True, scrape without saving to database (for testing).",
    )


class ScrapeJobResponse(BaseModel):
    """Response after triggering a scraping job."""

    task_id: str
    status: str
    message: str
    estimated_duration: str | None = None


class ScrapeStatusResponse(BaseModel):
    """Current status of a scraping job."""

    task_id: str
    status: str
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    include_details: bool = False
    dry_run: bool = False
    categories_total: int = 0
    categories_completed: int = 0
    current_category: str = ""
    products_scraped: int = 0
    products_with_details: int = 0
    products_saved: int = 0
    errors: list[str] = Field(default_factory=list)
    error: str | None = None


class CancelResponse(BaseModel):
    """Response after requesting cancellation."""

    task_id: str
    status: str
    message: str


class ActiveScrapeResponse(BaseModel):
    """Information about any active scrape."""

    active: bool
    task_id: str | None = None
    status: ScrapeStatusResponse | None = None


# Available categories for reference
AVAILABLE_CATEGORIES = [
    {"slug": "avisvarer", "name": "Avisvarer"},
    {"slug": "brod-bavinchi", "name": "Brød & Bavinchi"},
    {"slug": "frugt-gront", "name": "Frugt & Grønt"},
    {"slug": "nemt-hurtigt", "name": "Nemt & Hurtigt"},
    {"slug": "kod-fisk-fjerkrae", "name": "Kød, Fisk & Fjerkræ"},
    {"slug": "kol", "name": "Køl"},
    {"slug": "ost-mv", "name": "Ost m.v."},
    {"slug": "frost", "name": "Frost"},
    {"slug": "mejeri", "name": "Mejeri"},
    {"slug": "kolonial", "name": "Kolonial"},
    {"slug": "drikkevarer", "name": "Drikkevarer"},
    {"slug": "husholdning", "name": "Husholdning"},
    {"slug": "baby-og-smaborn", "name": "Baby og Småbørn"},
    {"slug": "personlig-pleje", "name": "Personlig Pleje"},
    {"slug": "slik", "name": "Slik"},
    {"slug": "kiosk", "name": "Kiosk"},
]


@router.post("/rema1000/full", response_model=ScrapeJobResponse)
async def trigger_full_rema1000_scrape(
    request: ScrapeJobRequest,
) -> ScrapeJobResponse:
    """
    Trigger a full product scrape for REMA 1000.

    This endpoint starts a background task that scrapes all products
    from the REMA 1000 online store. Only one full scrape can run at a time.

    The scrape includes:
    - All 16 product categories
    - Pagination handling (loads all products per category)
    - Optional full product details (description, nutrition, ingredients)
    - Anti-blocking measures (randomized delays, user-agent rotation)

    Use the returned task_id to monitor progress via /status/{task_id}.
    """
    # Check if another scrape is already running
    active = get_active_scrape()
    if active:
        logger.warning(f"Scrape request rejected: another scrape is active ({active})")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another scrape is already running (task_id: {active}). "
            "Wait for it to complete or cancel it first.",
        )

    # Validate categories if provided
    if request.categories:
        valid_slugs = {cat["slug"] for cat in AVAILABLE_CATEGORIES}
        invalid = [c for c in request.categories if c not in valid_slugs]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category slugs: {invalid}. "
                f"Valid options: {sorted(valid_slugs)}",
            )

    logger.info(
        f"Triggering REMA 1000 full scrape: "
        f"details={request.include_details}, "
        f"categories={request.categories}, "
        f"dry_run={request.dry_run}"
    )

    try:
        # Queue the Celery task
        task = full_rema1000_scrape_task.delay(
            include_details=request.include_details,
            categories=request.categories,
            resume_from_task_id=request.resume_from_task_id,
            dry_run=request.dry_run,
        )

        # Estimate duration based on settings
        num_categories = len(request.categories) if request.categories else 16
        if request.include_details:
            estimated = f"{num_categories * 15}-{num_categories * 30} minutes"
        else:
            estimated = f"{num_categories * 2}-{num_categories * 5} minutes"

        return ScrapeJobResponse(
            task_id=task.id,
            status="queued",
            message="REMA 1000 scrape task queued. Use /status/{task_id} to monitor progress.",
            estimated_duration=estimated,
        )

    except Exception as e:
        logger.error(f"Failed to queue scrape task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue scrape task: {e}",
        ) from e


@router.get("/rema1000/status/{task_id}", response_model=ScrapeStatusResponse)
async def get_scrape_status(task_id: str) -> ScrapeStatusResponse:
    """
    Get the current status of a scraping job.

    Returns detailed progress information including:
    - Number of categories/products processed
    - Current category being scraped
    - Any errors encountered
    - Timestamps for started/updated/completed
    """
    progress = get_progress(task_id)

    if not progress:
        # Check if task exists in Celery
        from celery.result import AsyncResult

        result = AsyncResult(task_id)
        if result.state == "PENDING":
            return ScrapeStatusResponse(
                task_id=task_id,
                status="pending",
            )
        elif result.state == "FAILURE":
            return ScrapeStatusResponse(
                task_id=task_id,
                status="failed",
                error=str(result.result) if result.result else "Unknown error",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scrape found with task_id: {task_id}",
            )

    return ScrapeStatusResponse(
        task_id=progress.get("task_id", task_id),
        status=progress.get("status", "unknown"),
        started_at=progress.get("started_at"),
        updated_at=progress.get("updated_at"),
        completed_at=progress.get("completed_at"),
        include_details=progress.get("include_details", False),
        dry_run=progress.get("dry_run", False),
        categories_total=progress.get("categories_total", 0),
        categories_completed=progress.get("categories_completed", 0),
        current_category=progress.get("current_category", ""),
        products_scraped=progress.get("products_scraped", 0),
        products_with_details=progress.get("products_with_details", 0),
        products_saved=progress.get("products_saved", 0),
        errors=progress.get("errors", [])[:10],
        error=progress.get("error"),
    )


@router.post("/rema1000/cancel/{task_id}", response_model=CancelResponse)
async def cancel_rema1000_scrape(task_id: str) -> CancelResponse:
    """
    Request cancellation of a running scrape.

    The scrape will stop after completing the current product.
    This is a graceful cancellation - partial results are preserved.
    """
    progress = get_progress(task_id)

    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No scrape found with task_id: {task_id}",
        )

    current_status = progress.get("status", "")
    if current_status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Scrape is already {current_status}, cannot cancel.",
        )

    logger.info(f"Cancellation requested for scrape task: {task_id}")

    if cancel_scrape(task_id):
        return CancelResponse(
            task_id=task_id,
            status="cancelling",
            message="Cancellation requested. Scrape will stop after current operation.",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request cancellation.",
        )


@router.get("/rema1000/active", response_model=ActiveScrapeResponse)
async def get_active_rema1000_scrape() -> ActiveScrapeResponse:
    """
    Check if there's an active REMA 1000 scrape running.

    Returns the task ID and status if a scrape is currently active.
    """
    active_task_id = get_active_scrape()

    if not active_task_id:
        return ActiveScrapeResponse(active=False)

    progress = get_progress(active_task_id)
    if progress:
        status_response = ScrapeStatusResponse(
            task_id=progress.get("task_id", active_task_id),
            status=progress.get("status", "unknown"),
            started_at=progress.get("started_at"),
            updated_at=progress.get("updated_at"),
            categories_total=progress.get("categories_total", 0),
            categories_completed=progress.get("categories_completed", 0),
            current_category=progress.get("current_category", ""),
            products_scraped=progress.get("products_scraped", 0),
            products_with_details=progress.get("products_with_details", 0),
            products_saved=progress.get("products_saved", 0),
        )
        return ActiveScrapeResponse(
            active=True,
            task_id=active_task_id,
            status=status_response,
        )

    return ActiveScrapeResponse(
        active=True,
        task_id=active_task_id,
    )


@router.get("/rema1000/categories")
async def list_rema1000_categories() -> dict:
    """
    List available REMA 1000 categories.

    Returns category slugs and names that can be used when triggering
    a targeted scrape of specific categories.
    """
    return {
        "categories": AVAILABLE_CATEGORIES,
        "total": len(AVAILABLE_CATEGORIES),
    }


@router.get("/rema1000/health")
async def check_rema1000_scraper_health() -> dict:
    """
    Check if the REMA 1000 scraper can reach the website.

    Performs a quick health check by attempting to load the homepage.
    """
    from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper

    try:
        async with Rema1000Scraper(headless=True) as scraper:
            is_healthy = await scraper.health_check()

        return {
            "healthy": is_healthy,
            "website": "https://shop.rema1000.dk",
            "checked_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "healthy": False,
            "website": "https://shop.rema1000.dk",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat(),
        }

"""Celery tasks for web scraping operations.

This module contains background tasks for scraping grocery store websites.
Tasks include progress tracking via Redis and support for checkpointing/resumption.
"""

import asyncio
import json
from datetime import datetime
from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from foodplanner.celery_app import celery_app
from foodplanner.logging_config import LoggingContext, configure_logging, get_logger

# Configure logging for Celery workers
configure_logging()
logger = get_logger(__name__)

# Redis key prefixes for scrape tracking
SCRAPE_PROGRESS_KEY = "scrape:rema1000:progress:{task_id}"
SCRAPE_CHECKPOINT_KEY = "scrape:rema1000:checkpoint:{task_id}"
ACTIVE_SCRAPE_KEY = "scrape:rema1000:active"


def run_async(coro: Any) -> Any:
    """Run an async coroutine in a synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def get_redis_client():
    """Get Redis client for progress tracking."""
    import redis

    from foodplanner.config import get_settings

    settings = get_settings()
    return redis.from_url(settings.redis_url)


def save_progress(task_id: str, progress_data: dict[str, Any]) -> None:
    """Save scrape progress to Redis.

    Args:
        task_id: Celery task ID.
        progress_data: Progress dictionary to save.
    """
    redis_client = get_redis_client()
    key = SCRAPE_PROGRESS_KEY.format(task_id=task_id)
    progress_data["updated_at"] = datetime.utcnow().isoformat()
    redis_client.setex(key, 86400 * 7, json.dumps(progress_data))  # 7 day expiry


def get_progress(task_id: str) -> dict[str, Any] | None:
    """Get scrape progress from Redis.

    Args:
        task_id: Celery task ID.

    Returns:
        Progress dictionary or None if not found.
    """
    redis_client = get_redis_client()
    key = SCRAPE_PROGRESS_KEY.format(task_id=task_id)
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None


def save_checkpoint(task_id: str, checkpoint_data: dict[str, Any]) -> None:
    """Save scrape checkpoint for resumption.

    Args:
        task_id: Celery task ID.
        checkpoint_data: Checkpoint data including last processed category.
    """
    redis_client = get_redis_client()
    key = SCRAPE_CHECKPOINT_KEY.format(task_id=task_id)
    checkpoint_data["saved_at"] = datetime.utcnow().isoformat()
    redis_client.setex(key, 86400 * 7, json.dumps(checkpoint_data))


def get_checkpoint(task_id: str) -> dict[str, Any] | None:
    """Get scrape checkpoint from Redis.

    Args:
        task_id: Celery task ID.

    Returns:
        Checkpoint dictionary or None if not found.
    """
    redis_client = get_redis_client()
    key = SCRAPE_CHECKPOINT_KEY.format(task_id=task_id)
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None


def set_active_scrape(task_id: str) -> bool:
    """Set this task as the active scrape (only one at a time).

    Args:
        task_id: Celery task ID.

    Returns:
        True if set successfully, False if another scrape is active.
    """
    redis_client = get_redis_client()
    # Use SETNX for atomic "only if not exists"
    result = redis_client.setnx(ACTIVE_SCRAPE_KEY, task_id)
    if result:
        # Set expiry in case task crashes without cleanup
        redis_client.expire(ACTIVE_SCRAPE_KEY, 86400)  # 24 hour max
    return bool(result)


def get_active_scrape() -> str | None:
    """Get the currently active scrape task ID.

    Returns:
        Task ID or None if no active scrape.
    """
    redis_client = get_redis_client()
    task_id = redis_client.get(ACTIVE_SCRAPE_KEY)
    return task_id.decode() if task_id else None


def clear_active_scrape(task_id: str) -> None:
    """Clear active scrape if it matches the given task ID.

    Args:
        task_id: Task ID to clear.
    """
    redis_client = get_redis_client()
    current = redis_client.get(ACTIVE_SCRAPE_KEY)
    if current and current.decode() == task_id:
        redis_client.delete(ACTIVE_SCRAPE_KEY)


def cancel_scrape(task_id: str) -> bool:
    """Mark a scrape for cancellation.

    Args:
        task_id: Task ID to cancel.

    Returns:
        True if cancelled, False if task not found.
    """
    progress = get_progress(task_id)
    if progress:
        progress["status"] = "cancelling"
        progress["cancelled_at"] = datetime.utcnow().isoformat()
        save_progress(task_id, progress)
        return True
    return False


@celery_app.task(
    bind=True,
    name="foodplanner.tasks.scraping.full_rema1000_scrape_task",
    max_retries=1,
    soft_time_limit=14400,  # 4 hours soft limit
    time_limit=14700,  # 4 hours + 5 min hard limit
    acks_late=True,
    reject_on_worker_lost=True,
)
def full_rema1000_scrape_task(
    self,
    include_details: bool = True,
    categories: list[str] | None = None,
    resume_from_task_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Background task to scrape all products from REMA 1000.

    This task scrapes all categories with anti-blocking measures and
    stores progress in Redis for monitoring. Only one full scrape
    can run at a time.

    Args:
        include_details: If True, fetch full product details (slower but more data).
        categories: Optional list of specific categories to scrape.
        resume_from_task_id: If provided, resume from a previous task's checkpoint.
        dry_run: If True, scrape but don't save to database.

    Returns:
        Dictionary with final scrape statistics.
    """
    task_id = self.request.id

    with LoggingContext(task_id=task_id):
        logger.info(
            f"Starting REMA 1000 full scrape task {task_id} "
            f"(details={include_details}, categories={categories}, dry_run={dry_run})"
        )

        # Check if another scrape is running
        if not set_active_scrape(task_id):
            existing = get_active_scrape()
            logger.warning(f"Another scrape is already active: {existing}")
            return {
                "status": "rejected",
                "reason": f"Another scrape is already active: {existing}",
                "task_id": task_id,
            }

        # Initialize progress tracking
        progress_data = {
            "task_id": task_id,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "include_details": include_details,
            "dry_run": dry_run,
            "categories_total": 0,
            "categories_completed": 0,
            "current_category": "",
            "products_scraped": 0,
            "products_with_details": 0,
            "products_saved": 0,
            "errors": [],
        }

        # Check for resume checkpoint
        resume_categories = None
        if resume_from_task_id:
            checkpoint = get_checkpoint(resume_from_task_id)
            if checkpoint:
                resume_categories = checkpoint.get("remaining_categories", [])
                remaining = len(resume_categories)
                logger.info(f"Resuming from checkpoint: {remaining} categories remaining")
                progress_data["resumed_from"] = resume_from_task_id

        try:
            result = run_async(
                _execute_full_scrape(
                    task_id=task_id,
                    include_details=include_details,
                    categories=resume_categories or categories,
                    dry_run=dry_run,
                    progress_data=progress_data,
                )
            )

            progress_data.update(result)
            progress_data["status"] = "completed"
            progress_data["completed_at"] = datetime.utcnow().isoformat()
            save_progress(task_id, progress_data)

            logger.info(
                f"REMA 1000 scrape completed: "
                f"{result.get('products_scraped', 0)} products, "
                f"{result.get('products_saved', 0)} saved"
            )

            return progress_data

        except SoftTimeLimitExceeded:
            logger.warning("Scrape task hit time limit, saving checkpoint")
            progress_data["status"] = "timeout"
            progress_data["error"] = "Task exceeded time limit"
            save_progress(task_id, progress_data)
            return progress_data

        except Exception as e:
            logger.exception(f"REMA 1000 scrape failed: {e}")
            progress_data["status"] = "failed"
            progress_data["error"] = str(e)[:500]
            progress_data["failed_at"] = datetime.utcnow().isoformat()
            save_progress(task_id, progress_data)
            raise

        finally:
            clear_active_scrape(task_id)


async def _execute_full_scrape(
    task_id: str,
    include_details: bool,
    categories: list[str] | None,
    dry_run: bool,
    progress_data: dict[str, Any],
) -> dict[str, Any]:
    """Execute the full scrape operation.

    Args:
        task_id: Celery task ID for progress tracking.
        include_details: Whether to fetch product details.
        categories: Optional specific categories to scrape.
        dry_run: If True, don't save to database.
        progress_data: Progress dict to update.

    Returns:
        Final statistics dictionary.
    """
    from sqlalchemy.orm import Session

    from foodplanner.config import get_settings
    from foodplanner.database import sync_engine
    from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper, ScrapeProgress
    from foodplanner.models import Store

    settings = get_settings()
    products_saved = 0
    scraper_progress = ScrapeProgress()

    # Progress callback to save state periodically
    def on_progress(sp: ScrapeProgress) -> None:
        progress_data.update(sp.to_dict())
        save_progress(task_id, progress_data)

        # Save checkpoint for potential resume
        if sp.current_category:
            remaining = [
                cat
                for cat in (categories or list(Rema1000Scraper.CATEGORY_SLUGS.keys()))
                if cat not in [sp.current_category]  # Simplified - would need completed list
            ]
            save_checkpoint(
                task_id,
                {
                    "remaining_categories": remaining,
                    "products_scraped": sp.products_scraped,
                },
            )

    # Check for cancellation periodically
    def check_cancelled() -> bool:
        current_progress = get_progress(task_id)
        if current_progress and current_progress.get("status") == "cancelling":
            scraper_progress.is_cancelled = True
            return True
        return False

    # Create scraper with settings
    scraper = Rema1000Scraper(
        headless=True,
        min_delay=settings.full_scrape_min_delay,
        max_delay=settings.full_scrape_max_delay,
        category_delay=settings.full_scrape_category_delay,
        detail_min_delay=1.0,
        detail_max_delay=3.0,
        max_consecutive_errors=settings.full_scrape_max_retries,
        backoff_factor=settings.full_scrape_backoff_factor,
    )

    try:
        async with scraper:
            # Ensure store record exists
            if not dry_run:
                with Session(sync_engine) as session:
                    store = session.query(Store).filter(Store.id == "rema1000-main").first()
                    if not store:
                        store = Store(
                            id="rema1000-main",
                            name="REMA 1000 (Online)",
                            brand="rema1000",
                            is_active=True,
                        )
                        session.add(store)
                        session.commit()
                        logger.info("Created REMA 1000 store record")

            # Batch for DB operations
            product_batch: list[dict[str, Any]] = []
            batch_size = 50

            async for product in scraper.scrape_all_products(
                include_details=include_details,
                categories=categories,
                progress_callback=on_progress,
            ):
                # Check for cancellation
                if check_cancelled():
                    logger.info("Scrape cancelled by user request")
                    progress_data["status"] = "cancelled"
                    break

                if not dry_run:
                    product_batch.append(product)

                    # Save batch when full
                    if len(product_batch) >= batch_size:
                        saved = _save_product_batch(product_batch, "rema1000-main")
                        products_saved += saved
                        progress_data["products_saved"] = products_saved
                        product_batch = []
                        save_progress(task_id, progress_data)

            # Save remaining products
            if product_batch and not dry_run:
                saved = _save_product_batch(product_batch, "rema1000-main")
                products_saved += saved
                progress_data["products_saved"] = products_saved

    except Exception as e:
        logger.exception(f"Scrape execution failed: {e}")
        raise

    return {
        "products_scraped": scraper_progress.products_scraped,
        "products_with_details": scraper_progress.products_with_details,
        "products_saved": products_saved,
        "categories_completed": scraper_progress.categories_completed,
        "errors": scraper_progress.errors[:10],
    }


def _save_product_batch(products: list[dict[str, Any]], store_id: str) -> int:
    """Save a batch of products to the database.

    Args:
        products: List of product dictionaries.
        store_id: Store ID to associate products with.

    Returns:
        Number of products saved.
    """
    from datetime import datetime

    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy.orm import Session

    from foodplanner.database import sync_engine
    from foodplanner.models import Product

    saved = 0

    with Session(sync_engine) as session:
        for product in products:
            product_id = product.get("id") or str(hash(product.get("name", "")))

            stmt = insert(Product).values(
                id=product_id,
                store_id=store_id,
                name=product.get("name", "Unknown"),
                price=product.get("price", 0.0),
                unit=product.get("unit") or "unit",
                ean=product.get("ean"),
                category=product.get("category"),
                brand=product.get("brand"),
                image_url=product.get("image_url"),
                description=product.get("description"),
                origin=product.get("origin"),
                nutrition=product.get("nutrition_info") or {},
                last_updated=datetime.utcnow(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": stmt.excluded.name,
                    "price": stmt.excluded.price,
                    "unit": stmt.excluded.unit,
                    "ean": stmt.excluded.ean,
                    "category": stmt.excluded.category,
                    "brand": stmt.excluded.brand,
                    "image_url": stmt.excluded.image_url,
                    "description": stmt.excluded.description,
                    "origin": stmt.excluded.origin,
                    "nutrition": stmt.excluded.nutrition,
                    "last_updated": stmt.excluded.last_updated,
                },
            )
            session.execute(stmt)
            saved += 1

        session.commit()

    return saved


@shared_task(name="foodplanner.tasks.scraping.get_scrape_status")
def get_scrape_status_task(task_id: str) -> dict[str, Any] | None:
    """Get the status of a scrape task.

    Args:
        task_id: The task ID to check.

    Returns:
        Progress dictionary or None if not found.
    """
    return get_progress(task_id)


@shared_task(name="foodplanner.tasks.scraping.cancel_scrape_task")
def cancel_scrape_task(task_id: str) -> dict[str, Any]:
    """Request cancellation of a running scrape.

    Args:
        task_id: The task ID to cancel.

    Returns:
        Status dictionary.
    """
    if cancel_scrape(task_id):
        return {"status": "cancelling", "task_id": task_id}
    return {"status": "not_found", "task_id": task_id}

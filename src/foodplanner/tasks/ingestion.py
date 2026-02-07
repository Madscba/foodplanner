"""Celery tasks for data ingestion pipeline."""

import asyncio
from typing import Any

from celery import shared_task

from foodplanner.celery_app import celery_app
from foodplanner.logging_config import LoggingContext, configure_logging, get_logger

# Configure logging for Celery workers
configure_logging()
logger = get_logger(__name__)


def run_async(coro: Any) -> Any:
    """Run an async coroutine in a synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If there's already an event loop, create a new one
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop exists, create one
        return asyncio.run(coro)


@celery_app.task(
    bind=True,
    name="foodplanner.tasks.ingestion.run_daily_ingestion_task",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,  # Max 1 hour between retries
    retry_jitter=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_daily_ingestion_task(
    self,
    store_ids: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Celery task to run daily ingestion pipeline.

    This task is scheduled to run daily at 2:00 AM by Celery Beat.
    It can also be triggered manually via the API.

    Args:
        store_ids: Optional list of specific store IDs to ingest.
                   If None, ingests all user-selected stores.
        force: Force re-ingestion even if already run today.

    Returns:
        dict with ingestion results summary.
    """
    from foodplanner.ingest.batch_ingest import run_daily_ingestion

    task_id = self.request.id
    trigger_type = "scheduled" if not self.request.called_directly else "manual"

    with LoggingContext(task_id=task_id):
        logger.info(
            f"Starting daily ingestion task {task_id} "
            f"(stores={store_ids}, force={force}, trigger={trigger_type})"
        )

        try:
            result = run_async(
                run_daily_ingestion(
                    store_ids=store_ids,
                    task_id=task_id,
                    force=force,
                    trigger_type=trigger_type,
                )
            )

            status = result.get("status", "unknown")
            if status in ("completed", "partial", "skipped", "no_stores"):
                logger.info(f"Ingestion task {task_id} finished with status: {status}")
            else:
                logger.warning(f"Ingestion task {task_id} finished with status: {status}")

            return result

        except Exception as e:
            logger.exception(f"Ingestion task {task_id} failed with error: {e}")
            # Re-raise to trigger Celery retry mechanism
            raise


@celery_app.task(
    bind=True,
    name="foodplanner.tasks.ingestion.ingest_single_store_task",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True,
)
def ingest_single_store_task(self, store_id: str, run_id: int) -> dict[str, Any]:
    """
    Celery task to ingest data for a single store.

    This allows parallel processing of multiple stores when needed.

    Args:
        store_id: The store ID to ingest.
        run_id: The ingestion run ID for tracking.

    Returns:
        dict with store ingestion results.
    """
    from foodplanner.ingest.batch_ingest import ingest_store

    task_id = self.request.id

    with LoggingContext(task_id=task_id, store_id=store_id, run_id=run_id):
        logger.info(f"Starting store ingestion task for store {store_id}")

        try:
            result = run_async(ingest_store(store_id=store_id, run_id=run_id))

            status = result.get("status", "unknown")
            if status == "completed":
                logger.info(
                    f"Store {store_id} ingestion completed: "
                    f"{result.get('products_inserted', 0)} products, "
                    f"{result.get('discounts_inserted', 0)} discounts"
                )
            else:
                logger.warning(f"Store {store_id} ingestion finished with status: {status}")

            return result

        except Exception as e:
            logger.exception(f"Store {store_id} ingestion failed: {e}")
            raise


@shared_task(
    name="foodplanner.tasks.ingestion.cleanup_old_data_task",
    acks_late=True,
)
def cleanup_old_data_task(days_to_keep: int = 30) -> dict[str, int]:
    """
    Cleanup old raw ingestion data and expired discounts.

    This task should be scheduled to run weekly to keep the database clean.

    Args:
        days_to_keep: Number of days of raw data to retain.

    Returns:
        dict with cleanup statistics.
    """
    from foodplanner.ingest.batch_ingest import cleanup_old_data

    logger.info(f"Starting cleanup task, keeping {days_to_keep} days of data")

    try:
        result = run_async(cleanup_old_data(days_to_keep=days_to_keep))
        logger.info(
            f"Cleanup completed: {result.get('raw_data_deleted', 0)} raw records, "
            f"{result.get('discounts_deleted', 0)} expired discounts"
        )
        return result

    except Exception as e:
        logger.exception(f"Cleanup task failed: {e}")
        raise


@shared_task(
    name="foodplanner.tasks.ingestion.health_check_task",
)
def health_check_task() -> dict[str, Any]:
    """
    Check the health of the ingestion system.

    Returns:
        dict with health status of various components.
    """
    logger.info("Running ingestion health check")

    results: dict[str, Any] = {
        "database": False,
        "redis": False,
    }

    # Check database connection
    try:
        from sqlalchemy import text
        from sqlalchemy.orm import Session

        from foodplanner.database import sync_engine

        with Session(sync_engine) as session:
            session.execute(text("SELECT 1"))
            results["database"] = True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        results["database_error"] = str(e)

    # Check Redis connection
    try:
        from foodplanner.celery_app import celery_app

        celery_app.control.ping(timeout=5)
        results["redis"] = True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        results["redis_error"] = str(e)

    results["healthy"] = all(results.get(k, False) for k in ["database", "redis"])

    logger.info(f"Health check completed: healthy={results['healthy']}")
    return results

"""Daily batch ingestion pipeline for scraping data and storing in DB."""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from foodplanner.database import sync_engine
from foodplanner.logging_config import LoggingContext, get_logger
from foodplanner.models import (
    Base,
    Discount,
    IngestionRun,
    Product,
    RawIngestionData,
    Store,
    StoreIngestionStatus,
    UserStorePreference,
)

logger = get_logger(__name__)


class IngestionResult:
    """Result of an ingestion operation."""

    def __init__(self) -> None:
        self.stores_total: int = 0
        self.stores_completed: int = 0
        self.stores_failed: int = 0
        self.products_updated: int = 0
        self.discounts_updated: int = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "stores_total": self.stores_total,
            "stores_completed": self.stores_completed,
            "stores_failed": self.stores_failed,
            "products_updated": self.products_updated,
            "discounts_updated": self.discounts_updated,
            "errors": self.errors,
        }


async def run_daily_ingestion(
    store_ids: list[str] | None = None,
    task_id: str | None = None,
    force: bool = False,
    trigger_type: str = "scheduled",
) -> dict[str, Any]:
    """
    Main entry point for daily ingestion pipeline.

    Args:
        store_ids: Optional list of specific store IDs to ingest.
                   If None, ingests stores that users have selected.
        task_id: Celery task ID for tracking.
        force: Force re-ingestion even if already run today.
        trigger_type: How the ingestion was triggered (scheduled, manual, retry).

    Returns:
        Dictionary with ingestion results summary.
    """
    run_date = date.today()
    result = IngestionResult()

    with LoggingContext(task_id=task_id):
        logger.info(f"Starting daily ingestion for {run_date}")

        # Create tables if they don't exist
        Base.metadata.create_all(sync_engine)

        with Session(sync_engine) as session:
            # Check if already run today (unless forced)
            if not force:
                existing_run = session.execute(
                    select(IngestionRun).where(
                        IngestionRun.run_date == run_date,
                        IngestionRun.status == "completed",
                    )
                ).scalar_one_or_none()

                if existing_run:
                    logger.info(f"Ingestion already completed for {run_date}")
                    return {
                        "status": "skipped",
                        "message": f"Ingestion already completed for {run_date}",
                        "run_id": existing_run.id,
                    }

            # Get stores to ingest
            if store_ids:
                stores_to_ingest = store_ids
            else:
                stores_to_ingest = _get_user_selected_stores(session)

            if not stores_to_ingest:
                logger.warning("No stores configured for ingestion")
                return {
                    "status": "no_stores",
                    "message": "No stores configured for ingestion",
                }

            result.stores_total = len(stores_to_ingest)

            # Create ingestion run record
            run = IngestionRun(
                run_date=run_date,
                status="running",
                task_id=task_id,
                trigger_type=trigger_type,
                stores_total=result.stores_total,
                started_at=datetime.utcnow(),
            )
            session.add(run)
            session.commit()

            logger.info(f"Created ingestion run {run.id} for {len(stores_to_ingest)} stores")

            # Process each store
            with LoggingContext(run_id=run.id):
                for store_id in stores_to_ingest:
                    store_result = await ingest_store(
                        store_id=store_id,
                        run_id=run.id,
                        session=session,
                    )

                    if store_result.get("status") == "completed":
                        result.stores_completed += 1
                        result.products_updated += store_result.get("products_inserted", 0)
                        result.discounts_updated += store_result.get("discounts_inserted", 0)
                    else:
                        result.stores_failed += 1
                        if error := store_result.get("error"):
                            result.errors.append(f"{store_id}: {error}")

                # Update run record
                run.status = "completed" if result.stores_failed == 0 else "partial"
                if result.stores_completed == 0 and result.stores_failed > 0:
                    run.status = "failed"

                run.stores_completed = result.stores_completed
                run.stores_failed = result.stores_failed
                run.products_updated = result.products_updated
                run.discounts_updated = result.discounts_updated
                run.completed_at = datetime.utcnow()

                if result.errors:
                    run.error_message = "; ".join(result.errors[:5])  # Store first 5 errors

                session.commit()

            logger.info(
                f"Ingestion completed: {result.stores_completed}/{result.stores_total} stores, "
                f"{result.products_updated} products, {result.discounts_updated} discounts"
            )

            return {
                "status": run.status,
                "run_id": run.id,
                **result.to_dict(),
            }


async def ingest_store(
    store_id: str,
    run_id: int,
    session: Session | None = None,
) -> dict[str, Any]:
    """
    Ingest data for a single store using web scraping.

    Args:
        store_id: The store ID to ingest.
        run_id: The ingestion run ID for tracking.
        session: Optional existing database session.

    Returns:
        Dictionary with store ingestion results.
    """
    own_session = session is None
    if own_session:
        session = Session(sync_engine)

    try:
        with LoggingContext(store_id=store_id, run_id=run_id):
            logger.info(f"Starting ingestion for store {store_id}")

            # Create or update store status record
            status = StoreIngestionStatus(
                run_id=run_id,
                store_id=store_id,
                status="running",
                started_at=datetime.utcnow(),
            )
            session.add(status)
            session.commit()

            try:
                # Ensure store exists in database
                await _ensure_store_exists(session, store_id)

                # Get the appropriate scraper for this store
                from foodplanner.ingest.scrapers import get_scraper_for_store

                scraper = get_scraper_for_store(store_id)
                if not scraper:
                    raise ValueError(f"No scraper available for store {store_id}")

                # Scrape products
                async with scraper:
                    products = await scraper.scrape_products()

                # Archive raw response
                _archive_raw_data(
                    session=session,
                    run_id=run_id,
                    store_id=store_id,
                    endpoint=f"/scrape/{store_id}",
                    params={},
                    response_data={"products_count": len(products)},
                    status_code=200,
                )

                status.products_fetched = len(products)
                status.discounts_fetched = 0

                # Upsert products
                products_inserted = _upsert_scraped_products(
                    session=session,
                    store_id=store_id,
                    products=products,
                )

                status.products_inserted = products_inserted
                status.discounts_inserted = 0
                status.status = "completed"
                status.completed_at = datetime.utcnow()

                # Update store's last ingestion timestamp
                session.execute(
                    Store.__table__.update()
                    .where(Store.id == store_id)
                    .values(last_ingested_at=datetime.utcnow())
                )

                session.commit()

                logger.info(f"Store {store_id} completed: {products_inserted} products")

                return {
                    "status": "completed",
                    "store_id": store_id,
                    "products_fetched": len(products),
                    "products_inserted": products_inserted,
                    "discounts_inserted": 0,
                }

            except Exception as e:
                logger.exception(f"Unexpected error ingesting store {store_id}")
                status.status = "failed"
                status.error_message = str(e)[:500]
                status.completed_at = datetime.utcnow()
                session.commit()

                return {
                    "status": "failed",
                    "store_id": store_id,
                    "error": str(e),
                }

    finally:
        if own_session:
            session.close()


def _get_user_selected_stores(session: Session) -> list[str]:
    """Get unique store IDs that users have selected."""
    result = session.execute(
        select(UserStorePreference.store_id)
        .where(UserStorePreference.is_active == True)  # noqa: E712
        .distinct()
    )
    store_ids = [row[0] for row in result.all()]

    # Also get any stores marked as active that we should always sync
    active_stores = session.execute(
        select(Store.id).where(Store.is_active == True)  # noqa: E712
    )
    for row in active_stores.all():
        if row[0] not in store_ids:
            store_ids.append(row[0])

    return store_ids


async def _ensure_store_exists(session: Session, store_id: str) -> None:
    """Ensure store record exists in database."""
    existing = session.execute(select(Store).where(Store.id == store_id)).scalar_one_or_none()

    if not existing:
        # Create placeholder store record
        store = Store(
            id=store_id,
            name=f"Store {store_id}",
            brand="unknown",
            is_active=True,
        )
        session.add(store)
        session.commit()
        logger.info(f"Created placeholder store record for {store_id}")


def _upsert_scraped_products(
    session: Session,
    store_id: str,
    products: list[dict[str, Any]],
) -> int:
    """
    Upsert products from scraped data.

    Args:
        session: Database session.
        store_id: The store ID.
        products: List of product dictionaries from scraper.

    Returns:
        Number of products inserted/updated.
    """
    products_inserted = 0

    for product in products:
        product_id = product.get("id") or product.get("ean") or str(hash(product.get("name", "")))

        # Upsert product
        product_stmt = insert(Product).values(
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
            last_updated=datetime.utcnow(),
        )
        product_stmt = product_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": product_stmt.excluded.name,
                "price": product_stmt.excluded.price,
                "unit": product_stmt.excluded.unit,
                "ean": product_stmt.excluded.ean,
                "category": product_stmt.excluded.category,
                "brand": product_stmt.excluded.brand,
                "image_url": product_stmt.excluded.image_url,
                "description": product_stmt.excluded.description,
                "origin": product_stmt.excluded.origin,
                "last_updated": product_stmt.excluded.last_updated,
            },
        )
        session.execute(product_stmt)
        products_inserted += 1

    session.commit()
    return products_inserted


def _archive_raw_data(
    session: Session,
    run_id: int,
    store_id: str,
    endpoint: str,
    params: dict[str, Any],
    response_data: Any,
    status_code: int,
) -> None:
    """Archive raw API response for replayability."""
    raw_data = RawIngestionData(
        run_id=run_id,
        store_id=store_id,
        endpoint=endpoint,
        request_params=params,
        response_data=response_data if isinstance(response_data, (dict, list)) else {},
        response_status=status_code,
        fetched_at=datetime.utcnow(),
    )
    session.add(raw_data)
    session.commit()


async def cleanup_old_data(days_to_keep: int = 30) -> dict[str, int]:
    """
    Cleanup old raw ingestion data and expired discounts.

    Args:
        days_to_keep: Number of days of raw data to retain.

    Returns:
        Dictionary with cleanup statistics.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
    discount_cutoff = date.today() - timedelta(days=7)  # Keep discounts 7 days past expiry

    logger.info(f"Cleaning up data older than {cutoff_date.date()}")

    with Session(sync_engine) as session:
        # Delete old raw data
        raw_deleted = session.execute(
            delete(RawIngestionData).where(RawIngestionData.fetched_at < cutoff_date)
        ).rowcount

        # Delete expired discounts
        discounts_deleted = session.execute(
            delete(Discount).where(Discount.valid_to < discount_cutoff)
        ).rowcount

        session.commit()

        logger.info(
            f"Cleanup completed: {raw_deleted} raw records, {discounts_deleted} expired discounts"
        )

        return {
            "raw_data_deleted": raw_deleted,
            "discounts_deleted": discounts_deleted,
        }


async def get_ingestion_stats(session: Session) -> dict[str, Any]:
    """Get statistics about recent ingestion runs."""
    # Recent runs
    recent_runs = (
        session.execute(select(IngestionRun).order_by(IngestionRun.run_date.desc()).limit(10))
        .scalars()
        .all()
    )

    # Totals
    total_products = session.execute(select(func.count(Product.id))).scalar() or 0
    total_discounts = session.execute(select(func.count(Discount.id))).scalar() or 0
    active_stores = (
        session.execute(
            select(func.count(Store.id)).where(Store.is_active == True)  # noqa: E712
        ).scalar()
        or 0
    )

    return {
        "recent_runs": [
            {
                "id": r.id,
                "run_date": r.run_date.isoformat(),
                "status": r.status,
                "stores_completed": r.stores_completed,
                "stores_failed": r.stores_failed,
                "products_updated": r.products_updated,
                "discounts_updated": r.discounts_updated,
            }
            for r in recent_runs
        ],
        "totals": {
            "products": total_products,
            "discounts": total_discounts,
            "active_stores": active_stores,
        },
    }


if __name__ == "__main__":
    import asyncio

    from foodplanner.logging_config import configure_logging

    configure_logging(log_level="INFO")
    asyncio.run(run_daily_ingestion(trigger_type="manual"))

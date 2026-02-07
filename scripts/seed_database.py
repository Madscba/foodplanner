#!/usr/bin/env python
"""
Database seeding script for initial data population.

This script is designed to run automatically when the Docker infrastructure
starts up. It will:

1. Wait for all required services to be healthy
2. Create the REMA 1000 store record if it doesn't exist
3. Check if data already exists (skip if already seeded)
4. Scrape products from configured categories
5. Optionally sync products to the Neo4j graph database

Run with: python scripts/seed_database.py

Environment Variables:
    SEED_CATEGORIES: Comma-separated list of category slugs to scrape
    SEED_LIMIT_PER_CATEGORY: Max products per category (default: 100)
    SEED_SKIP_IF_EXISTS: Skip seeding if products exist (default: true)
    SEED_SYNC_TO_GRAPH: Sync products to Neo4j after seeding (default: true)
    DATABASE_URL: PostgreSQL connection string
    NEO4J_URI: Neo4j connection URI
"""

import asyncio
import os
import sys
import time
from urllib.parse import urlparse

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from foodplanner.config import settings
from foodplanner.database import Base
from foodplanner.ingest.batch_ingest import _upsert_scraped_products
from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper
from foodplanner.logging_config import configure_logging, get_logger
from foodplanner.models import Product, Store

# Configure logging
configure_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger(__name__)

# Default categories to seed (food-related categories for meal planning)
DEFAULT_CATEGORIES = [
    "avisvarer",  # Weekly offers
    "brod-bavinchi",  # Bread
    "frugt-gront",  # Fruits & Vegetables
    "kod-fisk-fjerkrae",  # Meat, Fish & Poultry
    "kol",  # Refrigerated
    "ost-mv",  # Cheese
    "frost",  # Frozen
    "mejeri",  # Dairy
    "kolonial",  # Groceries
]

# Configuration from environment
SEED_CATEGORIES = os.getenv("SEED_CATEGORIES", ",".join(DEFAULT_CATEGORIES)).split(",")
SEED_LIMIT_PER_CATEGORY = int(os.getenv("SEED_LIMIT_PER_CATEGORY", "100"))
SEED_SKIP_IF_EXISTS = os.getenv("SEED_SKIP_IF_EXISTS", "true").lower() == "true"
SEED_SYNC_TO_GRAPH = os.getenv("SEED_SYNC_TO_GRAPH", "true").lower() == "true"
SEED_MIN_PRODUCTS = int(os.getenv("SEED_MIN_PRODUCTS", "100"))


def get_sync_engine():
    """Create synchronous database engine."""
    database_url = settings.database_url.replace("+asyncpg", "")
    return create_engine(database_url, echo=False)


def wait_for_postgres(max_retries: int = 30, retry_delay: int = 2) -> bool:
    """Wait for PostgreSQL to be available."""
    logger.info("Waiting for PostgreSQL to be ready...")

    for attempt in range(max_retries):
        try:
            engine = get_sync_engine()
            with engine.connect() as conn:
                conn.execute(select(1))
            logger.info("PostgreSQL is ready")
            return True
        except Exception as e:
            logger.debug(f"PostgreSQL not ready (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(retry_delay)

    logger.error("PostgreSQL did not become ready in time")
    return False


def wait_for_neo4j(max_retries: int = 30, retry_delay: int = 2) -> bool:
    """Wait for Neo4j to be available."""
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")

    # Extract host and port from bolt URI
    parsed = urlparse(neo4j_uri.replace("bolt://", "http://"))
    host = parsed.hostname or "localhost"
    port = 7474  # Neo4j HTTP port for health check

    logger.info(f"Waiting for Neo4j at {host}:{port}...")

    for attempt in range(max_retries):
        try:
            response = httpx.get(f"http://{host}:{port}", timeout=5)
            if response.status_code == 200:
                logger.info("Neo4j is ready")
                return True
        except Exception as e:
            logger.debug(f"Neo4j not ready (attempt {attempt + 1}/{max_retries}): {e}")
        time.sleep(retry_delay)

    logger.warning("Neo4j did not become ready - continuing without graph sync")
    return False


def init_database(engine) -> None:
    """Initialize database tables."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(engine)
    logger.info("Database tables initialized")


def create_rema_store(session: Session) -> None:
    """Create REMA 1000 store record if it doesn't exist."""
    existing = session.execute(select(Store).where(Store.id == "rema1000")).scalar_one_or_none()

    if not existing:
        store = Store(
            id="rema1000",
            name="REMA 1000",
            brand="rema1000",
            is_active=True,
        )
        session.add(store)
        session.commit()
        logger.info("Created REMA 1000 store record")
    else:
        logger.info("REMA 1000 store record already exists")


def check_existing_data(session: Session) -> int:
    """Check how many products already exist in the database."""
    count = (
        session.execute(
            select(func.count(Product.id)).where(Product.store_id == "rema1000")
        ).scalar()
        or 0
    )
    return count


async def scrape_category(
    scraper: Rema1000Scraper,
    category: str,
    limit: int,
) -> list[dict]:
    """Scrape products from a single category."""
    logger.info(f"Scraping category: {category} (limit: {limit})")
    try:
        products = await scraper.scrape_products(category=category, limit=limit)
        logger.info(f"Scraped {len(products)} products from {category}")
        return products
    except Exception as e:
        logger.error(f"Failed to scrape category {category}: {e}")
        return []


async def scrape_all_categories(
    categories: list[str],
    limit_per_category: int,
) -> list[dict]:
    """Scrape products from all configured categories."""
    all_products = []

    async with Rema1000Scraper(headless=True) as scraper:
        for category in categories:
            category = category.strip()
            if not category:
                continue

            products = await scrape_category(scraper, category, limit_per_category)
            all_products.extend(products)

            # Small delay between categories to be respectful
            if category != categories[-1]:
                await asyncio.sleep(2)

    return all_products


def store_products(session: Session, products: list[dict]) -> int:
    """Store scraped products in the database."""
    if not products:
        return 0

    logger.info(f"Storing {len(products)} products in database...")
    inserted = _upsert_scraped_products(
        session=session,
        store_id="rema1000",
        products=products,
    )
    logger.info(f"Stored {inserted} products in database")
    return inserted


async def sync_to_graph() -> bool:
    """Sync products to Neo4j graph database."""
    if not SEED_SYNC_TO_GRAPH:
        logger.info("Graph sync disabled, skipping...")
        return True

    try:
        from foodplanner.tasks.graph_ingestion import _sync_products_to_graph

        logger.info("Syncing products to Neo4j graph database...")
        result = await _sync_products_to_graph()

        status = result.get("status", "unknown")
        products_synced = result.get("products_synced", 0)
        logger.info(f"Graph sync completed: status={status}, products={products_synced}")

        return status in ("completed", "partial")
    except Exception as e:
        logger.warning(f"Graph sync failed (non-fatal): {e}")
        return False


async def seed_database() -> dict:
    """
    Main seeding function.

    Returns:
        Dictionary with seeding results.
    """
    results = {
        "status": "unknown",
        "products_scraped": 0,
        "products_stored": 0,
        "categories_processed": 0,
        "graph_synced": False,
        "skipped": False,
    }

    # Wait for services
    if not wait_for_postgres():
        results["status"] = "failed"
        results["error"] = "PostgreSQL not available"
        return results

    neo4j_available = wait_for_neo4j()

    # Initialize database
    engine = get_sync_engine()
    init_database(engine)

    with Session(engine) as session:
        # Create store record
        create_rema_store(session)

        # Check existing data
        existing_count = check_existing_data(session)
        logger.info(f"Found {existing_count} existing products")

        if SEED_SKIP_IF_EXISTS and existing_count >= SEED_MIN_PRODUCTS:
            logger.info(
                f"Database already has {existing_count} products "
                f"(minimum: {SEED_MIN_PRODUCTS}), skipping seed"
            )
            results["status"] = "skipped"
            results["skipped"] = True
            results["existing_products"] = existing_count
            return results

        # Scrape products
        logger.info(f"Scraping {len(SEED_CATEGORIES)} categories...")
        products = await scrape_all_categories(
            categories=SEED_CATEGORIES,
            limit_per_category=SEED_LIMIT_PER_CATEGORY,
        )

        results["products_scraped"] = len(products)
        results["categories_processed"] = len(SEED_CATEGORIES)

        if not products:
            logger.warning("No products scraped!")
            results["status"] = "warning"
            results["warning"] = "No products were scraped"
            return results

        # Store products
        stored = store_products(session, products)
        results["products_stored"] = stored

    # Sync to graph if available
    if neo4j_available and SEED_SYNC_TO_GRAPH:
        results["graph_synced"] = await sync_to_graph()

    results["status"] = "completed"
    logger.info(f"Seeding completed: {results}")
    return results


def main():
    """Entry point for the seed script."""
    logger.info("=" * 60)
    logger.info("Database Seeding Script")
    logger.info("=" * 60)
    logger.info(f"Categories: {SEED_CATEGORIES}")
    logger.info(f"Limit per category: {SEED_LIMIT_PER_CATEGORY}")
    logger.info(f"Skip if exists: {SEED_SKIP_IF_EXISTS}")
    logger.info(f"Minimum products: {SEED_MIN_PRODUCTS}")
    logger.info(f"Sync to graph: {SEED_SYNC_TO_GRAPH}")
    logger.info("=" * 60)

    try:
        results = asyncio.run(seed_database())

        logger.info("=" * 60)
        logger.info("Seeding Results:")
        for key, value in results.items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 60)

        if results["status"] in ("completed", "skipped"):
            sys.exit(0)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Seeding interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Seeding failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

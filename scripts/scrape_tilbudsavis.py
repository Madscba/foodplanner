"""Script to scrape tilbudsavis (weekly offers) from REMA 1000 and store in database.

Run with: uv run python scripts/scrape_tilbudsavis.py

Requires PostgreSQL to be running (via Docker or locally).
"""

import asyncio
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from foodplanner.config import settings
from foodplanner.database import Base
from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper, ScrapeProgress
from foodplanner.logging_config import configure_logging, get_logger
from foodplanner.models import Product, Store

configure_logging(log_level="INFO")
logger = get_logger(__name__)


def get_engine():
    """Create database engine using settings."""
    # Convert async URL to sync URL for this script
    database_url = settings.database_url.replace("+asyncpg", "")
    return create_engine(database_url, echo=False)


async def scrape_tilbudsavis():
    """Scrape tilbudsavis products and store in database."""

    engine = get_engine()

    # Ensure tables exist
    Base.metadata.create_all(engine)

    # Ensure store exists
    with Session(engine) as session:
        store = session.execute(
            select(Store).where(Store.id == "rema1000-main")
        ).scalar_one_or_none()
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

    # Scrape avisvarer (tilbudsavis)
    logger.info("Starting tilbudsavis scrape...")

    scraper = Rema1000Scraper(
        headless=True,
        min_delay=1.5,
        max_delay=3.0,
        detail_min_delay=1.0,
        detail_max_delay=2.0,
    )

    products_scraped = 0
    products_saved = 0
    progress = ScrapeProgress()

    try:
        async with scraper:
            # First, let's just get the listing without details to see what we have
            logger.info("Scraping avisvarer category (tilbudsavis)...")

            products = []
            async for product in scraper.scrape_category_products_full(
                category_slug="avisvarer",
                include_details=False,  # Start without details for speed
                progress=progress,
            ):
                products.append(product)
                products_scraped += 1

                if products_scraped % 10 == 0:
                    logger.info(f"Scraped {products_scraped} products...")

            logger.info(f"Total products found in tilbudsavis: {len(products)}")

            # Show sample products
            logger.info("\n--- Sample tilbudsavis products ---")
            for p in products[:10]:
                offer_tag = " [TILBUD]" if p.get("is_offer") else ""
                logger.info(f"  - {p['name']}: {p['price']:.2f} kr{offer_tag}")

            # Save to database
            logger.info("\nSaving products to database...")
            with Session(engine) as session:
                for product in products:
                    product_id = product.get("id") or str(hash(product.get("name", "")))

                    # Check if product exists
                    existing = session.execute(
                        select(Product).where(Product.id == product_id)
                    ).scalar_one_or_none()

                    if existing:
                        # Update existing
                        existing.name = product.get("name", "Unknown")
                        existing.price = product.get("price", 0.0)
                        existing.unit = product.get("unit") or "stk"
                        existing.category = product.get("category")
                        existing.image_url = product.get("image_url")
                        existing.description = product.get("description")
                        existing.origin = product.get("origin")
                        existing.nutrition = {
                            "is_offer": product.get("is_offer", False),
                            "scraped_from": "tilbudsavis",
                            "scraped_at": datetime.utcnow().isoformat(),
                        }
                        existing.last_updated = datetime.utcnow()
                    else:
                        # Insert new
                        new_product = Product(
                            id=product_id,
                            store_id="rema1000-main",
                            name=product.get("name", "Unknown"),
                            price=product.get("price", 0.0),
                            unit=product.get("unit") or "stk",
                            ean=product.get("ean"),
                            category=product.get("category"),
                            brand=product.get("brand"),
                            image_url=product.get("image_url"),
                            description=product.get("description"),
                            origin=product.get("origin"),
                            nutrition={
                                "is_offer": product.get("is_offer", False),
                                "scraped_from": "tilbudsavis",
                                "scraped_at": datetime.utcnow().isoformat(),
                            },
                            last_updated=datetime.utcnow(),
                        )
                        session.add(new_product)

                    products_saved += 1

                session.commit()

            logger.info("\n=== Tilbudsavis Scrape Complete ===")
            logger.info(f"Products scraped: {products_scraped}")
            logger.info(f"Products saved to database: {products_saved}")

            return {
                "status": "completed",
                "products_scraped": products_scraped,
                "products_saved": products_saved,
            }

    except Exception as e:
        logger.exception(f"Scrape failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "products_scraped": products_scraped,
            "products_saved": products_saved,
        }


if __name__ == "__main__":
    result = asyncio.run(scrape_tilbudsavis())
    print(f"\nResult: {result}")

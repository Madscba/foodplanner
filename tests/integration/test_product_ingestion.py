"""Integration tests for product ingestion into SQL database.

These tests scrape real products from REMA 1000 and ingest them into a test database.
Run with: uv run pytest tests/integration/test_product_ingestion.py -v -s

Requirements:
    - PostgreSQL database (use Docker: docker-compose up -d db)
"""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from foodplanner.ingest.batch_ingest import _upsert_scraped_products
from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper
from foodplanner.models import Product, Store


@pytest.fixture
def test_db(test_db_engine):
    """Create a PostgreSQL test database session with a test store.

    Uses the test_db_engine fixture from conftest.py.
    """
    with Session(test_db_engine) as session:
        # Create a test store
        store = Store(
            id="rema1000-test",
            name="REMA 1000 Test Store",
            brand="rema1000",
            is_active=True,
        )
        session.add(store)
        session.commit()

        yield session


@pytest.mark.integration
class TestProductIngestion:
    """Integration tests for scraping and storing products."""

    @pytest.mark.asyncio
    async def test_scrape_and_ingest_10_products(self, test_db):
        """Test scraping 10 products from REMA 1000 and storing in database."""
        session = test_db

        # Step 1: Scrape products from REMA 1000
        print("\n--- Scraping 10 products from REMA 1000 ---")
        async with Rema1000Scraper() as scraper:
            scraped_products = await scraper.scrape_products(limit=10)

        assert len(scraped_products) >= 10, f"Expected 10 products, got {len(scraped_products)}"
        print(f"Scraped {len(scraped_products)} products")

        # Step 2: Ingest products into database
        print("\n--- Ingesting products into database ---")
        products_inserted = _upsert_scraped_products(
            session=session,
            store_id="rema1000-test",
            products=scraped_products[:10],
        )

        assert products_inserted == 10, f"Expected 10 inserts, got {products_inserted}"
        print(f"Inserted {products_inserted} products")

        # Step 3: Verify products are in database
        print("\n--- Verifying products in database ---")
        db_products = (
            session.execute(select(Product).where(Product.store_id == "rema1000-test"))
            .scalars()
            .all()
        )

        assert len(db_products) == 10, f"Expected 10 products in DB, found {len(db_products)}"

        # Verify product data integrity
        for product in db_products:
            assert product.id, "Product missing ID"
            assert product.name, "Product missing name"
            assert product.price >= 0, f"Invalid price: {product.price}"
            assert product.store_id == "rema1000-test"
            print(f"  - {product.name}: {product.price:.2f} kr (ID: {product.id})")

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_products(self, test_db):
        """Test that upserting updates existing products instead of duplicating."""
        session = test_db

        # Step 1: Scrape initial products
        async with Rema1000Scraper() as scraper:
            products = await scraper.scrape_products(limit=5)

        # Step 2: First insert
        _upsert_scraped_products(
            session=session,
            store_id="rema1000-test",
            products=products[:5],
        )

        initial_count = (
            session.execute(select(Product).where(Product.store_id == "rema1000-test"))
            .scalars()
            .all()
        )
        assert len(initial_count) == 5

        # Step 3: Modify prices and re-insert (simulating price update)
        for product in products[:5]:
            product["price"] = product["price"] + 1.0  # Increase price by 1

        _upsert_scraped_products(
            session=session,
            store_id="rema1000-test",
            products=products[:5],
        )

        # Step 4: Verify count unchanged (upsert, not insert)
        final_products = (
            session.execute(select(Product).where(Product.store_id == "rema1000-test"))
            .scalars()
            .all()
        )

        assert len(final_products) == 5, f"Expected 5 products (upsert), got {len(final_products)}"

        # Verify prices were updated
        for db_product in final_products:
            # Find the corresponding scraped product
            scraped = next((p for p in products if p["id"] == db_product.id), None)
            if scraped:
                assert (
                    db_product.price == scraped["price"]
                ), f"Price not updated for {db_product.name}"

        print("\n--- Upsert correctly updated existing products ---")

    @pytest.mark.asyncio
    async def test_scrape_category_and_ingest(self, test_db):
        """Test scraping a specific category and ingesting."""
        session = test_db

        # Scrape products from Frugt & Grønt category
        print("\n--- Scraping products from Frugt & Grønt ---")
        async with Rema1000Scraper() as scraper:
            products = await scraper.scrape_products(category="frugt-gront", limit=5)

        assert len(products) > 0, "No products returned from category"

        # Verify category is set on scraped products
        for product in products:
            assert product.get("category") == "Frugt & Grønt"

        # Ingest into database
        _upsert_scraped_products(
            session=session,
            store_id="rema1000-test",
            products=products,
        )

        # Verify in database
        db_products = (
            session.execute(
                select(Product).where(
                    Product.store_id == "rema1000-test",
                    Product.category == "Frugt & Grønt",
                )
            )
            .scalars()
            .all()
        )

        assert len(db_products) == len(products)
        print(f"Inserted {len(db_products)} products from Frugt & Grønt category")

        for product in db_products:
            print(f"  - {product.name}: {product.price:.2f} kr")

    @pytest.mark.asyncio
    async def test_product_fields_stored_correctly(self, test_db):
        """Test that all product fields are stored correctly."""
        session = test_db

        # Scrape products
        async with Rema1000Scraper() as scraper:
            products = await scraper.scrape_products(limit=3)

        # Ingest
        _upsert_scraped_products(
            session=session,
            store_id="rema1000-test",
            products=products,
        )

        # Verify fields
        db_products = (
            session.execute(select(Product).where(Product.store_id == "rema1000-test"))
            .scalars()
            .all()
        )

        print("\n--- Product fields verification ---")
        for db_product in db_products:
            print(f"\nProduct: {db_product.name}")
            print(f"  ID: {db_product.id}")
            print(f"  Price: {db_product.price}")
            print(f"  Unit: {db_product.unit}")
            print(f"  Category: {db_product.category}")
            print(f"  Image URL: {db_product.image_url[:50] if db_product.image_url else 'N/A'}...")
            print(f"  Description: {db_product.description}")
            print(f"  Origin: {db_product.origin}")
            print(f"  Last Updated: {db_product.last_updated}")

            # Basic assertions
            assert db_product.id is not None
            assert db_product.name is not None
            assert db_product.price is not None
            assert db_product.last_updated is not None
            assert isinstance(db_product.last_updated, datetime)


@pytest.mark.integration
class TestBulkIngestion:
    """Tests for bulk ingestion scenarios."""

    @pytest.mark.asyncio
    async def test_ingest_multiple_categories(self, test_db):
        """Test ingesting products from multiple categories."""
        session = test_db

        categories = ["frugt-gront", "mejeri", "kolonial"]
        total_products = 0

        async with Rema1000Scraper() as scraper:
            for category in categories:
                print(f"\n--- Scraping {category} ---")
                products = await scraper.scrape_products(category=category, limit=3)

                if products:
                    _upsert_scraped_products(
                        session=session,
                        store_id="rema1000-test",
                        products=products,
                    )
                    total_products += len(products)
                    print(f"  Ingested {len(products)} products")

        # Verify all products are in database
        db_count = (
            session.execute(select(Product).where(Product.store_id == "rema1000-test"))
            .scalars()
            .all()
        )

        print(f"\n--- Total products in database: {len(db_count)} ---")
        assert len(db_count) == total_products

    @pytest.mark.asyncio
    async def test_large_batch_ingestion(self, test_db):
        """Test ingesting a larger batch of products."""
        session = test_db

        # Scrape 50 products
        print("\n--- Scraping 50 products ---")
        async with Rema1000Scraper() as scraper:
            products = await scraper.scrape_products(limit=50)

        assert len(products) >= 50, f"Expected 50 products, got {len(products)}"

        # Count unique product IDs (some may be duplicates)
        unique_ids = set(p["id"] for p in products[:50])
        print(f"Unique product IDs: {len(unique_ids)}")

        # Ingest all at once
        print(f"--- Ingesting {len(products[:50])} products ---")
        products_inserted = _upsert_scraped_products(
            session=session,
            store_id="rema1000-test",
            products=products[:50],
        )

        assert products_inserted == 50  # Number of upsert operations
        print(f"Successfully processed {products_inserted} upserts")

        # Verify - should have number of unique IDs (duplicates merged)
        db_products = (
            session.execute(select(Product).where(Product.store_id == "rema1000-test"))
            .scalars()
            .all()
        )

        # Allow for duplicates being merged (upsert behavior)
        assert (
            len(db_products) >= len(unique_ids) * 0.9
        ), f"Expected ~{len(unique_ids)} unique products, got {len(db_products)}"
        print(f"Verified {len(db_products)} unique products in database")

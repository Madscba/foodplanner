"""End-to-end integration tests for the ingestion pipeline.

These tests verify the full flow from scraping to database.

Run with:
    pytest tests/integration/test_ingestion_pipeline.py -v

Requirements:
    - PostgreSQL database (use Docker: docker-compose up -d db)
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from foodplanner.database import Base
from foodplanner.ingest.batch_ingest import (
    IngestionResult,
    _upsert_scraped_products,
    cleanup_old_data,
    ingest_store,
    run_daily_ingestion,
)
from foodplanner.models import (
    Discount,
    IngestionRun,
    Product,
    RawIngestionData,
    Store,
    StoreIngestionStatus,
)

# Note: test_db_engine, test_session, sample_store, and sample_scraped_products
# fixtures are provided by conftest.py


class TestUpsertScrapedProducts:
    """Tests for upserting scraped products to database."""

    def test_upsert_creates_products(self, test_session, sample_store, sample_scraped_products):
        """Test that upsert creates products."""
        products_inserted = _upsert_scraped_products(
            session=test_session,
            store_id=sample_store.id,
            products=sample_scraped_products,
        )

        assert products_inserted == 2

        # Verify products in database
        products = test_session.execute(select(Product)).scalars().all()
        assert len(products) == 2

    def test_upsert_updates_existing_products(
        self, test_session, sample_store, sample_scraped_products
    ):
        """Test that upsert updates existing products."""
        # First upsert
        _upsert_scraped_products(
            session=test_session,
            store_id=sample_store.id,
            products=sample_scraped_products,
        )

        # Modify product and upsert again
        sample_scraped_products[0]["price"] = 69.95
        _upsert_scraped_products(
            session=test_session,
            store_id=sample_store.id,
            products=sample_scraped_products,
        )

        # Should still have 2 products (updated, not duplicated)
        product_count = test_session.execute(select(func.count(Product.id))).scalar()
        assert product_count == 2

        # Price should be updated
        product = test_session.execute(
            select(Product).where(Product.ean == "5701234567890")
        ).scalar_one()
        assert product.price == 69.95


class TestIngestionResult:
    """Tests for IngestionResult class."""

    def test_ingestion_result_defaults(self):
        """Test IngestionResult default values."""
        result = IngestionResult()

        assert result.stores_total == 0
        assert result.stores_completed == 0
        assert result.stores_failed == 0
        assert result.products_updated == 0
        assert result.discounts_updated == 0
        assert result.errors == []

    def test_ingestion_result_to_dict(self):
        """Test IngestionResult serialization."""
        result = IngestionResult()
        result.stores_total = 5
        result.stores_completed = 4
        result.stores_failed = 1
        result.errors.append("Test error")

        data = result.to_dict()

        assert data["stores_total"] == 5
        assert data["stores_completed"] == 4
        assert data["stores_failed"] == 1
        assert "Test error" in data["errors"]


@pytest.mark.integration
class TestIngestStoreMocked:
    """Tests for ingest_store with mocked scraper."""

    @pytest.mark.asyncio
    async def test_ingest_store_success(
        self, test_db_engine, test_session, sample_store, sample_scraped_products
    ):
        """Test successful store ingestion with mocked scraper."""
        # Create an ingestion run
        run = IngestionRun(
            run_date=date.today(),
            status="running",
            trigger_type="test",
            stores_total=1,
            started_at=datetime.utcnow(),
        )
        test_session.add(run)
        test_session.commit()

        # Mock the scraper
        mock_scraper = AsyncMock()
        mock_scraper.scrape_products = AsyncMock(return_value=sample_scraped_products)
        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock()

        with patch("foodplanner.ingest.batch_ingest.get_scraper_for_store") as mock_get_scraper:
            mock_get_scraper.return_value = mock_scraper

            with patch("foodplanner.ingest.batch_ingest.sync_engine", test_db_engine):
                result = await ingest_store(
                    store_id=sample_store.id,
                    run_id=run.id,
                    session=test_session,
                )

        assert result["status"] == "completed"
        assert result["products_inserted"] == 2

        # Verify status record created
        status = test_session.execute(
            select(StoreIngestionStatus).where(
                StoreIngestionStatus.run_id == run.id,
                StoreIngestionStatus.store_id == sample_store.id,
            )
        ).scalar_one()

        assert status.status == "completed"
        assert status.products_fetched == 2


@pytest.mark.integration
class TestRunDailyIngestionMocked:
    """Tests for run_daily_ingestion with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_run_daily_ingestion_no_stores(self, test_db_engine):
        """Test daily ingestion with no configured stores."""
        with patch("foodplanner.ingest.batch_ingest.sync_engine", test_db_engine):
            result = await run_daily_ingestion(trigger_type="test")

        assert result["status"] == "no_stores"

    @pytest.mark.asyncio
    async def test_run_daily_ingestion_with_stores(self, test_db_engine, sample_scraped_products):
        """Test daily ingestion with specified stores."""
        # Create test database and store
        Base.metadata.create_all(test_db_engine)

        with Session(test_db_engine) as session:
            store = Store(
                id="test-store-e2e",
                name="E2E Test Store",
                brand="rema1000",
                is_active=True,
            )
            session.add(store)
            session.commit()

        # Mock the scraper
        mock_scraper = AsyncMock()
        mock_scraper.scrape_products = AsyncMock(return_value=sample_scraped_products)
        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock()

        with patch("foodplanner.ingest.batch_ingest.get_scraper_for_store") as mock_get_scraper:
            mock_get_scraper.return_value = mock_scraper

            with patch("foodplanner.ingest.batch_ingest.sync_engine", test_db_engine):
                result = await run_daily_ingestion(
                    store_ids=["test-store-e2e"],
                    trigger_type="test",
                )

        assert result["status"] == "completed"
        assert result["stores_completed"] == 1
        assert result["products_updated"] == 2

        # Verify database state
        with Session(test_db_engine) as session:
            run = session.execute(
                select(IngestionRun).order_by(IngestionRun.id.desc())
            ).scalar_one()

            assert run.status == "completed"
            assert run.products_updated == 2

    @pytest.mark.asyncio
    async def test_run_daily_ingestion_idempotent(self, test_db_engine, sample_scraped_products):
        """Test that running twice on same day is idempotent."""
        Base.metadata.create_all(test_db_engine)

        with Session(test_db_engine) as session:
            store = Store(
                id="test-store-idempotent",
                name="Idempotent Test Store",
                brand="rema1000",
                is_active=True,
            )
            session.add(store)
            session.commit()

        mock_scraper = AsyncMock()
        mock_scraper.scrape_products = AsyncMock(return_value=sample_scraped_products)
        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock()

        with patch("foodplanner.ingest.batch_ingest.get_scraper_for_store") as mock_get_scraper:
            mock_get_scraper.return_value = mock_scraper

            with patch("foodplanner.ingest.batch_ingest.sync_engine", test_db_engine):
                # First run
                result1 = await run_daily_ingestion(
                    store_ids=["test-store-idempotent"],
                    trigger_type="test",
                )

                # Second run (should skip)
                result2 = await run_daily_ingestion(
                    store_ids=["test-store-idempotent"],
                    trigger_type="test",
                )

        assert result1["status"] == "completed"
        assert result2["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_run_daily_ingestion_force_rerun(self, test_db_engine, sample_scraped_products):
        """Test force flag allows re-ingestion."""
        Base.metadata.create_all(test_db_engine)

        with Session(test_db_engine) as session:
            store = Store(
                id="test-store-force",
                name="Force Test Store",
                brand="rema1000",
                is_active=True,
            )
            session.add(store)
            session.commit()

        mock_scraper = AsyncMock()
        mock_scraper.scrape_products = AsyncMock(return_value=sample_scraped_products)
        mock_scraper.__aenter__ = AsyncMock(return_value=mock_scraper)
        mock_scraper.__aexit__ = AsyncMock()

        with patch("foodplanner.ingest.batch_ingest.get_scraper_for_store") as mock_get_scraper:
            mock_get_scraper.return_value = mock_scraper

            with patch("foodplanner.ingest.batch_ingest.sync_engine", test_db_engine):
                # First run
                result1 = await run_daily_ingestion(
                    store_ids=["test-store-force"],
                    trigger_type="test",
                )

                # Second run with force=True
                result2 = await run_daily_ingestion(
                    store_ids=["test-store-force"],
                    trigger_type="test",
                    force=True,
                )

        assert result1["status"] == "completed"
        assert result2["status"] == "completed"

        # Should have 2 ingestion runs
        with Session(test_db_engine) as session:
            run_count = session.execute(select(func.count(IngestionRun.id))).scalar()
            assert run_count == 2


@pytest.mark.integration
class TestCleanupOldData:
    """Tests for cleanup_old_data function."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_data(self, test_db_engine):
        """Test that cleanup removes old raw data and expired discounts."""
        Base.metadata.create_all(test_db_engine)

        with Session(test_db_engine) as session:
            # Create store and product
            store = Store(
                id="cleanup-store", name="Cleanup Store", brand="rema1000", is_active=True
            )
            session.add(store)
            session.commit()

            product = Product(
                id="cleanup-product",
                store_id=store.id,
                name="Test Product",
                price=10.0,
                unit="unit",
            )
            session.add(product)

            # Create old run
            old_run = IngestionRun(
                run_date=date.today() - timedelta(days=60),
                status="completed",
                trigger_type="test",
                started_at=datetime.utcnow() - timedelta(days=60),
            )
            session.add(old_run)
            session.commit()

            # Create old raw data
            old_raw = RawIngestionData(
                run_id=old_run.id,
                store_id=store.id,
                endpoint="/test",
                response_data={},
                response_status=200,
                fetched_at=datetime.utcnow() - timedelta(days=60),
            )
            session.add(old_raw)

            # Create expired discount
            old_discount = Discount(
                product_id=product.id,
                store_id=store.id,
                discount_price=8.0,
                valid_from=date.today() - timedelta(days=30),
                valid_to=date.today() - timedelta(days=20),
            )
            session.add(old_discount)
            session.commit()

            old_raw_id = old_raw.id
            old_discount_id = old_discount.id

        with patch("foodplanner.ingest.batch_ingest.sync_engine", test_db_engine):
            result = await cleanup_old_data(days_to_keep=30)

        assert result["raw_data_deleted"] >= 1
        assert result["discounts_deleted"] >= 1

        # Verify data was actually deleted
        with Session(test_db_engine) as session:
            raw = session.get(RawIngestionData, old_raw_id)
            discount = session.get(Discount, old_discount_id)

            assert raw is None
            assert discount is None

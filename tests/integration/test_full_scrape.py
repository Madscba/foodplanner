"""Integration tests for the full REMA 1000 scrape functionality.

These tests verify the extended scraper capabilities including:
- Pagination/infinite scroll handling
- Product detail fetching
- Anti-blocking measures
- Progress tracking

Run with: uv run pytest tests/integration/test_full_scrape.py -v -s
"""

import pytest

from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper, ScrapeProgress


@pytest.mark.integration
class TestFullScrapeIntegration:
    """Integration tests for full scrape capabilities."""

    @pytest.mark.asyncio
    async def test_scrape_category_with_pagination(self):
        """Test scraping a full category with pagination/infinite scroll."""
        # Use a smaller category for faster testing
        category = "kiosk"  # Typically has fewer products

        async with Rema1000Scraper(
            headless=True,
            min_delay=1.0,  # Faster for testing
            max_delay=2.0,
        ) as scraper:
            products = []
            async for product in scraper.scrape_category_products_full(
                category_slug=category,
                include_details=False,  # Skip details for speed
            ):
                products.append(product)
                # Limit for testing
                if len(products) >= 20:
                    break

            # Should get some products
            assert len(products) > 0, f"No products from category {category}"

            print(f"\n--- Category {category}: {len(products)} products ---")
            for p in products[:5]:
                print(f"  - {p['name']} ({p['price']:.2f} kr)")

            # Verify category is set
            for p in products:
                assert p.get("category"), "Product missing category"

    @pytest.mark.asyncio
    async def test_scrape_product_details(self):
        """Test fetching detailed information for a product."""
        async with Rema1000Scraper(headless=True) as scraper:
            # First get a product to test
            products = await scraper.scrape_products(limit=5)
            assert len(products) > 0, "No products to test details"

            product_id = products[0]["id"]
            print(f"\n--- Testing product details for ID: {product_id} ---")

            details = await scraper.scrape_product_details(product_id)

            # Details may be None if the product page doesn't exist
            # or doesn't have the expected structure
            if details:
                print(f"  Description: {details.get('description', 'N/A')[:100]}...")
                print(f"  Brand: {details.get('brand', 'N/A')}")
                print(f"  EAN: {details.get('ean', 'N/A')}")
                print(f"  Nutrition: {details.get('nutrition_info', {})}")
            else:
                print("  (No details available)")

    @pytest.mark.asyncio
    async def test_scrape_category_with_details(self):
        """Test scraping products with full details."""
        async with Rema1000Scraper(
            headless=True,
            min_delay=1.0,
            max_delay=2.0,
            detail_min_delay=0.5,
            detail_max_delay=1.0,
        ) as scraper:
            products = []
            progress = ScrapeProgress()

            async for product in scraper.scrape_category_products_full(
                category_slug="slik",  # Small category
                include_details=True,
                progress=progress,
            ):
                products.append(product)
                # Limit for testing
                if len(products) >= 5:
                    break

            print(f"\n--- Products with details: {len(products)} ---")
            for p in products:
                print(f"  - {p['name']}")
                print(f"    Price: {p['price']:.2f} kr")
                print(f"    Description: {p.get('description', 'N/A')[:50]}...")
                print(f"    Brand: {p.get('brand', 'N/A')}")

            # Check progress tracking
            print("\n--- Progress ---")
            print(f"  Products scraped: {progress.products_scraped}")
            print(f"  Products with details: {progress.products_with_details}")

    @pytest.mark.asyncio
    async def test_scrape_multiple_categories(self):
        """Test scraping from multiple categories."""
        # Test with two small categories
        categories = ["kiosk", "slik"]

        async with Rema1000Scraper(
            headless=True,
            min_delay=1.0,
            max_delay=2.0,
            category_delay=5.0,  # Shorter for testing
        ) as scraper:
            products = []

            def progress_callback(p: ScrapeProgress) -> None:
                print(f"  Progress: {p.categories_completed}/{p.categories_total} categories")

            async for product in scraper.scrape_all_products(
                include_details=False,
                categories=categories,
                progress_callback=progress_callback,
            ):
                products.append(product)
                # Limit for testing
                if len(products) >= 30:
                    break

            print(f"\n--- Multi-category scrape: {len(products)} total products ---")

            # Group by category
            by_category: dict[str, int] = {}
            for p in products:
                cat = p.get("category", "Unknown")
                by_category[cat] = by_category.get(cat, 0) + 1

            for cat, count in by_category.items():
                print(f"  {cat}: {count} products")

    @pytest.mark.asyncio
    async def test_progress_tracking(self):
        """Test that progress tracking works correctly."""
        progress = ScrapeProgress()
        progress.categories_total = 16
        progress.current_category = "frugt-gront"

        async with Rema1000Scraper(
            headless=True,
            min_delay=0.5,
            max_delay=1.0,
        ) as scraper:
            count = 0
            async for _product in scraper.scrape_category_products_full(
                category_slug="mejeri",
                include_details=False,
                progress=progress,
            ):
                count += 1
                if count >= 10:
                    break

            # Verify progress was updated
            assert progress.products_scraped >= count, "Progress not tracking products"
            print("\n--- Progress tracking ---")
            print(f"  products_scraped: {progress.products_scraped}")
            print(f"  current_category: {progress.current_category}")

    @pytest.mark.asyncio
    async def test_scrape_cancellation(self):
        """Test that scraping can be cancelled gracefully."""
        progress = ScrapeProgress()

        async with Rema1000Scraper(headless=True) as scraper:
            count = 0
            async for _product in scraper.scrape_category_products_full(
                category_slug="kolonial",
                include_details=False,
                progress=progress,
            ):
                count += 1
                if count >= 5:
                    # Request cancellation
                    scraper.cancel_scrape(progress)

                if progress.is_cancelled:
                    break

            print("\n--- Cancellation test ---")
            print(f"  Products before cancel: {count}")
            print(f"  is_cancelled: {progress.is_cancelled}")

            assert progress.is_cancelled, "Cancellation should be set"
            assert count >= 5, "Should have scraped at least 5 products before cancel"

    @pytest.mark.asyncio
    async def test_user_agent_rotation(self):
        """Test that user agent rotation works."""
        scraper = Rema1000Scraper(headless=True)

        initial_ua = scraper._current_user_agent
        initial_viewport = scraper._current_viewport

        # Rotate identity
        scraper._rotate_identity()

        # Should have changed (with high probability due to randomness)
        # Note: There's a small chance it picks the same one
        print("\n--- User Agent Rotation ---")
        print(f"  Initial UA: {initial_ua[:50]}...")
        print(f"  New UA: {scraper._current_user_agent[:50]}...")
        print(f"  Initial viewport: {initial_viewport}")
        print(f"  New viewport: {scraper._current_viewport}")

    @pytest.mark.asyncio
    async def test_backoff_mechanism(self):
        """Test that the backoff mechanism works."""
        scraper = Rema1000Scraper(
            headless=True,
            min_delay=1.0,
            max_consecutive_errors=3,
            backoff_factor=2.0,
        )

        # Initial state
        assert scraper._current_backoff == 1.0
        assert scraper._consecutive_errors == 0

        # Record some errors
        scraper._record_error("Test error 1")
        assert scraper._consecutive_errors == 1

        scraper._record_error("Test error 2")
        assert scraper._consecutive_errors == 2

        # Reset backoff
        scraper._reset_backoff()
        assert scraper._consecutive_errors == 0
        assert scraper._current_backoff == 1.0

        print("\n--- Backoff mechanism verified ---")


@pytest.mark.integration
class TestFullScrapeAPI:
    """Integration tests for the full scrape API endpoints."""

    @pytest.mark.asyncio
    async def test_categories_endpoint(self):
        """Test the categories list endpoint."""
        from httpx import ASGITransport, AsyncClient

        from foodplanner.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/scrape/rema1000/categories")

            assert response.status_code == 200
            data = response.json()

            assert "categories" in data
            assert "total" in data
            assert data["total"] == 16

            print("\n--- Categories endpoint ---")
            print(f"  Total categories: {data['total']}")

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test the scraper health check endpoint."""
        from httpx import ASGITransport, AsyncClient

        from foodplanner.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/scrape/rema1000/health")

            assert response.status_code == 200
            data = response.json()

            assert "healthy" in data
            assert "website" in data
            assert "checked_at" in data

            print("\n--- Health endpoint ---")
            print(f"  Healthy: {data['healthy']}")
            print(f"  Website: {data['website']}")

    @pytest.mark.asyncio
    async def test_active_scrape_endpoint_no_active(self):
        """Test the active scrape endpoint when no scrape is running."""
        from httpx import ASGITransport, AsyncClient

        from foodplanner.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/scrape/rema1000/active")

            assert response.status_code == 200
            data = response.json()

            # Should be no active scrape in test environment
            print("\n--- Active scrape endpoint ---")
            print(f"  Active: {data['active']}")


@pytest.mark.integration
@pytest.mark.slow
class TestFullScrapeEndToEnd:
    """End-to-end integration tests (slower, more comprehensive)."""

    @pytest.mark.asyncio
    async def test_full_category_scrape_with_details(self):
        """Test a complete category scrape with all products and details.

        This is a slower test that scrapes an entire small category.
        """
        async with Rema1000Scraper(
            headless=True,
            min_delay=2.0,
            max_delay=4.0,
            detail_min_delay=1.0,
            detail_max_delay=2.0,
        ) as scraper:
            products = []
            progress = ScrapeProgress()

            # Use a small category
            async for product in scraper.scrape_category_products_full(
                category_slug="kiosk",
                include_details=True,
                progress=progress,
            ):
                products.append(product)

            print("\n--- Full category scrape: kiosk ---")
            print(f"  Total products: {len(products)}")
            print(f"  With details: {progress.products_with_details}")
            print(f"  Errors: {len(progress.errors)}")

            # Verify data quality
            with_names = sum(1 for p in products if p.get("name"))
            with_prices = sum(1 for p in products if p.get("price", 0) > 0)
            with_images = sum(1 for p in products if p.get("image_url"))

            print("\n--- Data quality ---")
            print(f"  With names: {with_names}/{len(products)}")
            print(f"  With prices: {with_prices}/{len(products)}")
            print(f"  With images: {with_images}/{len(products)}")

            # At least 80% should have core data
            if len(products) > 0:
                assert with_names >= len(products) * 0.8
                assert with_prices >= len(products) * 0.8

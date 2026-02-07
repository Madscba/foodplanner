"""Integration tests for REMA 1000 scraper.

These tests use Playwright to scrape the REMA 1000 website.
Run with: uv run pytest tests/integration/test_rema1000_scraper.py -v -s
"""

import pytest

from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper


@pytest.mark.integration
class TestRema1000ScraperIntegration:
    """Integration tests that scrape the real REMA 1000 website."""

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test that the scraper can reach the REMA 1000 website."""
        async with Rema1000Scraper() as scraper:
            is_healthy = await scraper.health_check()
            assert is_healthy, "REMA 1000 website is not reachable"

    @pytest.mark.asyncio
    async def test_fetch_10_products(self):
        """Test fetching 10 products from REMA 1000."""
        async with Rema1000Scraper() as scraper:
            products = await scraper.scrape_products(limit=10)

            # Verify we got products
            assert len(products) >= 10, f"Expected at least 10 products, got {len(products)}"

            # Verify product structure
            for product in products[:10]:
                assert "id" in product, "Product missing 'id' field"
                assert "name" in product, "Product missing 'name' field"
                assert "price" in product, "Product missing 'price' field"
                assert product["id"], f"Product has empty id: {product}"
                assert product["name"], f"Product has empty name: {product}"
                assert isinstance(
                    product["price"], (int, float)
                ), f"Price should be numeric: {product}"

            # Log some products for debugging
            print("\n--- First 10 products fetched ---")
            for product in products[:10]:
                name = product["name"]
                pid = product["id"]
                price = product["price"]
                print(f"  - {name} (ID: {pid}, Price: {price:.2f} kr)")

    @pytest.mark.asyncio
    async def test_fetch_products_with_category(self):
        """Test fetching products from a specific category."""
        async with Rema1000Scraper() as scraper:
            products = await scraper.scrape_products(category="frugt-gront", limit=5)

            # Verify we got products
            assert len(products) > 0, "No products returned from category"

            # Verify category is set
            for product in products:
                assert product.get("category") == "Frugt & Grønt"

            print(f"\n--- Products from Frugt & Grønt: {len(products)} ---")
            for product in products[:5]:
                print(f"  - {product['name']} ({product['price']:.2f} kr)")

    @pytest.mark.asyncio
    async def test_fetch_categories(self):
        """Test fetching categories from REMA 1000."""
        async with Rema1000Scraper() as scraper:
            categories = await scraper.scrape_categories()

            # Verify we got categories
            assert len(categories) > 0, "No categories returned"

            # Verify category structure
            for cat in categories:
                assert "id" in cat, "Category missing 'id' field"
                assert "name" in cat, "Category missing 'name' field"
                assert "slug" in cat, "Category missing 'slug' field"

            # Log categories
            print("\n--- Categories ---")
            for cat in categories:
                print(f"  - {cat['name']} (slug: {cat['slug']})")

    @pytest.mark.asyncio
    async def test_search_products(self):
        """Test searching for products."""
        async with Rema1000Scraper() as scraper:
            # Search for a common Danish product term
            products = await scraper.search_products("mælk", limit=5)

            print(f"\n--- Search for 'mælk': {len(products)} results ---")
            for product in products[:5]:
                print(f"  - {product['name']} ({product['price']:.2f} kr)")

    @pytest.mark.asyncio
    async def test_product_data_quality(self):
        """Test that scraped product data has reasonable quality."""
        async with Rema1000Scraper() as scraper:
            products = await scraper.scrape_products(limit=20)

            # Check data quality
            products_with_images = sum(1 for p in products if p.get("image_url"))
            products_with_prices = sum(1 for p in products if p.get("price", 0) > 0)

            print(f"\n--- Data Quality Check (n={len(products)}) ---")
            print(f"  Products with images: {products_with_images}/{len(products)}")
            print(f"  Products with prices: {products_with_prices}/{len(products)}")

            # At least 80% should have images and prices
            assert products_with_images >= len(products) * 0.8, "Too many products missing images"
            assert products_with_prices >= len(products) * 0.8, "Too many products missing prices"
